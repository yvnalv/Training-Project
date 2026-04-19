# VialVision — Changelog

All changes are listed newest first.
Each entry includes the date, what changed, the problem it solved, and how it was solved.

---

## [2026-04-19] RPi autostart, settings persistence, camera fixes, network IP
**Branch:** `fixing-upload-button`
**Date:** 2026-04-19

---

### Platform-aware settings persistence (database)

**Problem:**
UI settings (camera mode, FPS, resolution, confidence, flip) were lost on every page reload.
Additionally, when the default camera was set to "server" mode, visiting the page on a Windows machine
caused the `/capture` endpoint to try opening a local webcam and fail with:
```
RuntimeError: Could not open camera source: 0
```

**Fix:**
- Added `settings` table to SQLite database (key-value store):
  ```sql
  CREATE TABLE settings (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```
- Added `GET /settings` endpoint: returns saved settings + platform info (`is_raspi`, `has_picamera2`, `default_camera_mode`) + device network IP
- Added `PUT /settings` endpoint: upserts up to 5 allowed keys (`cameraMode`, `fps`, `resolution`, `confidence`, `flipHorizontal`)
- Frontend calls `loadSettings()` on page load — applies saved values and uses `default_camera_mode` from server as the platform-aware default (server on Pi, client on Windows)
- All settings change handlers now call a debounced `saveSettings()` (600 ms delay)

**Files changed:**
- `app/db/database.py` — added `settings` table and `CREATE TABLE` call in `init_db()`
- `app/db/queries.py` — added `get_all_settings()` and `set_settings(data)` functions
- `app/api.py` — added `GET /settings`, `PUT /settings`; added `_get_network_ip()`, `_platform_info()` helpers; added imports: `importlib`, `sys`, `socket`
- `static/js/script.js` — added `loadSettings()`, `saveSettings()` with debounce; wired all settings handlers; called `loadSettings()` on page load

---

### Raspberry Pi camera — color fix (BGR/RGB pipeline)

**Problem:**
Images captured by the Pi camera via the `/capture` endpoint appeared blue (red and blue channels swapped).

**Root Cause:**
Two compounding issues:
1. `BGR888` format in picamera2 delivers data in RGB byte order on some Pi hardware and libcamera versions (known libcamera quirk) — the format name is misleading
2. `cv2.imencode` on ARM does not perform a BGR→RGB swap before libjpeg, so the JPEG was encoded with swapped channels regardless of the format string

**Fix:**
- Changed picamera2 init to always request `RGB888` format (universally reliable)
- Changed `_capture_loop` from `capture_array()` to `capture_image("main")` which returns a PIL Image with guaranteed RGB channel order; added `.convert("RGB")` guard for rare RGBA output; then converts RGB→BGR with `cv2.cvtColor` so the in-memory frame buffer stays in OpenCV BGR convention
- Changed `/capture` endpoint to use PIL for JPEG encoding: `cv2.COLOR_BGR2RGB` → `PIL.Image.fromarray` → `pil_img.save(buf, format="JPEG")` — avoids libjpeg ARM issues entirely

**Files changed:**
- `app/camera.py` — removed BGR888 attempt; always uses RGB888; `_capture_loop` uses `capture_image("main")` + `cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)`; added `import numpy as np`
- `app/api.py` — `/capture` endpoint now uses PIL JPEG encoding; added `import io`, `from PIL import Image as _PIL_Image`

---

### Raspberry Pi camera — zoom out, sharpness, and autofocus

**Problem:**
Captured image was too zoomed in (object at 12 cm appeared too close; ideal capture distance is 19 cm).
Image was also blurry.

**Fix:**
- Added `ScalerCrop` set to full `PixelArraySize` — uses the entire sensor pixel array, giving the widest possible field of view (maximum zoom-out)
- Added `Sharpness: 4.0` (default is 1.0) to increase apparent sharpness at close range
- Added `AfMode: 2` (Continuous autofocus) — effective on Camera Module 3; silently ignored on CM1/CM2 which have fixed focus
- Added a 2-second stabilization wait in `/capture` after the first frame arrives — allows exposure, white balance, and AF to settle before the image is taken

