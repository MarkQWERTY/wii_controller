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
    },
    pointer: {
        x: 128,
        y: 128
    }
};

let trackpadActive = false;
let startX = 0;
let startY = 0;
let pointerX = 128;
let pointerY = 128;

// Keep track of the touch ID handling the trackpad
let trackpadTouchId = null;

controller.addEventListener('touchstart', (e) => {
    // Only start tracking if we didn't touch a button directly
    if (e.target.tagName !== 'BUTTON' && !trackpadActive) {
        e.preventDefault();
        trackpadActive = true;
        // Use the first touch that started this event
        const touch = e.changedTouches[0];
        trackpadTouchId = touch.identifier;
        startX = touch.clientX;
        startY = touch.clientY;
    }
}, { passive: false });

controller.addEventListener('touchmove', (e) => {
    if (trackpadActive) {
        e.preventDefault();
        // Find our specific touch
        let touch = null;
        for (let i = 0; i < e.changedTouches.length; i++) {
            if (e.changedTouches[i].identifier === trackpadTouchId) {
                touch = e.changedTouches[i];
                break;
            }
        }

        if (touch) {
            const dx = touch.clientX - startX;
            const dy = touch.clientY - startY;

            // Sensitivity factor (adjust as needed)
            const sensitivity = 0.5;

            // Update virtual pointer position
            pointerX += dx * sensitivity;
            pointerY += dy * sensitivity;

            // Clamp to 0-255 range (8-bit value expected by DSU for analog stick)
            pointerX = Math.max(0, Math.min(255, pointerX));
            pointerY = Math.max(0, Math.min(255, pointerY));

            state.pointer.x = pointerX;
            state.pointer.y = pointerY;

            // Update start coordinates for next move event
            startX = touch.clientX;
            startY = touch.clientY;

            sendState();
        }
    }
}, { passive: false });

controller.addEventListener('touchend', (e) => {
    if (trackpadActive) {
        for (let i = 0; i < e.changedTouches.length; i++) {
            if (e.changedTouches[i].identifier === trackpadTouchId) {
                trackpadActive = false;
                trackpadTouchId = null;
                // Center pointer when released (optional, depending on desired behavior)
                // Let's keep it where it is, acting like a mouse pad
                break;
            }
        }
    }
}, { passive: false });

controller.addEventListener('touchcancel', (e) => {
    if (trackpadActive) {
        for (let i = 0; i < e.changedTouches.length; i++) {
            if (e.changedTouches[i].identifier === trackpadTouchId) {
                trackpadActive = false;
                trackpadTouchId = null;
                break;
            }
        }
    }
}, { passive: false });

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
        if (!state.buttons[btnName]) {
            state.buttons[btnName] = true;
            btn.classList.add('active');
            if (navigator.vibrate) {
                navigator.vibrate(15); // short vibration on press
            }
            sendState();
        }
    };

    const release = (e) => {
        e.preventDefault();
        if (state.buttons[btnName]) {
            state.buttons[btnName] = false;
            btn.classList.remove('active');
            sendState();
        }
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
    let motionGranted = false;

    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
        try {
            const permissionState = await DeviceMotionEvent.requestPermission();
            if (permissionState === 'granted') {
                motionGranted = true;
            } else {
                statusDiv.innerText = 'Permission denied for motion sensors.';
            }
        } catch (error) {
            console.error(error);
            statusDiv.innerText = 'Error requesting motion permission.';
        }
    } else {
        motionGranted = true;
    }

    if (motionGranted) {
        window.addEventListener('devicemotion', handleMotion);
    }

    connectWebSocket();
}

startBtn.addEventListener('click', requestPermissions);