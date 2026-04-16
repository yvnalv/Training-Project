# VialVision — Architecture

---

## Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI (async Python) |
| ASGI Server | Uvicorn |
| AI / ML | Ultralytics YOLOv8 Nano (`best.pt`) |
| Database | SQLite (WAL mode) |
| Image Processing | Pillow, OpenCV |
| Real-time | WebSockets (`websockets` library) |
| Frontend | Vanilla HTML5 + CSS3 + JavaScript (no framework) |
| Templates | Jinja2 |

---

## Module Breakdown

### app/main.py
Entry point. Runs three startup tasks in order:
1. Loads MPN lookup table into memory
2. Initializes SQLite database and creates `data/results/` directory
3. Runs startup history pruning if record count exceeds `MAX_HISTORY` (500)

Mounts `/static` and `/results` as static file directories.
Includes the API router from `api.py`.

---

### app/api.py
All HTTP routes and the WebSocket endpoint.

**REST routes:**

| Route | Method | Description |
|---|---|---|
| `/` | GET | Renders `index.html` home page |
| `/health` | GET | Returns `{"status": "ok", "model": "best.pt"}` |
| `/predict` | POST | Accepts image upload, runs inference, saves to DB |
| `/history` | GET | Paginated history (params: `limit`, `offset`) |
| `/history/export` | GET | Streams all records as a CSV download |
| `/history/{id}` | DELETE | Deletes one record and its image file |
| `/ws` | WebSocket | Real-time streaming (dual mode) |

**`/predict` flow:**
1. Receive image bytes and optional `conf` threshold (form fields)
2. Call `inference.run_inference_with_count()`
3. Compute MPN via `_compute_mpn()` if total_tubes == 9
4. Save to database via `queries.save_prediction()`
5. Return JSON with detections, MPN fields, and base64-encoded annotated image

**WebSocket dual-mode:**
- **Client mode** — Browser captures frames with `getUserMedia`, sends binary blobs over WS, server runs inference and sends annotated image back
- **Server mode** — Server captures from local camera (picamera2 or OpenCV), runs inference, sends annotated frames to browser
- Both modes use the same `inference.run_inference_with_count()` path
- Session confidence threshold is adjustable via `set_conf` control messages

---

### app/inference.py
The full inference pipeline.

**`run_inference_with_count(image_bytes, conf=0.4)`**
1. Open image from bytes, downscale 50% (Lanczos) for performance
2. Run YOLOv8 with `conf` threshold, `iou=0.6`, `agnostic_nms=True`
3. Call `suppress_duplicate_tubes()` to remove false positives
4. Draw annotated bounding boxes and tube count on image
5. Return `(detections, total_count, annotated_jpeg_bytes)`

**`suppress_duplicate_tubes(detections, iou_thresh=0.3, x_thresh_ratio=0.4)`**

Greedy NMS deduplication — processes detections highest-confidence first.
Two suppression criteria (either triggers suppression):
- IoU overlap > 30% — catches directly overlapping boxes
- x-centre distance < avg_tube_width × 0.4 — catches vertically-stacked duplicates (e.g. label region vs tube body)

After NMS: hard cap of 9 tubes max. If anything still slips through,
only the top-9 by confidence are kept. Final result is sorted left-to-right.

**`detections_to_tubes(detections)`**
Maps each detection label:
- `Yellow_Bubble` → 1 (positive, microbial growth detected)
- anything else → 0 (negative)

**`tubes_to_xyz(tubes)`**
Groups 9 tube values into 3 dilution counts:
- `x` = sum of tubes 1–3 (0.1 g dilution)
- `y` = sum of tubes 4–6 (0.01 g dilution)
- `z` = sum of tubes 7–9 (0.001 g dilution)

---

### app/camera.py
Camera abstraction that works on both Raspberry Pi and desktop.

**Backend priority:**
1. `picamera2` — preferred on Raspberry Pi (native driver, low latency)
2. OpenCV — fallback for USB cameras on any platform

**Key behaviors:**
- Capture runs in a background thread, continuously updating a shared frame buffer with a Lock for thread safety
- Supports rotation and horizontal flip transforms (configured from frontend settings)
- `get_frame()` returns the latest frame (thread-safe read)
- `stop()` signals the thread and joins with a 2-second timeout

---

### app/db/database.py
SQLite setup and lifecycle management.