**Files changed:**
- `app/camera.py` — added ScalerCrop, Sharpness, AfMode controls after `picam.start()`
- `app/api.py` — `/capture` endpoint polls until first frame, then waits 2 s before encoding

---

### Network IP display in Settings

**Problem:**
Users needed to know the device's LAN IP address to connect from another device, but there was no way to see it from within the app.

**Fix:**
- Added `_get_network_ip()` helper in `api.py` using a UDP socket to `8.8.8.8:80` (no data sent) to detect the primary network interface IP
- `GET /settings` response now includes `network_ip` field (`null` if no network)
- Added "Network" settings group in the Settings view showing the device IP address

**Files changed:**
- `app/api.py` — added `_get_network_ip()`, included `network_ip` in `GET /settings` response
- `templates/index.html` — added Network settings group with `#networkIp` span
- `static/js/script.js` — `loadSettings()` populates `#networkIp` from `data.network_ip`

---

### Raspberry Pi autostart on boot (XDG / Wayfire)

**Problem:**
On boot, the server had to be started manually from a terminal. Chromium also had to be opened manually.

**Background:**
The Pi runs Raspberry Pi OS Trixie (Debian 13) with the Wayfire compositor. X11-based tools (`wmctrl`, `xdotool`) do not work on Wayland. The previous `systemd` service approach did not open a browser window.

**Solution:**
XDG autostart `.desktop` file in `~/.config/autostart/` — supported natively by Wayfire; executed at desktop login.

**New files in `scripts/`:**

| File | Purpose |
|---|---|
| `rpi_start_server.sh` | Activates venv, starts uvicorn HTTPS server |
| `rpi_autostart.sh` | Boot orchestrator: waits for Wayfire, starts server, polls until ready, opens Chromium fullscreen |
| `vialvision.desktop` | XDG autostart entry that launches `rpi_autostart.sh` at login |
| `rpi_setup_autostart.sh` | One-time setup: marks scripts executable, converts CRLF→LF, installs `.desktop` file |

**Boot sequence:**
1. Wayfire compositor starts
2. XDG autostart fires `rpi_autostart.sh` after login
3. `sleep 8` — waits for Wayfire to fully initialize
4. `rpi_start_server.sh` is launched in background → logs to `server.log`
5. `hostname -I` detects LAN IP → builds URL (`https://$IP:8000` or `https://localhost:8000`)
6. Polls `curl -k $URL` up to 90 seconds until server accepts connections
7. Opens `chromium-browser --start-fullscreen --ignore-certificate-errors`

**Setup (run once on the Pi):**
```bash
bash scripts/rpi_setup_autostart.sh
sudo reboot
```

**Files changed (new):**
- `scripts/rpi_start_server.sh`
- `scripts/rpi_autostart.sh`
- `scripts/vialvision.desktop`
- `scripts/rpi_setup_autostart.sh`

---

## [2026-04-16] Fix missing WebSocket dependencies
**Commit:** `0c37bec`
**Branch:** `bugs/fixing-raspi-camera-mode`

**Problem:**
The Live Stream feature produced no output. The server logs showed:
```
WARNING: Unsupported upgrade request.
WARNING: No supported WebSocket library detected. Please use
         "pip install 'uvicorn[standard]'", or install 'websockets' or 'wsproto' manually.
GET /ws HTTP/1.1  404 Not Found
```
The WebSocket connection was rejected entirely because neither `websockets` nor `wsproto`
was installed. Uvicorn requires one of these to upgrade HTTP connections to WebSocket.

**Root Cause:**
`websockets` was never included in `requirements.txt`.

**Fix:**
- Installed `websockets` library (`pip install websockets`)
- Added `websockets>=12.0` to `requirements.txt`
- Restarted the server; WebSocket connects and streams correctly

**Files changed:**
- `requirements.txt` — added `websockets>=12.0`

---

## [2026-04-16] Fix over-detection (>9 tubes) and reversed positive label
**Commit:** `e040fa3`
**Branch:** `bugs/fixing-raspi-camera-mode`

### Part 1 — Over-detection (>9 tubes reported)

