# API Specification

Base URL: `https://<host>:8000` (HTTP also works, but browser camera access requires
HTTPS). All responses are JSON unless noted.

Response shapes below are taken from `app/api.py` and reflect actual behavior.

---

## REST endpoints

### `GET /`
Renders the single-page app (`templates/index.html`). Response: `text/html`.

---

### `GET /health`
Health check.

```json
{ "status": "ok", "model": "best.pt" }
```

---

### `POST /predict`
Run inference on an uploaded image and persist the result.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | image file | Yes | Any format Pillow can open |
| `conf` | float | No | Confidence threshold (default `0.4`, clamped to `0.05–0.95`) |

**Response:** `application/json`

```json
{
  "id": 42,
  "detections": [
    { "label": "Yellow_Bubble", "confidence": 0.91, "bbox": [120.5, 45.2, 210.3, 330.1] }
  ],
  "total_tubes": 9,
  "tubes": [1, 0, 0, 1, 1, 0, 0, 0, 0],
  "pattern": "P210",
  "mpn": "15",
  "ci_low": "3.7",
  "ci_high": "42",
  "image": "<base64-encoded JPEG>"
}
```

Notes:
- When `total_tubes != 9`: `tubes` is `[]` and `pattern`/`mpn`/`ci_low`/`ci_high`
  are `null` (a warning is logged).
- `id` is `null` if the DB save failed — the prediction is **still returned**.
- `bbox` is `[x1, y1, x2, y2]` in pixels on the **50 %-downscaled** image.

---

### `GET /history`
Paginated list of past predictions.

**Query params:** `limit` (default 20, hard cap 100), `offset` (default 0).

**Response:**

```json
{
  "total": 103,
  "limit": 20,
  "offset": 0,
  "records": [
    {
      "id": 42,
      "created_at": "2026-04-16 23:03:41",
      "filename": "photo.jpg",
      "total_tubes": 9,
      "pattern": "P210",
      "mpn": "15",
      "ci_low": "3.7",
      "ci_high": "42",
      "tubes": [1, 0, 0, 1, 1, 0, 0, 0, 0],
      "detections": [ ... ],
      "image_path": "data/results/20260416_230341_1b87a2d1.jpg",
      "image_url": "/results/20260416_230341_1b87a2d1.jpg"
    }
  ]
}
```

`image_url` is derived from `image_path` (the filename served under `/results/`), or
`null` if there is no image.

---

### `GET /history/export`
Streams all records as a CSV download (`Content-Disposition: attachment;
filename=vialvision_history.csv`).

Columns: `id, created_at, filename, total_tubes, pattern, mpn_per_g, ci_low,
ci_high, tubes`.

---

### `DELETE /history/{record_id}`
Delete a record and its image file.

- Success: `{ "deleted": <record_id> }`
- Not found: HTTP `404` with `{ "error": "Record <id> not found." }`

---

### `GET /settings`
Saved UI settings plus platform detection hints and the device LAN IP. Used by the
frontend on load to restore settings and pick platform-aware defaults.

```json
{
  "is_raspi": true,
  "has_picamera2": true,
  "default_camera_mode": "server",
  "network_ip": "192.168.1.42",
  "settings": {
    "cameraMode": "server",
    "fps": "5",
    "resolution": "640x480",
    "confidence": "0.25",
    "flipHorizontal": "false"
  }
}
```

Notes:
- Saved settings are nested under the `settings` key (only previously-saved keys
  appear; values are strings).
- `default_camera_mode` is `"server"` when `picamera2` is importable, else `"client"`.
- `network_ip` is `null` if the device is offline.

---

### `PUT /settings`
Upsert UI settings. JSON body of `{key: value}`. Only allowed keys are persisted;
unknown keys are silently ignored.

Allowed keys: `cameraMode`, `fps`, `resolution`, `confidence`, `flipHorizontal`.

- Success: `{ "saved": ["cameraMode", "fps", ...] }` (the keys that were persisted)
- Invalid JSON body: HTTP `400` with `{ "error": "Invalid JSON body." }`

---

### `GET /capture`
Capture a single still from the **server-side** camera (Pi/USB). Used when the camera
source is `server`. Waits up to ~3 s for the first frame, then waits an additional
2 s for exposure/AWB/AF to stabilize before encoding (with PIL, to avoid ARM libjpeg
channel-order issues).

- Success: `{ "image": "<base64-encoded JPEG>" }`
- No frame in time: HTTP `503` with `{ "error": "Camera not ready — ..." }`
- Other failure: HTTP `500` with `{ "error": "<message>" }`

---

## WebSocket — `/ws`

Full-duplex channel for live streaming. Connect: `wss://<host>:8000/ws`. Streaming
results are **not** persisted to the database. Full protocol in
[STREAMING.md](STREAMING.md).

### Client mode (browser camera)
- **Browser → Server:** binary WebSocket message (JPEG bytes).
- **Server → Browser:** JSON with `"mode": "client"`, `detections`, `total_tubes`,
  the MPN fields, and base64 `image`.

### Server mode (Pi / USB camera)
- **Browser → Server (text/JSON):** `{ "action": "start_server_stream",
  "resolution": "640x480", "source": 0 }` to start; `{ "action":
  "stop_server_stream" }` to stop.
- **Server → Browser:** JSON with `"mode": "server"` and the same fields as client
  mode; on failure `{ "mode": "server", "error": "<message>" }`.

### Control
- `{ "action": "set_conf", "value": 0.5 }` — sets the confidence threshold for all
  subsequent frames in this WebSocket session.
- `{ "action": "set_fps", "value": 5 }` — caps the inference rate for this session
  (frames/sec); frames arriving sooner are dropped to bound latency. Governs
  server-camera mode and backstops client mode. `<=0` disables the cap. Defaults to
  `VIALVISION_STREAM_MAX_FPS` (env, default 10) until the client sends a value. This
  is the UI "Max FPS" slider — see [STREAM_PERFORMANCE.md](STREAM_PERFORMANCE.md).

---

## Detection labels

| Label | Tube value | Meaning |
|---|---|---|
| `Yellow_Bubble` | 1 | Positive — yellow with bubble (microbial growth) |
| anything else | 0 | Negative |

See [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) for the full mapping rules.

---

## Static file routes

| Route | Serves |
|---|---|
| `/static/...` | CSS / JS from `static/` |
| `/results/<filename>` | Annotated JPEGs from `data/results/` |
