# Mobile Wii Controller Emulator

This project allows you to use your mobile phone as a Wii Remote controller for the Dolphin Emulator on your PC. It hosts a web application that you access from your phone, which captures button presses and motion data (accelerometer/gyroscope) and sends it to a Python server on your PC via WebSockets. The Python server then translates this data and streams it to Dolphin using the Cemuhook DSU (DualShock UDP) protocol.

## Prerequisites

- Python 3.7+
- Dolphin Emulator (with alternate input source support)
- Both your PC and mobile phone must be on the same local Wi-Fi network.

## Installation

1. Clone or download this repository.
2. Open a terminal/command prompt and navigate to the project folder (`wii_controller`).
3. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

1. Start the server by running:
   ```bash
   python server.py
   ```
2. The server will automatically generate a self-signed SSL certificate (`cert.pem`, `key.pem`) to enable secure context, which is required by modern mobile browsers (especially iOS) to access device motion sensors.
3. The terminal will display the local IP address and port to connect to (e.g., `https://192.168.1.X:8080`).

## Connecting the Phone

1. Open your mobile phone's web browser (Safari on iOS, Chrome on Android).
2. Enter the URL displayed in the terminal (e.g., `https://192.168.1.X:8080`).
3. **Important:** Because it's a self-signed certificate, your browser will show a warning about the connection not being secure.
   - **Chrome:** Click "Advanced" -> "Proceed to 192.168.1.X (unsafe)".
   - **Safari:** Click "Show Details" -> "visit this website" -> "Visit Website".
4. Once the web app loads, tap the **"Start & Allow Sensors"** button. If prompted (especially on iOS 13+), grant permission to access Motion and Orientation.
5. The interface should change to a Wii Remote layout, and the status should say "Connected".

## Configuring Dolphin Emulator

1. Open Dolphin.
2. Go to **Controllers**.
3. Under "Alternate Input Sources", ensure **"Enable"** is checked and the server IP/Port matches (default is `127.0.0.1` and `26760`).
4. Click **Configure** next to "Emulated Wii Remote" (or "Emulated GameCube Controller").
5. In the Device dropdown, look for something like `DSUClient/0/YourPhoneMac` or simply `DSUClient/0/Controller`. Select it.
6. Map the buttons according to the mobile UI (A to A, B to B, D-Pad to D-Pad, etc.).
7. For motion controls, map the Accelerometer and Gyroscope axes under the **Motion Simulation** or **Extension** tabs, depending on your setup.
