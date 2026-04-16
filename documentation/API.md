# VialVision — API Reference

Base URL: `https://<host>:8000`

All endpoints are served over HTTPS when SSL certificates are provided.

---

## REST Endpoints

---

### GET /

Returns the main web application HTML page.

**Response:** `text/html` — the single-page application shell.

---

### GET /health

Health check endpoint.

**Response:**
```json
{ "status": "ok", "model": "best.pt" }
```

---

### POST /predict

Run inference on an uploaded image. Saves the result to the database.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | image file | Yes | Any image format supported by Pillow |
| `conf` | float | No | Confidence threshold (default: 0.4, range: 0.05–0.95) |

**Response:** `application/json`

```json
{
  "id": 42,
  "detections": [
    {
      "label": "Yellow_Bubble",
      "confidence": 0.91,
      "bbox": [120.5, 45.2, 210.3, 330.1]
    }
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

**Notes:**
- `tubes` and `pattern`/`mpn`/`ci_low`/`ci_high` are `null` when `total_tubes ≠ 9`
- `id` may be `null` if database save failed (prediction is still returned)
- `bbox` is `[x1, y1, x2, y2]` in pixels (on the 50%-downscaled image)

---

### GET /history

Retrieve a paginated list of past predictions.

**Query Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 20 | Max records to return (capped at 100) |
| `offset` | int | 0 | Number of records to skip |

**Response:** `application/json`

```json
{
  "records": [
    {
      "id": 42,
      "created_at": "2026-04-16 23:03:41",
      "filename": "20260416_230341_1b87a2d1.jpg",
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
  ],
  "total": 103,
  "limit": 20,
  "offset": 0
}
```

---

### GET /history/export

Download all prediction history as a CSV file.

**Response:** `text/csv` (streamed, `Content-Disposition: attachment`)

**Columns:**
`id, created_at, filename, total_tubes, pattern, mpn_per_g, ci_low, ci_high, tubes`

---

### DELETE /history/{record_id}

Delete a single prediction record and its image file from disk.

**Path Parameter:** `record_id` — integer ID of the record.

**Response:**
```json
{ "deleted": true }
```

Returns `{ "deleted": false }` if the record was not found.

---

## WebSocket — /ws

Full-duplex real-time channel for live camera streaming and inference.

**Connect:** `wss://<host>:8000/ws`

---

### Client Mode (Browser Camera)

The browser captures frames from the user's webcam, applies rotation/flip transforms,
then sends binary blobs to the server for inference.

**Browser → Server:** Binary WebSocket message (JPEG image bytes)

**Server → Browser:**
```json
{
  "mode": "client",
  "detections": [ { "label": "Yellow_Bubble", "confidence": 0.87, "bbox": [...] } ],
  "total_tubes": 9,
  "tubes": [1, 0, 0, 1, 1, 0, 0, 0, 0],
  "pattern": "P210",
  "mpn": "15",
  "ci_low": "3.7",
  "ci_high": "42",
  "image": "<base64 JPEG>"
}
```

---

### Server Mode (Raspberry Pi / USB Camera)

The server captures frames from a local camera and pushes results to the browser.

**Start streaming — Browser → Server (text/JSON):**
```json
{
  "action": "start_server_stream",
  "resolution": "640x480",
  "source": 0
}
```

| Field | Type | Description |
|---|---|---|
| `resolution` | string | `"320x240"`, `"640x480"`, or `"1280x720"` |
| `source` | int or string | Camera index (0 = default) |

**Stop streaming — Browser → Server (text/JSON):**
```json
{ "action": "stop_server_stream" }
```

**Server → Browser** (same structure as client mode, with `"mode": "server"`):
```json
{
  "mode": "server",
  "detections": [ ... ],
  "total_tubes": 9,
  "tubes": [...],
  "pattern": "P210",
  "mpn": "15",
  "ci_low": "3.7",
  "ci_high": "42",
  "image": "<base64 JPEG>"
}
```

**Error response from server:**
```json
{ "mode": "server", "error": "Camera not available" }
```

---

### Set Confidence Threshold — Browser → Server (text/JSON):
```json
{ "action": "set_conf", "value": 0.5 }
```

Applies to all subsequent frames in the current WebSocket session.

---

## Detection Labels

| Label | Value | Meaning |
|---|---|---|
| `Yellow_Bubble` | 1 | Positive — yellow color with bubble (microbial growth) |
| `Yellow_NoBubble` | 0 | Negative — yellow color, no bubble |
| Other | 0 | Negative |

---

## MPN Pattern Format

Patterns follow the format `P{x}{y}{z}` where x, y, z are the count of positive
tubes in each dilution group (0–3 each).

Examples:
- `P000` — all negative, MPN < 3.0
- `P210` — 2 positives in group 1, 1 in group 2, 0 in group 3, MPN = 15
- `P333` — all positive, MPN > 1100

---

## Static File Routes

| Route | Serves |
|---|---|
| `/static/...` | CSS, JavaScript from `static/` |
| `/results/<filename>` | Annotated JPEG images from `data/results/` |
