// State
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

// --- Navigation ---
function navigateTo(viewId) {
    // Update State
    state.currentView = viewId;

    // Update Sidebar
    document.querySelectorAll('.nav-links li').forEach(li => {
        li.classList.remove('active');
        // Simple check based on onclick attribute text
        if (li.getAttribute('onclick').includes(viewId)) {
            li.classList.add('active');
        }
    });

    // Update Views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(`${viewId}-view`).classList.add('active');
}

// --- Settings Handlers ---
function updateFpsDisplay(val) {
    state.fps = parseInt(val);
    document.getElementById('fpsValue').textContent = `${val} FPS`;
    // If streaming, restart interval with new FPS
    if (state.isStreaming) {
        restartStreamInterval(); // dynamically adjust without stopping camera
    }
}

function updateConfDisplay(val) {
    state.confidence = parseFloat(val);
    document.getElementById('confValue').textContent = val;
    // Note: To actually use this, backend needs to accept it. 
    // For now, we store it. Future refactor: Send conf with WS or POST.
}

function setRotation(deg) {
    state.rotation = deg;
    document.getElementById('currentRotation').textContent = `${deg}°`;
}

document.getElementById('flipHorizontal').addEventListener('change', (e) => {
    state.flipHorizontal = e.target.checked;
});

document.getElementById('resolutionSelect').addEventListener('change', (e) => {
    state.resolution = e.target.value;
    // Resolution change requires camera restart to take effect on hardware level
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
        // Optional: Auto restart? Let's just stop and let user start again to be safe.
        alert("Camera source changed. Please click Start to resume.");
    }
});


// --- Upload Logic ---
// Drag & Drop
const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('click', () => document.getElementById('fileInput').click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; });
dropZone.addEventListener('dragleave', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--border)'; });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border)';
    const files = e.dataTransfer.files;
    if (files.length) handleFile(files[0]);
});

document.getElementById('fileInput').addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    // Just visual feedback, user still needs to click Analyze
    // Or we could auto-analyze. Let's auto-fill the input but wait for click.
    // Actually, let's just trigger uploadImage immediately for smoother UX
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    document.getElementById('fileInput').files = dataTransfer.files;

    // Preview
    const reader = new FileReader();
    reader.onload = (e) => {
        // We could show a preview here if we wanted
    };
    reader.readAsDataURL(file);

    // Auto-click analyze? Let's stick to manual for now to match UI text
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

    // Clear previous results
    resultImage.removeAttribute('src');
    if (tableBody) tableBody.innerHTML = '';

    // Reset count UI (whatever exists)
    const countSpan =
        document.getElementById('uploadTotalTubesValue') ||
        document.getElementById('totalTubesValue');
    if (countSpan) countSpan.textContent = '0';

    const countText = document.getElementById('totalTubesText');
    if (countText) countText.innerHTML = 'Total Tubes: <span id="uploadTotalTubesValue">0</span>';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/predict', { method: 'POST', body: formData });
        if (!response.ok) throw new Error('Prediction failed');

        const data = await response.json();

        // ✅ annotated image
        resultImage.src = 'data:image/jpeg;base64,' + data.image;

        // ✅ tube count (prefer API value; fallback to detections length)
        const totalCount = (data.total_tubes ?? (data.detections ? data.detections.length : 0));

        // ✅ update span if present
        const spanEl =
            document.getElementById('uploadTotalTubesValue') ||
            document.getElementById('totalTubesValue');
        if (spanEl) spanEl.textContent = String(totalCount);

        // ✅ update full text line if present
        const textEl = document.getElementById('totalTubesText');
        if (textEl) textEl.innerHTML = `Total Tubes: <span id="uploadTotalTubesValue">${totalCount}</span>`;

        // ✅ table
        updateTable(data.detections || [], 'tableBody');

        // --- MPN UI update ---
        document.getElementById('mpnPattern').textContent = data.pattern || '-';
        document.getElementById('mpnValue').textContent = data.mpn || '-';

        if (data.ci_low && data.ci_high) {
            document.getElementById('mpnCI').textContent =
                `${data.ci_low} – ${data.ci_high}`;
        } else {
            document.getElementById('mpnCI').textContent = '-';
        }

        uploadResults.style.display = 'block';
    } catch (err) {
        alert("Error: " + err.message);
        console.error(err);
    } finally {
        btn.disabled = false;
        loading.style.display = 'none';
    }
}


// --- Stream Logic ---
let videoStream = null;
let ws = null;
let streamInterval = null;