**Problem:**
The model sometimes detected 10, 11, or more tubes when the physical rack only ever
has exactly 9. False positives from rack edges, label regions, and reflections were
not being removed by the deduplication step.

**Root Cause:**
`suppress_duplicate_tubes()` used a single left-to-right sweep.
- If 3 or more detections clustered near the same physical tube, only the first adjacent pair was merged; the third one slipped through.
- The check was x-axis proximity only — a false positive that was vertically offset (e.g. a tube label strip below the tube body) shared no x-overlap and was not caught.
- There was no hard upper bound; the count could exceed 9.

**Fix:**
Replaced the single-sweep algorithm with a full **greedy NMS (Non-Maximum Suppression)**:
1. Sort all detections by confidence (highest first)
2. For each kept detection, suppress all lower-confidence detections that either:
   - Have IoU overlap > 30% (catches directly overlapping boxes in 2D)
   - Have x-centre distance < 40% of average tube width (catches vertically-stacked duplicates)
3. After NMS, apply a **hard cap of 9**: if anything still passes through, keep only the top-9 by confidence
4. Sort final result left-to-right for consistent tube ordering

**Files changed:**
- `app/inference.py`
  - Added `_MAX_TUBES = 9` constant
  - Added `_iou(a, b)` helper function
  - Rewrote `suppress_duplicate_tubes()` with full greedy NMS + hard cap

---

### Part 2 — Reversed positive/negative label

**Problem:**
The label `1` (positive, microbial growth detected) was assigned to `Yellow_NoBubble`
instead of `Yellow_Bubble`. This produced wrong MPN patterns and inverted tube values.

**Root Cause:**
The original labeling logic had the class names swapped in `detections_to_tubes()`,
the drawing code in `run_inference_with_count()`, the JavaScript table renderers,
and the guideline documentation.

**Fix:**
Corrected the label mapping to: `Yellow_Bubble` → 1 (positive), everything else → 0

**Files changed:**
- `app/inference.py`
  - `detections_to_tubes()`: changed condition from `Yellow_NoBubble` to `Yellow_Bubble`
  - `run_inference_with_count()` drawing: changed condition from `Yellow_NoBubble` to `Yellow_Bubble`
  - Updated docstring to match
- `static/js/script.js`
  - Upload result table renderer (line ~437): `Yellow_NoBubble` → `Yellow_Bubble`
  - History detail modal table renderer (line ~848): `Yellow_NoBubble` → `Yellow_Bubble`
- `templates/index.html`
  - Guideline section: corrected description from "yellow / no bubble = positive" to "yellow / bubble = positive"

---

## [2026-04-16] Fix Internal Server Error on root route
**Commit:** `bdd5762`
**Branch:** `bugs/fixing-raspi-camera-mode`

**Problem:**
Navigating to `https://<host>:8000/` returned `500 Internal Server Error`.
All other routes (`/health`, `/predict`, `/docs`) worked normally.

**Root Cause:**
Starlette 1.0.0 changed the `TemplateResponse` API signature.
The old call style passed `request` inside the context dictionary:
```python
# Old — broken in Starlette 1.0.0
templates.TemplateResponse("index.html", {"request": request})
```
In Starlette 1.0.0, the context dict is used as part of a Jinja2 cache key.
Since a dict is not hashable, this raised `TypeError: unhashable type: 'dict'`
inside Jinja2's LRU cache, which FastAPI caught and converted to a 500.

**Fix:**
Updated to the new Starlette 1.0.0 API where `request` is the first positional argument:
```python
# New — correct for Starlette 1.0.0
templates.TemplateResponse(request, "index.html")
```

**Files changed:**
- `app/api.py` — `read_root()` function, line 66

---

## [2026-03-02] Fix RGB display
**Commit:** `cb4a87b`
**Branch:** `bugs/fixing-raspi-camera-mode`

**Problem:**
Camera frames displayed with incorrect colors — RGB channels were swapped.

**Fix:**
Corrected BGR/RGB channel ordering in the camera frame processing pipeline.

**Files changed:** `app/camera.py`

---

## [2026-03-02] Fix flip horizontal and vertical
**Commit:** `c63518f`
**Branch:** `bugs/fixing-raspi-camera-mode`