**Schema:**
```sql
CREATE TABLE predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename    TEXT,
    total_tubes INTEGER,
    pattern     TEXT,
    mpn         TEXT,
    ci_low      TEXT,
    ci_high     TEXT,
    tubes       TEXT,       -- JSON array, e.g. "[1,0,0,1,1,0,0,0,0]"
    detections  TEXT,       -- JSON array of detection dicts
    image_path  TEXT        -- relative path to annotated JPEG
);
CREATE INDEX idx_created_at ON predictions (created_at DESC);
```

**Auto-pruning:**
- Triggered on startup and after every INSERT
- Deletes the oldest rows (by `created_at`) when count > 500
- Also unlinks the corresponding image files from disk

---

### app/db/queries.py
All database operations.

| Function | Description |
|---|---|
| `save_prediction(...)` | Generates filename, writes image to disk, inserts DB row, prunes |
| `list_predictions(limit, offset)` | Paginated fetch, newest first, deserializes JSON fields |
| `count_predictions()` | Returns total record count |
| `delete_prediction(id)` | Deletes DB row and image file, returns True/False |
| `export_csv()` | Returns all records as a CSV string |

---

### app/mpn/mpn_lookup.py
In-memory MPN reference table.

**`load_mpn_table()`** — called once at startup, reads `mpn_table.csv`
into a dict keyed by pattern string (e.g. `"P210"`).

**`lookup_mpn(x, y, z)`** — builds pattern key from (x,y,z) counts,
returns `{"pattern", "mpn", "low", "high"}`.
Returns `None` values (does not crash) if pattern is not in table.

---

## Data Flow

### Image Upload

```
Browser selects file
       │
POST /predict (multipart: file + conf)
       │
inference.run_inference_with_count()
  ├─ Downscale 50%
  ├─ YOLOv8 detect
  ├─ suppress_duplicate_tubes()   ← greedy NMS + hard cap 9
  └─ draw annotations
       │
_compute_mpn()
  ├─ detections_to_tubes()       ← Yellow_Bubble=1
  ├─ tubes_to_xyz()
  └─ lookup_mpn(x, y, z)
       │
queries.save_prediction()
  ├─ write JPEG to data/results/
  └─ INSERT into predictions
       │
JSON response → Browser renders result
```

### Live Stream

```
Browser: getUserMedia() → canvas capture at 1/fps interval
       │
WebSocket binary frame → /ws
       │
Server: inference.run_inference_with_count()
       │
WebSocket JSON response → { image_b64, detections, mpn fields }
       │
Browser: update <img> src + detection table
```

### MPN Lookup

```
9 detections (left → right, sorted)
       │
[1, 0, 0, 1, 1, 0, 0, 0, 0]   ← Yellow_Bubble=1
       │
x=sum(0:3)=1, y=sum(3:6)=2, z=sum(6:9)=0
       │
Pattern key = "P120"
       │
CSV lookup → { mpn: "15", ci_low: "3.7", ci_high: "42" }
       │
Risk classification:
  < 3    → Safe
  3–20   → Low
  21–110 → Moderate
  > 110  → High
```

---

## Frontend Architecture

The frontend is a single-page app (SPA) with no external JS framework.

**State object** (`state` in script.js):
```js
{
  currentView: 'home',
  fps: 5,
  resolution: '640x480',
  rotation: 0,
  flipHorizontal: false,
  confidence: 0.25,
  isStreaming: false,
  cameraMode: 'client' | 'server'
}
```

**Navigation:** `navigateTo(view)` toggles `.active` on `<section>` views and nav items.

**Upload path:** `uploadImage()` → `fetch POST /predict` → `updateMpnDisplay()` + `updateTable()`

**Stream path:**
- Client mode: `getUserMedia()` → `canvas.toBlob()` → WS binary send → `onmessage` updates display
- Server mode: WS text message `{action: "start_server_stream"}` → server pushes frames

**History:**
- `loadHistory()` fetches `/history?limit=20&offset=0`
- `renderHistoryCard()` builds card DOM with delete + modal open
- `openHistoryModal()` calls `/history/{id}` (actually uses cached data) and renders detail view

---

## Design System (style.css)

**Color palette:**
- Background: `#0A0A0A` (near black)
- Accent: `#C5F135` (lime green)
- Secondary: `#7C6FF7` (purple)
- Text: `#F0F0F0`
- Muted: `#666666`

**Breakpoints:**
- Desktop: > 768px (fixed sidebar 220px)
- Mobile: ≤ 768px (bottom nav bar 60px)
- RPi 7" LCD: ≤ 480px width or ≤ 320px height

**Risk colors:**
- Safe: green (`#22C55E`)
- Low: yellow (`#EAB308`)
- Moderate: orange (`#F97316`)
- High: red (`#EF4444`)
