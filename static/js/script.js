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

    document.querySelectorAll('.nav-links li').forEach(li => {
        li.classList.toggle('active', li.dataset.view === viewId);
    });

    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(`${viewId}-view`).classList.add('active');

    // Auto-load history fresh every time the view is opened
    if (viewId === 'history') {
        historyState.offset = 0;
        historyState.total  = 0;
        historyState.loaded = false;
        document.getElementById('historyList').innerHTML = '';
        loadHistory();
    }

    // Render guideline table on first visit (no-op on subsequent visits)
    if (viewId === 'guideline') {
        renderGuidelineTable();
    }
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
        updateMpnDisplay(data, 'mpnPattern', 'mpnValue', 'mpnCI', 'mpnRisk', 'mpnRiskItem');

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
            updateMpnDisplay(data, 'streamMpnPattern', 'streamMpnValue', 'streamMpnCI', 'streamMpnRisk', 'streamMpnRiskItem');
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
 * riskItemId is the ID of the parent .summary-item wrapper to colour it.
 */
function updateMpnDisplay(data, patternId, valueId, ciId, riskValueId = null, riskItemId = null) {
    const patternEl = document.getElementById(patternId);
    const valueEl   = document.getElementById(valueId);
    const ciEl      = document.getElementById(ciId);

    if (patternEl) patternEl.textContent = data.pattern || '–';
    if (valueEl)   valueEl.textContent   = data.mpn     || '–';
    if (ciEl) {
        ciEl.textContent = (data.ci_low && data.ci_high)
            ? `${data.ci_low} – ${data.ci_high}`
            : '–';
    }

    // Risk badge
    if (riskValueId) {
        const risk      = _mpnRisk(data.mpn);
        const label     = _riskLabel[risk] || '–';
        const riskValEl = document.getElementById(riskValueId);
        const riskItem  = riskItemId ? document.getElementById(riskItemId) : null;

        if (riskValEl) {
            riskValEl.textContent = data.mpn ? label : '–';
        }
        if (riskItem) {
            // Remove previous risk classes then apply current
            riskItem.classList.remove('risk-safe', 'risk-low', 'risk-medium', 'risk-high');
            if (data.mpn) riskItem.classList.add(`risk-${risk}`);
        }
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


// ---------------------------------------------------------------------------
// History — state
// ---------------------------------------------------------------------------

const historyState = {
    offset:  0,      // how many records have been loaded so far
    total:   0,      // total records in DB (from API response)
    limit:   20,     // records per page
    loading: false,  // prevent concurrent fetches
    loaded:  false,  // has the first load happened?
};


// ---------------------------------------------------------------------------
// History — load / load more
// ---------------------------------------------------------------------------

async function loadHistory() {
    if (historyState.loading) return;
    historyState.loading = true;

    const loadingEl  = document.getElementById('historyLoading');
    const emptyEl    = document.getElementById('historyEmpty');
    const listEl     = document.getElementById('historyList');
    const loadMoreEl = document.getElementById('historyLoadMore');
    const subtitleEl = document.getElementById('historySubtitle');

    // First load — show spinner, hide everything else
    if (historyState.offset === 0) {
        loadingEl.style.display  = 'block';
        emptyEl.style.display    = 'none';
        loadMoreEl.style.display = 'none';
    }

    try {
        const res = await fetch(
            `/history?limit=${historyState.limit}&offset=${historyState.offset}`
        );
        if (!res.ok) throw new Error(`Server error: ${res.status}`);

        const data = await res.json();

        historyState.total   = data.total;
        historyState.offset += data.records.length;
        historyState.loaded  = true;

        // Update subtitle
        if (subtitleEl) {
            subtitleEl.textContent = `${data.total} record${data.total !== 1 ? 's' : ''}`;
        }

        // Render cards
        data.records.forEach(rec => {
            listEl.appendChild(renderHistoryCard(rec));
        });

        // Empty state
        if (data.total === 0) {
            emptyEl.style.display = 'flex';
        }

        // Load More button — show only if more records exist
        const hasMore = historyState.offset < historyState.total;
        loadMoreEl.style.display = hasMore ? 'flex' : 'none';

    } catch (err) {
        console.error('loadHistory error:', err);
        if (subtitleEl) subtitleEl.textContent = 'Failed to load history.';
    } finally {
        historyState.loading    = false;
        loadingEl.style.display = 'none';
    }
}


function loadMoreHistory() {
    loadHistory();
}


// ---------------------------------------------------------------------------
// History — render one card
// ---------------------------------------------------------------------------

function renderHistoryCard(rec) {
    const card = document.createElement('div');
    card.className = 'history-card';
    card.dataset.id = rec.id;

    // Open detail modal when clicking anywhere on the card
    card.addEventListener('click', () => openHistoryModal(rec));

    // ---- Thumbnail ----
    const thumbHtml = rec.image_url
        ? `<div class="history-thumb">
               <img src="${rec.image_url}" alt="Result" loading="lazy"
                    onload="this.classList.add('loaded')"
                    onerror="this.closest('.history-thumb').style.display='none'">
               <span class="history-thumb-badge">${formatTimestamp(rec.created_at)}</span>
           </div>`
        : '';

    // ---- MPN result row ----
    const _cardRisk      = _mpnRisk(rec.mpn);
    const _cardRiskLabel = rec.pattern ? _riskLabel[_cardRisk] : null;
    const mpnHtml = rec.pattern
        ? `<div class="history-mpn-row">
               <span class="history-pattern">${rec.pattern}</span>
               <div style="display:flex;align-items:center;gap:0.4rem;">
                   <span class="history-mpn-value">${rec.mpn ?? '–'}</span>
                   <span class="history-mpn-unit">MPN/g</span>
               </div>
           </div>
           <div class="history-mpn-meta">
               <span class="history-risk-badge risk-${_cardRisk}">${_cardRiskLabel}</span>
               <span class="history-ci">CI: ${(rec.ci_low && rec.ci_high) ? `${rec.ci_low} – ${rec.ci_high}` : '–'}</span>
           </div>`
        : `<div class="history-mpn-none">
               MPN not available
               <span class="history-tubes-count">(${rec.total_tubes} tube${rec.total_tubes !== 1 ? 's' : ''} detected)</span>
           </div>`;

    // ---- Tube dot grid ----
    const tubesHtml = renderTubeDots(rec.tubes || []);

    // ---- Filename (truncated) ----
    const fname = rec.filename || 'unknown';

    card.innerHTML = `
        ${thumbHtml}
        <div class="history-body">
            ${mpnHtml}
            ${tubesHtml}
        </div>
        <div class="history-footer">
            <span class="history-filename">
                <i class="fa-solid fa-file-image"></i>${fname}
            </span>
            <button class="btn-delete" onclick="event.stopPropagation(); deleteHistoryRecord(${rec.id}, this)">
                <i class="fa-solid fa-trash-can"></i> Delete
            </button>
        </div>
    `;

    return card;
}


// ---------------------------------------------------------------------------
// History — tube dot grid
// ---------------------------------------------------------------------------

function renderTubeDots(tubes) {
    if (!tubes || tubes.length === 0) return '';

    // Pad to 9 if needed
    const t = [...tubes];
    while (t.length < 9) t.push(0);

    // Split into 3 groups of 3
    const groups = [t.slice(0, 3), t.slice(3, 6), t.slice(6, 9)];
    const labels = ['0.1g', '0.01g', '0.001g'];

    const groupsHtml = groups.map((group, gi) => {
        const dots = group.map(val =>
            `<span class="tube-dot ${val === 1 ? 'positive' : 'negative'}"
                   title="${labels[gi]}: ${val === 1 ? 'positive' : 'negative'}">
                ${val}
            </span>`
        ).join('');
        return `<div class="tube-group">${dots}</div>`;
    }).join('');

    return `<div class="history-tubes">${groupsHtml}</div>`;
}


// ---------------------------------------------------------------------------
// History — delete
// ---------------------------------------------------------------------------

async function deleteHistoryRecord(id, btnEl) {
    if (!confirm('Delete this record and its image?')) return;

    // Disable button immediately to prevent double-click
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

    try {
        const res = await fetch(`/history/${id}`, { method: 'DELETE' });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Server error: ${res.status}`);
        }

        // Remove card from DOM with a fade-out
        const card = document.querySelector(`.history-card[data-id="${id}"]`);
        if (card) {
            card.style.transition = 'opacity 0.25s, transform 0.25s';
            card.style.opacity    = '0';
            card.style.transform  = 'scale(0.97)';
            setTimeout(() => card.remove(), 260);
        }

        // Update counters
        historyState.total   = Math.max(0, historyState.total - 1);
        historyState.offset  = Math.max(0, historyState.offset - 1);

        const subtitleEl = document.getElementById('historySubtitle');
        if (subtitleEl) {
            subtitleEl.textContent =
                `${historyState.total} record${historyState.total !== 1 ? 's' : ''}`;
        }

        // Show empty state if nothing left
        if (historyState.total === 0) {
            document.getElementById('historyEmpty').style.display    = 'flex';
            document.getElementById('historyLoadMore').style.display = 'none';
        }

    } catch (err) {
        console.error('deleteHistoryRecord error:', err);
        alert('Could not delete record: ' + err.message);
        // Restore button on failure
        btnEl.disabled = false;
        btnEl.innerHTML = '<i class="fa-solid fa-trash-can"></i> Delete';
    }
}


// ---------------------------------------------------------------------------
// History — export CSV
// ---------------------------------------------------------------------------

function exportHistory() {
    // Trigger browser download by navigating to the endpoint.
    // The server responds with Content-Disposition: attachment so the
    // browser saves it rather than navigating away.
    window.location.href = '/history/export';
}


// ---------------------------------------------------------------------------
// History — helpers
// ---------------------------------------------------------------------------

/**
 * Format a SQLite DATETIME string ("2026-02-24 14:30:22")
 * into a readable short form ("24 Feb, 14:30").
 */
function formatTimestamp(ts) {
    if (!ts) return '';
    try {
        // SQLite stores DATETIME as "YYYY-MM-DD HH:MM:SS"
        // Replace space with T so Date() parses it correctly across browsers
        const d = new Date(ts.replace(' ', 'T'));
        const day  = d.getDate();
        const mon  = d.toLocaleString('default', { month: 'short' });
        const time = d.toTimeString().slice(0, 5);
        return `${day} ${mon}, ${time}`;
    } catch {
        return ts;
    }
}


// ---------------------------------------------------------------------------
// History Detail Modal
// ---------------------------------------------------------------------------

// Holds the record currently shown in the modal
let _modalRecord = null;

/**
 * Open the detail modal for a given history record.
 * Called from renderHistoryCard() via onclick on the card element.
 */
function openHistoryModal(rec) {
    _modalRecord = rec;

    const overlay = document.getElementById('historyModal');

    // ---- Header ----
    document.getElementById('modalPattern').textContent =
        rec.pattern || 'No MPN';
    document.getElementById('modalTimestamp').textContent =
        formatTimestamp(rec.created_at);

    // ---- Image ----
    const img = document.getElementById('modalImage');
    if (rec.image_url) {
        img.src = rec.image_url;
        img.style.display = 'block';
        img.closest('.modal-image-wrap').style.display = 'flex';
    } else {
        img.src = '';
        img.closest('.modal-image-wrap').style.display = 'none';
    }

    // ---- MPN stats ----
    document.getElementById('modalMpn').textContent       = rec.mpn    || '–';
    document.getElementById('modalTubeCount').textContent = rec.total_tubes ?? '–';
    document.getElementById('modalFilename').textContent  = rec.filename || 'unknown';

    const ci = (rec.ci_low && rec.ci_high)
        ? `${rec.ci_low} – ${rec.ci_high}`
        : '–';
    document.getElementById('modalCI').textContent = ci;

    // ---- Risk ----
    const _risk      = _mpnRisk(rec.mpn);
    const _riskLbl   = _riskLabel[_risk];

    // Header badge
    const riskBadge = document.getElementById('modalRiskBadge');
    if (riskBadge) {
        riskBadge.textContent = rec.mpn ? _riskLbl : '';
        riskBadge.className   = rec.mpn
            ? `modal-risk-badge risk-pill ${_risk}`
            : 'modal-risk-badge';
    }

    // Stat cell
    const riskStat  = document.getElementById('modalRiskStat');
    const riskValue = document.getElementById('modalRiskValue');
    if (riskValue) riskValue.textContent = rec.mpn ? _riskLbl : '–';
    if (riskStat) {
        riskStat.classList.remove('risk-safe', 'risk-low', 'risk-medium', 'risk-high');
        if (rec.mpn) riskStat.classList.add(`risk-${_risk}`);
    }

    // ---- Tube dots (reuse renderTubeDots) ----
    document.getElementById('modalTubes').innerHTML =
        renderTubeDots(rec.tubes || []);

    // ---- Detections table ----
    _renderModalTable(rec.detections || []);

    // ---- Open with animation ----
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden'; // prevent background scroll

    // Trap focus inside modal for accessibility
    overlay.querySelector('.modal-close').focus();
}


/**
 * Close the modal.
 * Accepts an optional MouseEvent — if the click was inside .modal-box,
 * do nothing (only close when clicking the dark overlay behind it).
 */
function closeHistoryModal(event) {
    if (event && event.target !== document.getElementById('historyModal')) {
        return;
    }
    const overlay = document.getElementById('historyModal');
    overlay.classList.remove('open');
    document.body.style.overflow = ''; // restore scroll
    _modalRecord = null;
}


// Close on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeHistoryModal();
});


/**
 * Populate the detections table inside the modal.
 */
function _renderModalTable(detections) {
    const tbody = document.getElementById('modalTableBody');
    tbody.innerHTML = '';

    if (!detections || detections.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align:center; opacity:0.5; padding:1rem;">
                    No detections recorded
                </td>
            </tr>`;
        return;
    }

    // Sort left → right by bbox x1 (same as updateTable)
    const sorted = detections
        .slice()
        .sort((a, b) => {
            if (Array.isArray(a.bbox) && Array.isArray(b.bbox)) {
                return a.bbox[0] - b.bbox[0];
            }
            return 0;
        });

    sorted.forEach((d, i) => {
        const value = d.label === 'Yellow_NoBubble' ? 1 : 0;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${i + 1}</td>
            <td>${d.label}</td>
            <td>${(d.confidence * 100).toFixed(1)}%</td>
            <td>${value}</td>
        `;
        tbody.appendChild(tr);
    });
}


// ---------------------------------------------------------------------------
// MPN Guideline
// ---------------------------------------------------------------------------

const MPN_TABLE = [
    { pattern: "P000", mpn: "<3.0", ci_low: "–",    ci_high: "9.5"  },
    { pattern: "P001", mpn: "3",    ci_low: "0.15",  ci_high: "9.6"  },
    { pattern: "P010", mpn: "3",    ci_low: "0.15",  ci_high: "11"   },
    { pattern: "P011", mpn: "6.1",  ci_low: "1.2",   ci_high: "18"   },
    { pattern: "P020", mpn: "6.2",  ci_low: "1.2",   ci_high: "18"   },
    { pattern: "P030", mpn: "9.4",  ci_low: "3.6",   ci_high: "38"   },
    { pattern: "P100", mpn: "3.6",  ci_low: "0.17",  ci_high: "18"   },
    { pattern: "P101", mpn: "7.2",  ci_low: "1.3",   ci_high: "18"   },
    { pattern: "P102", mpn: "11",   ci_low: "3.6",   ci_high: "38"   },
    { pattern: "P110", mpn: "7.4",  ci_low: "1.3",   ci_high: "20"   },
    { pattern: "P111", mpn: "11",   ci_low: "3.6",   ci_high: "38"   },
    { pattern: "P120", mpn: "11",   ci_low: "3.6",   ci_high: "42"   },
    { pattern: "P121", mpn: "15",   ci_low: "4.5",   ci_high: "42"   },
    { pattern: "P130", mpn: "16",   ci_low: "4.5",   ci_high: "42"   },
    { pattern: "P200", mpn: "9.2",  ci_low: "1.4",   ci_high: "38"   },
    { pattern: "P201", mpn: "14",   ci_low: "3.6",   ci_high: "42"   },
    { pattern: "P202", mpn: "20",   ci_low: "4.5",   ci_high: "42"   },
    { pattern: "P210", mpn: "15",   ci_low: "3.7",   ci_high: "42"   },
    { pattern: "P211", mpn: "20",   ci_low: "4.5",   ci_high: "42"   },
    { pattern: "P212", mpn: "27",   ci_low: "8.7",   ci_high: "94"   },
    { pattern: "P220", mpn: "21",   ci_low: "4.5",   ci_high: "42"   },
    { pattern: "P221", mpn: "28",   ci_low: "8.7",   ci_high: "94"   },
    { pattern: "P222", mpn: "35",   ci_low: "8.7",   ci_high: "94"   },
    { pattern: "P230", mpn: "29",   ci_low: "8.7",   ci_high: "94"   },
    { pattern: "P231", mpn: "36",   ci_low: "8.7",   ci_high: "94"   },
    { pattern: "P300", mpn: "23",   ci_low: "4.6",   ci_high: "94"   },
    { pattern: "P301", mpn: "38",   ci_low: "8.7",   ci_high: "110"  },
    { pattern: "P302", mpn: "64",   ci_low: "17",    ci_high: "180"  },
    { pattern: "P310", mpn: "43",   ci_low: "9",     ci_high: "180"  },
    { pattern: "P311", mpn: "75",   ci_low: "17",    ci_high: "200"  },
    { pattern: "P312", mpn: "120",  ci_low: "37",    ci_high: "420"  },
    { pattern: "P313", mpn: "160",  ci_low: "40",    ci_high: "420"  },
    { pattern: "P320", mpn: "93",   ci_low: "18",    ci_high: "420"  },
    { pattern: "P321", mpn: "150",  ci_low: "37",    ci_high: "420"  },
    { pattern: "P322", mpn: "210",  ci_low: "40",    ci_high: "430"  },
    { pattern: "P323", mpn: "290",  ci_low: "90",    ci_high: "1000" },
    { pattern: "P330", mpn: "240",  ci_low: "42",    ci_high: "1000" },
    { pattern: "P331", mpn: "460",  ci_low: "90",    ci_high: "2000" },
    { pattern: "P332", mpn: "1100", ci_low: "180",   ci_high: "4100" },
    { pattern: "P333", mpn: ">1100",ci_low: "420",   ci_high: "–"    },
];

/**
 * Classify a numeric MPN value into a risk tier.
 * Returns one of: "safe" | "low" | "medium" | "high"
 */
function _mpnRisk(mpnStr) {
    if (!mpnStr || mpnStr === "–") return "safe";
    if (mpnStr.startsWith("<"))   return "safe";
    if (mpnStr.startsWith(">"))   return "high";
    const v = parseFloat(mpnStr);
    if (isNaN(v))  return "safe";
    if (v < 3)     return "safe";
    if (v <= 20)   return "low";
    if (v <= 110)  return "medium";
    return "high";
}

const _riskLabel = { safe: "Safe", low: "Low", medium: "Moderate", high: "High" };

/**
 * Build the xyz label from pattern string.
 * "P210" → "2-1-0"
 */
function _patternToXyz(pattern) {
    const digits = pattern.replace("P", "");
    return digits.split("").join("-");
}

/**
 * Render the full reference table into #guideTableBody.
 * Called once when the guideline view is first opened.
 */
function renderGuidelineTable() {
    const tbody = document.getElementById("guideTableBody");
    if (!tbody || tbody.dataset.rendered === "1") return; // render once only
    tbody.dataset.rendered = "1";

    MPN_TABLE.forEach(row => {
        const risk      = _mpnRisk(row.mpn);
        const riskLabel = _riskLabel[risk];
        const tr        = document.createElement("tr");
        tr.className    = `risk-${risk}`;
        tr.innerHTML    = `
            <td><span style="font-family:var(--font-mono);font-weight:600;">${row.pattern}</span></td>
            <td style="font-family:var(--font-mono);color:var(--text-muted);">${_patternToXyz(row.pattern)}</td>
            <td style="font-family:var(--font-mono);font-weight:600;">${row.mpn}</td>
            <td style="font-family:var(--font-mono);color:var(--text-muted);">${row.ci_low}</td>
            <td style="font-family:var(--font-mono);color:var(--text-muted);">${row.ci_high}</td>
            <td><span class="risk-pill ${risk}">${riskLabel}</span></td>
        `;
        tbody.appendChild(tr);
    });
}