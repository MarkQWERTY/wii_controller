import asyncio
import json
import logging
import ssl
import struct
import time
import uuid
import binascii
from typing import Dict, Any

from aiohttp import web

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Shared State ---
# Store the latest state received from the mobile phone
class ControllerState:
    def __init__(self):
        self.connected = False
        self.buttons = {
            'up': False, 'down': False, 'left': False, 'right': False,
            'A': False, 'B': False, 'minus': False, 'home': False, 'plus': False,
            '1': False, '2': False
        }
        self.motion = {
            'accel': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'gyro': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'timestamp': 0
        }
        self.mac_address = "00:11:22:33:44:55"
        self.packet_count = 0

controller_state = ControllerState()

# --- WebSocket Server (AIOHTTP) ---
async def handle_index(request):
    return web.FileResponse('./public/index.html')

async def handle_style(request):
    return web.FileResponse('./public/style.css')

async def handle_script(request):
    return web.FileResponse('./public/script.js')

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logging.info("WebSocket connection opened")
    controller_state.connected = True

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    controller_state.buttons.update(data.get('buttons', {}))
                    controller_state.motion.update(data.get('motion', {}))
                except json.JSONDecodeError:
                    pass
            elif msg.type == web.WSMsgType.ERROR:
                logging.error(f"WebSocket connection closed with exception {ws.exception()}")
    finally:
        logging.info("WebSocket connection closed")
        controller_state.connected = False

    return ws

# --- DSU (CemuHook) UDP Server ---
class DSUServerProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.server_id = uuid.uuid4().int & 0xFFFFFFFF
        self.clients = set()  # Store (ip, port) of connected emulators
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logging.info(f"DSU UDP Server listening")

    def error_received(self, exc):
        logging.debug(f"DSU UDP Server error received: {exc}")

    def connection_lost(self, exc):
        pass

    def datagram_received(self, data, addr):
        if len(data) < 16:
            return

        magic = data[0:4]
        if magic != b'DSUC':
            return

        version = struct.unpack('<H', data[4:6])[0]
        length = struct.unpack('<H', data[6:8])[0]
        crc32 = struct.unpack('<I', data[8:12])[0]
        client_id = struct.unpack('<I', data[12:16])[0]
        msg_type = struct.unpack('<I', data[16:20])[0]

        if msg_type == 0x100000: # Protocol version info
            self.send_protocol_version(addr)
        elif msg_type == 0x100001: # Info about connected controllers
            self.send_controller_info(addr, data[20:])
        elif msg_type == 0x100002: # Actual controller data (subscription request)
            self.clients.add(addr)
            self.send_controller_data(addr)

    def calculate_crc(self, data):
        return binascii.crc32(data) & 0xffffffff

    def send_packet(self, addr, msg_type, payload):
        header = struct.pack('<4sHHII', b'DSUS', 1001, len(payload) + 4, 0, self.server_id)
        msg_type_bytes = struct.pack('<I', msg_type)
        
        packet = bytearray(header + msg_type_bytes + payload)
        
        # Calculate CRC of packet with CRC field set to 0
        crc = self.calculate_crc(packet)
        struct.pack_into('<I', packet, 8, crc)
        
        self.transport.sendto(packet, addr)

    def send_protocol_version(self, addr):
        payload = struct.pack('<H', 1001)
        self.send_packet(addr, 0x100000, payload)

    def _get_shared_response_beginning(self, slot):
        # 0: Slot, 1: State (0: Not connected, 2: Connected), 2: Model (2: Full gyro)
        # 3: Connection type (1: USB, 2: Bluetooth), 4-9: MAC address, 10: Battery (5: Full)
        state = 2 if controller_state.connected else 0
        mac_bytes = bytes.fromhex(controller_state.mac_address.replace(':', ''))
        return struct.pack('<BBB', slot, state, 2) + struct.pack('<B', 2) + mac_bytes + struct.pack('<B', 0x05)

    def send_controller_info(self, addr, payload):
        if len(payload) < 4:
            return
        
        amount_of_ports = struct.unpack('<I', payload[0:4])[0]
        ports = payload[4:4+amount_of_ports]
        
        for port in ports:
            # We only support port 0 (slot 0)
            if port == 0:
                resp_payload = self._get_shared_response_beginning(0) + b'\x00'
                self.send_packet(addr, 0x100001, resp_payload)

    def send_controller_data(self, addr=None):
        if not controller_state.connected:
            return

        slot = 0
        shared = self._get_shared_response_beginning(slot)
        
        is_connected = 1
        packet_num = controller_state.packet_count
        controller_state.packet_count += 1
        
        # Build bitmasks
        # D-Pad Left, D-Pad Down, D-Pad Right, D-Pad Up, Options, R3, L3, Share
        btn_mask1 = 0
        if controller_state.buttons.get('left'): btn_mask1 |= 0x80
        if controller_state.buttons.get('down'): btn_mask1 |= 0x40
        if controller_state.buttons.get('right'): btn_mask1 |= 0x20
        if controller_state.buttons.get('up'): btn_mask1 |= 0x10
        if controller_state.buttons.get('plus'): btn_mask1 |= 0x08 # Options
        if controller_state.buttons.get('minus'): btn_mask1 |= 0x01 # Share
        
        # Y, B, A, X, R1, L1, R2, L2
        btn_mask2 = 0
        if controller_state.buttons.get('1'): btn_mask2 |= 0x80 # Y -> 1
        if controller_state.buttons.get('B'): btn_mask2 |= 0x40
        if controller_state.buttons.get('A'): btn_mask2 |= 0x20
        if controller_state.buttons.get('2'): btn_mask2 |= 0x10 # X -> 2

        home_btn = 1 if controller_state.buttons.get('home') else 0
        touch_btn = 0
        
        ls_x, ls_y, rs_x, rs_y = 128, 128, 128, 128
        
        analog_buttons = bytes([
            255 if controller_state.buttons.get('left') else 0,
            255 if controller_state.buttons.get('down') else 0,
            255 if controller_state.buttons.get('right') else 0,
            255 if controller_state.buttons.get('up') else 0,
            255 if controller_state.buttons.get('1') else 0, # Y
            255 if controller_state.buttons.get('B') else 0,
            255 if controller_state.buttons.get('A') else 0,
            255 if controller_state.buttons.get('2') else 0, # X
            0, 0, 0, 0 # R1, L1, R2, L2
        ])
        
        touch_data = b'\x00' * 12
        
        timestamp = int(time.time() * 1000000) & 0xFFFFFFFFFFFFFFFF
        accel_x = float(controller_state.motion['accel'].get('x', 0.0))
        accel_y = float(controller_state.motion['accel'].get('y', 0.0))
        accel_z = float(controller_state.motion['accel'].get('z', 0.0))
        
        gyro_p = float(controller_state.motion['gyro'].get('x', 0.0))
        gyro_r = float(controller_state.motion['gyro'].get('y', 0.0))
        gyro_y = float(controller_state.motion['gyro'].get('z', 0.0))

        data_payload = shared + struct.pack('<BI', is_connected, packet_num) + \
            struct.pack('<BBBBBBBB', btn_mask1, btn_mask2, home_btn, touch_btn, ls_x, ls_y, rs_x, rs_y) + \
            analog_buttons + touch_data + \
            struct.pack('<Qffffff', timestamp, accel_x, accel_y, accel_z, gyro_p, gyro_y, gyro_r)

        if addr:
            self.send_packet(addr, 0x100002, data_payload)
        else:
            for client_addr in list(self.clients):
                self.send_packet(client_addr, 0x100002, data_payload)

