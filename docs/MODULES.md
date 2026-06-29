# Modules

Per-module responsibilities and public API. File paths are relative to the repo root.

---

## `app/main.py`

FastAPI application entry point.

- Configures logging.
- Creates `app = FastAPI(title="VialVision", version="1.0.0")`.
- **Startup tasks (run at import):** `load_mpn_table()`, then `init_db()`.
- Mounts `/static` → `static/` and `/results` → `data/results/`.
- Includes the API router via `app.include_router(api.router)`.

---

## `app/api.py`

All REST routes and the WebSocket endpoint. Full contract in [API_SPEC.md](API_SPEC.md).

| Symbol | Type | Purpose |
|---|---|---|
| `router` | `APIRouter` | All routes register here |
| `_compute_mpn(detections, total_count)` | helper | Returns MPN fields; all `None` when `total_count != 9` |
| `read_root()` | `GET /` | Renders `index.html` (Starlette 1.0 signature: `request` first) |
| `health()` | `GET /health` | `{"status": "ok", "model": "best.pt"}` |
| `predict(file, conf)` | `POST /predict` | Runs inference, persists, returns result + base64 image |
| `get_history(limit, offset)` | `GET /history` | Paginated history + `image_url` per record |
| `export_history()` | `GET /history/export` | Streams CSV download |
| `delete_history_record(id)` | `DELETE /history/{id}` | Deletes record + image, 404 if missing |
| `_get_network_ip()` | helper | LAN IP via UDP socket to `8.8.8.8:80` |
| `_platform_info()` | helper | `is_raspi`, `has_picamera2`, `default_camera_mode` |
| `get_settings_endpoint()` | `GET /settings` | Saved settings + platform info + network IP |
| `put_settings_endpoint()` | `PUT /settings` | Upserts allowed keys only |
| `capture_frame()` | `GET /capture` | Single still from server camera (PIL JPEG encode) |
| `websocket_endpoint(ws)` | `WS /ws` | Live stream — client + server modes |

Allowed settings keys: `cameraMode`, `fps`, `resolution`, `confidence`,
`flipHorizontal`.

---

## `app/inference.py`

YOLO inference + post-processing. Details in [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

| Symbol | Purpose |
|---|---|
| `model = YOLO("best.pt")` | Loaded once at import |
| `_MAX_TUBES = 9` | Hard cap on tube count |
| `_iou(a, b)` | IoU of two `[x1,y1,x2,y2]` boxes |
| `suppress_duplicate_tubes(detections, iou_thresh=0.3, x_thresh_ratio=0.4)` | Greedy NMS dedup + hard cap + left-to-right sort |
| `detections_to_tubes(detections)` | `Yellow_Bubble → 1`, else `0`; raises if not exactly 9 |
| `tubes_to_xyz(tubes)` | Group sums: tubes[0:3], [3:6], [6:9] |
| `run_inference_with_count(image_bytes, conf=0.4)` | Full pipeline → `(detections, count, jpeg_bytes)` |

Font path is resolved absolutely from the module location
(`Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"`) so it works regardless
of the launch directory.

---

## `app/camera.py`

Camera abstraction. Details in [CAMERA.md](CAMERA.md).

| Symbol | Purpose |
|---|---|
| `Camera` | The class; one instance per capture session |
| `Camera.start(source=0, width=640, height=480)` | Start picamera2 or OpenCV backend on a background thread |
| `Camera.get_frame()` | Thread-safe read of the latest BGR frame |
| `Camera.stop()` | Signal + join thread (2 s timeout), release backend, clear frame |
| `Camera.camera_available()` | Whether the active backend is open and running |
| `Camera.is_running` | Public flag |
| `_open_opencv_capture(...)` | Tries multiple sources/backends per platform |
| `_capture_loop()` | Background frame producer (handles RGB→BGR + flips) |

---

## `app/db/database.py`

SQLite lifecycle. Details in [DATABASE.md](DATABASE.md).

| Symbol | Purpose |
|---|---|
| `_PROJECT_ROOT`, `DATA_DIR`, `RESULTS_DIR`, `DB_PATH` | Resolved paths |
| `MAX_HISTORY = 500` | Prune threshold |
| `get_connection()` | SQLite connection (WAL, `Row` factory, FK on) |
| `init_db()` | Create dirs + schema + startup prune |
| `_prune_oldest()` | Delete oldest rows + their images when over cap |
| `maybe_prune()` | Public hook called after each INSERT |

---

## `app/db/queries.py`

All DB read/write operations.

| Symbol | Purpose |
|---|---|
| `save_prediction(...)` | Write image, INSERT row, prune; returns new id |
| `list_predictions(limit=20, offset=0)` | Page of records (limit capped at 100), JSON fields parsed |
| `count_predictions()` | Total record count |
| `delete_prediction(id)` | Delete row + image; `True`/`False` |
| `export_csv()` | All records as CSV string |
| `get_all_settings()` | `{key: value}` of settings |
| `set_settings(data)` | Upsert via `ON CONFLICT DO UPDATE` |
| `_safe_json(value, fallback)` | Parse JSON, return fallback on error |

---

## `app/mpn/mpn_lookup.py`

In-memory MPN reference table. Details in [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md).

| Symbol | Purpose |
|---|---|
| `MPN_TABLE_PATH` | Path to `mpn_table.csv` (resolved from module dir) |
| `_REQUIRED_COLUMNS` | `{pattern, mpn_per_g, ci_low, ci_high}` |
| `load_mpn_table()` | Load + validate CSV into `_MPN_TABLE` (called at startup) |
| `lookup_mpn(x, y, z)` | Build `P{x}{y}{z}` key → `{pattern, mpn, low, high}` (or `None`s) |

---

## Frontend — `static/js/script.js`, `static/css/style.css`, `templates/index.html`

Single-page app shell with six views: **Home** (upload), **Stream**, **History**,
**Guideline**, **Settings**, plus detail modals. Key JS functions:
`navigateTo(view)`, `loadSettings()`, `saveSettings()` (debounced 600 ms),
`uploadImage()`, `updateMpnDisplay()`, `updateTable()`, `loadHistory()`,
`renderHistoryCard()`, `openHistoryModal()`, and the WebSocket stream handlers.
