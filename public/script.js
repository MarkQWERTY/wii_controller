const startScreen = document.getElementById('start-screen');
const controller = document.getElementById('controller');
const startBtn = document.getElementById('start-btn');
const statusDiv = document.getElementById('status');

let ws;
const state = {
    buttons: {
        up: false, down: false, left: false, right: false,
        A: false, B: false, minus: false, home: false, plus: false,
        '1': false, '2': false
    },
    motion: {
        accel: { x: 0, y: 0, z: 0 },
        gyro: { x: 0, y: 0, z: 0 },
        timestamp: 0
    }
};

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    statusDiv.innerText = `Connecting to ${wsUrl}...`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        statusDiv.innerText = 'Status: Connected';
        startScreen.style.display = 'none';
        controller.style.display = 'flex';
        if (navigator.wakeLock) {
            navigator.wakeLock.request('screen').catch(console.error);
        }
    };

    ws.onclose = () => {
        statusDiv.innerText = 'Status: Disconnected. Reconnecting...';
        setTimeout(connectWebSocket, 1000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        statusDiv.innerText = 'Status: Error';
    };
}

function sendState() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(state));
    }
}

setInterval(sendState, 20); // 50Hz

document.querySelectorAll('button[data-btn]').forEach(btn => {
    const btnName = btn.getAttribute('data-btn');

    const press = (e) => {
        e.preventDefault();
        state.buttons[btnName] = true;
        btn.classList.add('active');
        sendState();
    };

    const release = (e) => {
        e.preventDefault();
        state.buttons[btnName] = false;
        btn.classList.remove('active');
        sendState();
    };

    btn.addEventListener('touchstart', press, { passive: false });
    btn.addEventListener('touchend', release, { passive: false });
    btn.addEventListener('mousedown', press);
    btn.addEventListener('mouseup', release);
    btn.addEventListener('mouseleave', release);
});

function handleMotion(event) {
    state.motion.timestamp = Date.now();

    if (event.accelerationIncludingGravity) {
        state.motion.accel.x = event.accelerationIncludingGravity.x / 9.81 || 0;
        state.motion.accel.y = event.accelerationIncludingGravity.y / 9.81 || 0;
        state.motion.accel.z = event.accelerationIncludingGravity.z / 9.81 || 0;
    }

    if (event.rotationRate) {
        state.motion.gyro.x = event.rotationRate.beta || 0;
        state.motion.gyro.y = event.rotationRate.gamma || 0;
        state.motion.gyro.z = event.rotationRate.alpha || 0;
    }
}

async function requestPermissions() {
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
        try {
            const permissionState = await DeviceMotionEvent.requestPermission();
            if (permissionState === 'granted') {
                window.addEventListener('devicemotion', handleMotion);
                connectWebSocket();
            } else {
                statusDiv.innerText = 'Permission denied for motion sensors.';
                connectWebSocket();
            }
        } catch (error) {
            console.error(error);
            statusDiv.innerText = 'Error requesting permission.';
            connectWebSocket();
        }
    } else {
        window.addEventListener('devicemotion', handleMotion);
        connectWebSocket();
    }
}

startBtn.addEventListener('click', requestPermissions);