**Problem:**
The flip horizontal and flip vertical settings from the frontend had no effect
or flipped in the wrong direction.

**Fix:**
Corrected the flip transform logic applied to camera frames before inference.

**Files changed:** `app/camera.py`

---

## [2026-03-02] Test camera fix
**Commit:** `726edc2`
**Branch:** `bugs/fixing-raspi-camera-mode`

Diagnostic changes to camera handling for Raspberry Pi camera module.

---

## [2026-02-24] Add database, MPN table, history and details
**Commit:** `e5eb856`

Added persistent storage and full history feature:
- SQLite database (`data/vialvision.db`) with `predictions` table
- Auto-pruning when history exceeds 500 records
- Paginated history view with annotated image thumbnails
- Detail modal showing full detection breakdown
- CSV export of all history records
- MPN lookup table (40 patterns, `app/mpn/mpn_table.csv`)
- MPN Guideline view with interpretation table

**Files changed:**
- `app/db/database.py` (new)
- `app/db/queries.py` (new)
- `app/mpn/mpn_lookup.py` (new)
- `app/mpn/mpn_table.csv` (new)
- `app/api.py` — history, export, delete endpoints
- `templates/index.html` — History and Guideline views
- `static/js/script.js` — history loading, modal, MPN table render

---

## [2026-02-24] Add database and other menus
**Commit:** `fbf11a0`

Initial scaffolding for database integration and additional navigation views.

---

## [2026-02-23] Dark-Yellow UI
**Commit:** `7b82af0`

Redesigned UI with dark theme using near-black background and lime-green accent color.

---

## [2026-02-23] Refactor
**Commit:** `0fbc501`

Major codebase cleanup and restructuring after initial prototype phase.

---

## [2026-02-23] Make responsive for LCD screen
**Commit:** `df9bb9d`

Added responsive CSS breakpoints for Raspberry Pi 7-inch LCD display.
Bottom navigation bar replaces sidebar on screens ≤ 768px.

---

## [2026-02-21] Update live streaming
**Commit:** `1644a5b`

Improvements to the WebSocket streaming pipeline and frontend stream handling.

---

## [2026-02-18] Simplify output label to 0 and 1
**Commit:** `d0afab4`

Changed annotated image labels from class names to numeric values (0 or 1)
for cleaner visual output on small screens.

---

## [2026-02-06] Add Final Output
**Commit:** `eb7c96c`

Completed the prediction result display: annotated image, MPN summary block,
pattern, confidence interval, and risk classification.

---

## [2026-02-02] Tube counter done
**Commit:** `f1b9e1e`

Added tube count display on annotated images (bottom-right overlay).
`suppress_duplicate_tubes()` introduced to reduce false positives.

---

## [2026-01-20] Fix navbar position to bottom
**Commit:** `1a5e812`

Moved navigation to the bottom of the screen on mobile/RPi layouts.

---

## [2026-01-18] Generate certificate
**Commit:** `d1e57e2`

Added `generate_cert.py` script and SSL certificate generation for HTTPS support.
Required for `getUserMedia` (webcam access) in browsers over non-localhost connections.

---

## [2025-12-30] Add YOLOv8 tube detection model
**Commit:** `96ec007`

Integrated trained `best.pt` YOLOv8 Nano model for tube detection.

---

## [2025-12-25] Add camera option in settings
**Commit:** `f40164a`

Added camera source selector (Client/Server) and resolution/FPS controls in the Settings view.

---

## [2025-12-22] Fix UI/UX
**Commit:** `ef7a4fe`

General UI/UX fixes and layout improvements across all views.

---

## [2025-12-16] Add Raspberry Pi startup guide
**Commit:** `c86428b`

Added `raspberry_pi_startup_guide.md` with setup instructions for RPi deployment.

---

## [2025-12-16] Add live camera mode
**Commit:** `764eba6`

Implemented WebSocket-based live streaming. Added `Camera` class with picamera2 and
OpenCV backend support. Added Stream view to the frontend.

---

## [2025-12-15] Initial commit
**Commit:** `641eb7e`

Base project: FastAPI server, YOLO inference pipeline, image upload endpoint,
basic HTML frontend with Upload view.