async def dsu_broadcast_task(protocol):
    while True:
        try:
            if protocol and protocol.clients and controller_state.connected:
                protocol.send_controller_data()
        except Exception as e:
            logging.error(f"Error in broadcast task: {e}")
        await asyncio.sleep(0.01)

# --- SSL Generation ---
def generate_self_signed_cert():
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import datetime
    import os

    if os.path.exists("cert.pem") and os.path.exists("key.pem"):
        return

    logging.info("Generating self-signed SSL certificate...")
    
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
        critical=False,
    ).sign(key, hashes.SHA256())

    with open("key.pem", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    logging.info("Generated cert.pem and key.pem")

def get_local_ips():
    import socket
    ips = []
    try:
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)
        ips.append(host_ip)
    except:
        pass
    
    try:
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            for ip in result.stdout.strip().split():
                if ip not in ips and not ip.startswith('127.'):
                    ips.append(ip)
    except:
        pass
    
    if not ips:
        ips = ['127.0.0.1']
    return ips

async def main():
    generate_self_signed_cert()
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain('cert.pem', 'key.pem')

    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/style.css', handle_style)
    app.router.add_get('/script.js', handle_script)
    app.router.add_get('/ws', websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080, ssl_context=ssl_context)
    await site.start()
    
    local_ips = get_local_ips()
    logging.info("Web Server started!")
    logging.info("On your phone, open your browser and go to one of the following URLs:")
    for ip in local_ips:
        logging.info(f" -> https://{ip}:8080")

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: DSUServerProtocol(),
        local_addr=('0.0.0.0', 26760)
    )
    
    asyncio.create_task(dsu_broadcast_task(protocol))

    await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass