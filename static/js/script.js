// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let state = {
    currentView: 'home',
    fps: 5,
    resolution: '640x480',
    rotation: 0,
    flipHorizontal: false,
    confidence: 0.25,
    isStreaming: false,
    cameraMode: 'client' // 'client' | 'server'
};


// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function navigateTo(viewId) {
    state.currentView = viewId;

    // FIX: Use data-view attribute instead of parsing onclick string,
    // which was fragile and would break if the function call was ever reformatted.
    document.querySelectorAll('.nav-links li').forEach(li => {
        li.classList.toggle('active', li.dataset.view === viewId);
    });

    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(`${viewId}-view`).classList.add('active');
}


// ---------------------------------------------------------------------------
// Settings handlers
// ---------------------------------------------------------------------------

function updateFpsDisplay(val) {
    state.fps = parseInt(val);
    document.getElementById('fpsValue').textContent = `${val} FPS`;
    if (state.isStreaming) {
        restartStreamInterval();
    }
}

function updateConfDisplay(val) {
    state.confidence = parseFloat(val);
    document.getElementById('confValue').textContent = val;

    // FIX: send updated confidence to the server in real time so the backend
    // actually uses it — previously state.confidence was stored but never sent.
    if (state.isStreaming && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "set_conf", value: state.confidence }));
    }
}

function setRotation(deg) {
    state.rotation = deg;
    document.getElementById('currentRotation').textContent = `${deg}°`;

    // FIX: when rotation changes mid-stream, the canvas dimensions need to be
    // swapped (portrait ↔ landscape) and the interval restarted. Previously the
    // old canvas size was kept, causing the image to be drawn incorrectly.
    if (state.isStreaming && videoStream) {
        const [width, height] = state.resolution.split('x').map(Number);
        const canvas = document.getElementById('canvasElement');
        if (deg === 90 || deg === 270) {
            canvas.width = height;
            canvas.height = width;
        } else {
            canvas.width = width;
            canvas.height = height;
        }
        restartStreamInterval();
    }
}

document.getElementById('flipHorizontal').addEventListener('change', (e) => {
    state.flipHorizontal = e.target.checked;
});

document.getElementById('resolutionSelect').addEventListener('change', (e) => {
    state.resolution = e.target.value;
    if (state.isStreaming) {
        alert("Restarting camera to apply resolution change...");
        stopCamera();
        setTimeout(startCamera, 500);
    }
});

document.getElementById('cameraSourceSelect').addEventListener('change', (e) => {
    state.cameraMode = e.target.value;
    if (state.isStreaming) {
        stopCamera();
        alert("Camera source changed. Please click Start to resume.");
    }
});


// ---------------------------------------------------------------------------
// Upload logic
// ---------------------------------------------------------------------------

const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('click', () => document.getElementById('fileInput').click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; });
dropZone.addEventListener('dragleave', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--border)'; });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border)';
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});

document.getElementById('fileInput').addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    document.getElementById('fileInput').files = dataTransfer.files;
    dropZone.querySelector('p').textContent = `Selected: ${file.name}`;
}

async function uploadImage() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return alert("Please select an image first.");

    const btn = document.getElementById('predictBtn');
    const loading = document.getElementById('loading');
    const uploadResults = document.getElementById('uploadResults');
    const resultImage = document.getElementById('resultImage');
    const tableBody = document.getElementById('tableBody');

    btn.disabled = true;
    loading.style.display = 'block';
    uploadResults.style.display = 'none';

    resultImage.removeAttribute('src');
    if (tableBody) tableBody.innerHTML = '';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('conf', state.confidence); // FIX: send confidence so backend uses it

    try {
        const response = await fetch('/predict', { method: 'POST', body: formData });
        if (!response.ok) throw new Error(`Server error: ${response.status}`);

        const data = await response.json();

        resultImage.src = 'data:image/jpeg;base64,' + data.image;

        const totalCount = data.total_tubes ?? (data.detections ? data.detections.length : 0);
        const textEl = document.getElementById('totalTubesText');
        if (textEl) textEl.innerHTML = `Total Tubes: <span>${totalCount}</span>`;

        updateTable(data.detections || [], 'tableBody');
        updateMpnDisplay(data, 'mpnPattern', 'mpnValue', 'mpnCI');

        uploadResults.style.display = 'block';
    } catch (err) {
        alert("Error: " + err.message);
        console.error(err);
    } finally {
        btn.disabled = false;
        loading.style.display = 'none';
    }
}


// ---------------------------------------------------------------------------
// Stream logic
// ---------------------------------------------------------------------------

let videoStream = null;
let ws = null;
let streamInterval = null; // FIX: declared at module scope (was implicit global)

// FIX: declared at module scope so updateFpsDisplay() can safely call it
// before streaming starts without throwing a ReferenceError.
function restartStreamInterval() {
    if (streamInterval) clearInterval(streamInterval);
    if (!state.isStreaming) return; // guard: don't start if not streaming
    const ms = 1000 / state.fps;
    streamInterval = setInterval(_captureAndSend, ms);
}

// Holds the active canvas capture function — set by startStreamingCanvas()
let _captureAndSend = () => {};