async function startCamera() {
    try {
        const [width, height] = state.resolution.split('x').map(Number);

        // Connect WS first
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("WS Connected");
            if (state.cameraMode === 'client') {
                startClientStream(width, height);
            } else {
                startServerStream(width, height);
            }
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            document.getElementById('streamResult').src = 'data:image/jpeg;base64,' + data.image;
            updateTable(data.detections, 'streamTableBody');
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
                errorMsg += "\nSince you are connecting via HTTP, the browser blocks camera access.";
                errorMsg += `\n\nTo fix this on Chrome/Edge (Mobile & Desktop):`;
                errorMsg += `\n1. Go to: chrome://flags/#unsafely-treat-insecure-origin-as-secure`;
                errorMsg += `\n2. Enable it and add this origin: http://${window.location.host}`;
                errorMsg += `\n3. Restart the browser.`;
            }
            throw new Error(errorMsg);
        }

        // Default to no mirror for back camera
        state.flipHorizontal = false;
        if (document.getElementById('flipHorizontal')) {
            document.getElementById('flipHorizontal').checked = false;
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: width,
                height: height,
                facingMode: { ideal: "environment" }
            }
        });

        const video = document.getElementById('videoElement');
        video.srcObject = stream;

        await new Promise(resolve => video.onloadedmetadata = resolve);
        video.play();

        videoStream = stream;
        startStreamingCanvas(video, width, height);
    } catch (err) {
        console.error("Error accessing client camera:", err);
        let userMsg = "Could not access client camera.";
        if (err.message.includes("requires HTTPS") || err.name === 'NotAllowedError') {
            userMsg = err.message; // Use our detailed message if it's ours, or standard permission error
            if (err.name === 'NotAllowedError') {
                userMsg += "\n\nPlease allow camera permission in your browser settings.";
            }
        } else if (err.name === 'NotFoundError') {
            userMsg = "No camera found on this device.";
        }
        alert(userMsg);
        stopCamera();
    }
}

function startServerStream(width, height) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "start_server_stream",
            resolution: state.resolution
        }));
    }
}

function startStreamingCanvas(video, width, height) {
    const canvas = document.getElementById('canvasElement');
    const ctx = canvas.getContext('2d');

    // Adjust canvas size based on rotation
    if (state.rotation === 90 || state.rotation === 270) {
        canvas.width = height;
        canvas.height = width;
    } else {
        canvas.width = width;
        canvas.height = height;
    }

    const captureFrame = () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;

        ctx.save();
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Transforms
        // Move to center
        ctx.translate(canvas.width / 2, canvas.height / 2);

        // Rotate
        ctx.rotate(state.rotation * Math.PI / 180);

        // Flip (Scale)
        // If flipped, scale X by -1. 
        // Note: If rotated 90/270, the 'horizontal' axis is relative to the rotated image. 
        // Usually users expect flip relative to the screen axis. 
        // But for simplicity, let's flip the source image axis.
        if (state.flipHorizontal) {
            ctx.scale(-1, 1);
        }

        // Draw Image - need to handle width/height swapping for drawImage
        // If 90/270, the image is drawn perpendicular.
        // We are at center [0,0]. Image needs to be drawn centered.
        ctx.drawImage(video, -width / 2, -height / 2, width, height);

        ctx.restore();

        canvas.toBlob((blob) => {
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(blob);
        }, 'image/jpeg', 0.7); // 0.7 quality for speed
    };

    // Start Interval
    restartStreamInterval = () => {
        if (streamInterval) clearInterval(streamInterval);
        // Calculate interval from FPS
        const ms = 1000 / state.fps;
        streamInterval = setInterval(captureFrame, ms);
    };

    restartStreamInterval();
}

function stopCamera() {
    // Client Stop
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }

    // Server Stop
    if (state.cameraMode === 'server' && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "stop_server_stream" }));
    }

    // Common Stop
    if (ws) {
        ws.close();
        ws = null;
    }
    if (streamInterval) {
        clearInterval(streamInterval);
        streamInterval = null;
    }
    state.isStreaming = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
}

function updateTable(detections, tableId) {
    const tbody = document.getElementById(tableId);
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!detections || detections.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3" style="text-align:center; opacity:0.6;">
                No tubes detected
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Limit to top 10 to avoid UI lag on Raspberry Pi
    // Sort detections LEFT → RIGHT using bbox[0] (x1)
    detections
        .slice() // clone, do not mutate original
        .sort((a, b) => {
            if (Array.isArray(a.bbox) && Array.isArray(b.bbox)) {
                return a.bbox[0] - b.bbox[0]; // x1 comparison
            }
            return 0;
        })
        .slice(0, 9) // keep existing limit
        .forEach(d => {
            const value = d.label === 'Yellow_NoBubble' ? 1 : 0;

            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${d.label}</td>
                <td>${(d.confidence * 100).toFixed(1)}%</td>
                <td>${value}</td>
            `;
            tbody.appendChild(row);
        });
        console.log(detections.map(d => d.bbox[0]));

}

