# Architecture

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async Python) |
| ASGI server | Uvicorn |
| AI / ML | Ultralytics YOLOv8 Nano (`best.pt`) |
| Database | SQLite (WAL mode), raw `sqlite3` (no ORM) |
| Image processing | Pillow, OpenCV (headless), NumPy |
| Real-time | WebSockets (`websockets` library) |
| Frontend | Vanilla HTML5 + CSS3 + JavaScript (no framework) |
| Templates | Jinja2 |
| Camera | picamera2 (Raspberry Pi) / OpenCV (desktop) |

## High-level diagram

```
                 ┌──────────────────────────────────────────────┐
   Browser  ◄───►│  FastAPI (app/main.py → app/api.py router)    │
  (SPA, JS)      │                                                │
                 │  REST: / /health /predict /capture /history    │
                 │        /settings                               │
                 │  WS:   /ws  (client mode + server mode)         │
                 └───┬───────────────┬───────────────┬────────────┘
                     │               │               │
              inference.py       camera.py        db/ + mpn/
            (YOLO + dedup +    (picamera2 /     (SQLite +
             annotation)         OpenCV)         MPN table)
                     │                               │
                  best.pt                     data/vialvision.db
                                              data/results/*.jpg
```

## Module breakdown

For each module's public functions and responsibilities, see [MODULES.md](MODULES.md).
A summary:

### `app/main.py`
Application entry point. On import it runs three startup tasks **in order**:
1. `load_mpn_table()` — loads the MPN reference CSV into memory.
2. `init_db()` — creates `data/` + `data/results/`, the SQLite schema, and prunes if
   over `MAX_HISTORY` (500).
3. Logs startup completion.

It then mounts `/static` (frontend assets) and `/results` (saved annotated images)
as static directories and includes the API router from `api.py`.

### `app/api.py`
All HTTP routes and the WebSocket endpoint. See [API_SPEC.md](API_SPEC.md) for the
full contract. Notable helpers: `_compute_mpn()` (detections → MPN fields, returns
`None`s when `total_tubes != 9`), `_get_network_ip()` (UDP-socket trick to find the
LAN IP), and `_platform_info()` (detects `picamera2` to pick the default camera mode).

### `app/inference.py`
The inference pipeline: load → downscale 50 % → YOLO → `suppress_duplicate_tubes()`
(greedy NMS + hard cap of 9) → annotate → return `(detections, count, jpeg_bytes)`.
Also exposes `detections_to_tubes()` and `tubes_to_xyz()`. Detailed in
[INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

### `app/camera.py`
Camera abstraction with two backends — `picamera2` (preferred on Pi) and OpenCV
(fallback). Capture runs on a background thread writing a lock-protected frame
buffer. Handles the RGB→BGR conversion, flips, and Pi-specific controls (full-sensor
crop, sharpness, autofocus). Detailed in [CAMERA.md](CAMERA.md).

### `app/db/database.py` and `app/db/queries.py`
SQLite setup, connection helper, pruning (`database.py`) and all read/write
operations (`queries.py`). Schema and behavior in [DATABASE.md](DATABASE.md).

### `app/mpn/mpn_lookup.py` and `mpn_table.csv`
In-memory cache of the 40-pattern MPN reference table; `lookup_mpn(x, y, z)` builds
the `P{x}{y}{z}` key and returns the MPN value + CI (or `None`s, never crashing).
See [MPN_DESIGN.md](MPN_DESIGN.md) and [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md).

## Data flow

### Image upload (`POST /predict`)

```
Browser selects file
       │ multipart: file + conf
       ▼
inference.run_inference_with_count()
  ├─ downscale 50% (Lanczos)
  ├─ YOLOv8 detect (conf, iou=0.6, agnostic_nms=True)
  ├─ suppress_duplicate_tubes()   ← greedy NMS + hard cap 9
  └─ draw annotations + total count
       │
_compute_mpn()  (only if total_tubes == 9)
  ├─ detections_to_tubes()        ← Yellow_Bubble = 1
  ├─ tubes_to_xyz()               ← group sums
  └─ lookup_mpn(x, y, z)
       │
queries.save_prediction()         ← write JPEG + INSERT (failure is non-fatal)
       │
JSON response → Browser renders result
```

### Live stream (`/ws`)

- **Client mode:** browser captures frames (`getUserMedia` → canvas → blob), sends
  binary over WS; server infers and returns annotated frame + MPN. No DB write.
- **Server mode:** browser sends `start_server_stream`; server captures from the
  local camera, infers, and pushes annotated frames. No DB write.
- Both paths share `run_inference_with_count()`. See [STREAMING.md](STREAMING.md).

## Frontend architecture

Single-page app (no framework). A `state` object in `static/js/script.js` holds the
current view, FPS, resolution, flip, confidence, streaming flag, and camera mode.
`loadSettings()` (on page load) fetches `GET /settings` and applies saved values,
using `default_camera_mode` from the server as a platform-aware default;
`saveSettings()` is debounced 600 ms. Navigation toggles `.active` on `<section>`
views. See [MODULES.md](MODULES.md) for the view list and key functions.

## Deployment

Primary target is the Raspberry Pi 4 with XDG/Wayfire autostart. See
[DEPLOYMENT.md](DEPLOYMENT.md) and
[../raspberry_pi_startup_guide.md](../raspberry_pi_startup_guide.md).

## Design system

Dark theme: background `#0A0A0A`, lime accent `#C5F135`, purple `#7C6FF7`. Risk
colors: Safe `#22C55E`, Low `#EAB308`, Moderate `#F97316`, High `#EF4444`.
Breakpoints: desktop > 768 px (220 px sidebar), mobile ≤ 768 px (bottom nav), RPi 7"
LCD ≤ 480 px width or ≤ 320 px height.