async function startCamera() {
    try {
        const [width, height] = state.resolution.split('x').map(Number);

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("WS Connected");

            // Send initial confidence so the session starts with the correct value
            ws.send(JSON.stringify({ action: "set_conf", value: state.confidence }));

            if (state.cameraMode === 'client') {
                startClientStream(width, height);
            } else {
                startServerStream(width, height);
            }
        };

        ws.onmessage = (event) => {
            // FIX: wrap JSON.parse in try/catch — a malformed message previously
            // threw an uncaught exception that silently killed the onmessage handler.
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (err) {
                console.error("WS: failed to parse message:", err);
                return;
            }

            document.getElementById('streamResult').src = 'data:image/jpeg;base64,' + data.image;
            updateTable(data.detections || [], 'streamTableBody');

            // FIX: MPN results were sent by the server but never shown in the
            // stream view — they are now displayed using the same helper used
            // by the upload view.
            updateMpnDisplay(data, 'streamMpnPattern', 'streamMpnValue', 'streamMpnCI');
        };

        ws.onclose = () => console.log("WS Closed");
        ws.onerror = (err) => console.error("WS Error", err);

        state.isStreaming = true;
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        document.getElementById('streamResult').style.display = 'block';

    } catch (err) {
        console.error("Error starting camera:", err);
        alert("Could not start camera. Check permissions/HTTPS.");
    }
}

async function startClientStream(width, height) {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            let errorMsg = "Camera API not available.";
            if (!window.isSecureContext) {
                errorMsg += "\n\nCamera access requires HTTPS (Secure Context).";
                errorMsg += "\n\nTo fix this on Chrome/Edge:\n";
                errorMsg += `1. Go to: chrome://flags/#unsafely-treat-insecure-origin-as-secure\n`;
                errorMsg += `2. Enable it and add: http://${window.location.host}\n`;
                errorMsg += "3. Restart the browser.";
            }
            throw new Error(errorMsg);
        }

        state.flipHorizontal = false;
        const flipEl = document.getElementById('flipHorizontal');
        if (flipEl) flipEl.checked = false;

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width, height, facingMode: { ideal: "environment" } }
        });

        const video = document.getElementById('videoElement');
        video.srcObject = stream;
        await new Promise(resolve => video.onloadedmetadata = resolve);
        video.play();

        videoStream = stream;
        startStreamingCanvas(video, width, height);

    } catch (err) {
        console.error("Error accessing client camera:", err);
        let userMsg = "Could not access client camera.\n" + err.message;
        if (err.name === 'NotAllowedError') userMsg += "\n\nPlease allow camera permission in your browser settings.";
        if (err.name === 'NotFoundError') userMsg = "No camera found on this device.";
        alert(userMsg);
        stopCamera();
    }
}

function startServerStream() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "start_server_stream", resolution: state.resolution }));
    }
}

function startStreamingCanvas(video, width, height) {
    const canvas = document.getElementById('canvasElement');
    const ctx = canvas.getContext('2d');

    if (state.rotation === 90 || state.rotation === 270) {
        canvas.width = height;
        canvas.height = width;
    } else {
        canvas.width = width;
        canvas.height = height;
    }

    // FIX: assign to module-scoped _captureAndSend so restartStreamInterval()
    // can call the right function regardless of when it's invoked.
    _captureAndSend = () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;

        ctx.save();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(state.rotation * Math.PI / 180);
        if (state.flipHorizontal) ctx.scale(-1, 1);
        ctx.drawImage(video, -width / 2, -height / 2, width, height);
        ctx.restore();

        canvas.toBlob((blob) => {
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(blob);
        }, 'image/jpeg', 0.7);
    };

    restartStreamInterval();
}

function stopCamera() {
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }

    if (state.cameraMode === 'server' && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "stop_server_stream" }));
    }

    if (ws) { ws.close(); ws = null; }
    if (streamInterval) { clearInterval(streamInterval); streamInterval = null; }

    state.isStreaming = false;
    _captureAndSend = () => {}; // reset so a stale interval can't fire
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
}


// ---------------------------------------------------------------------------
// Shared UI helpers
// ---------------------------------------------------------------------------

/**
 * Populate an MPN summary block with values from a server response.
 * Works for both the upload view and stream view by accepting element IDs.
 */
function updateMpnDisplay(data, patternId, valueId, ciId) {
    const patternEl = document.getElementById(patternId);
    const valueEl = document.getElementById(valueId);
    const ciEl = document.getElementById(ciId);

    if (patternEl) patternEl.textContent = data.pattern || '-';
    if (valueEl) valueEl.textContent = data.mpn || '-';
    if (ciEl) {
        ciEl.textContent = (data.ci_low && data.ci_high)
            ? `${data.ci_low} – ${data.ci_high}`
            : '-';
    }
}

function updateTable(detections, tableId) {
    const tbody = document.getElementById(tableId);
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!detections || detections.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `<td colspan="3" style="text-align:center; opacity:0.6;">No tubes detected</td>`;
        tbody.appendChild(row);
        return;
    }

    detections
        .slice()
        .sort((a, b) => {
            if (Array.isArray(a.bbox) && Array.isArray(b.bbox)) return a.bbox[0] - b.bbox[0];
            return 0;
        })
        .slice(0, 9)
        .forEach(d => {
            const value = d.label === 'Yellow_NoBubble' ? 1 : 0;
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${d.label}</td>
                <td>${(d.confidence * 100).toFixed(1)}%</td>
                <td>${value}</td>
            `;
            tbody.appendChild(row);
            // FIX: debug console.log removed (was logging bbox x1 values on every frame)
        });
}