# Streaming (WebSocket Protocol)

> _This document occupies the template slot originally named `INTEGRATION_EVENTS`.
> VialVision has no external integrations; its real-time "events" are the WebSocket
> messages exchanged for live inference._

Endpoint: `WS /ws` (`wss://<host>:8000/ws`). Implemented in
`websocket_endpoint()` in `app/api.py`. Streaming results are **never persisted** —
only `POST /predict` writes to the database.

## Two modes over one socket

| Mode | Frame source | Inference | Direction of frames |
|---|---|---|---|
| **Client** | Browser webcam (`getUserMedia`) | Server | Browser → Server (binary) |
| **Server** | Server's Pi/USB camera | Server | Server captures locally |

Both modes return the same result shape and reuse
`inference.run_inference_with_count()`.

## Message contract

### Client mode
- **Browser → Server:** a **binary** WebSocket message containing JPEG bytes of the
  captured frame.
- **Server → Browser:** JSON

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

(When `total_tubes != 9`, `tubes` is `[]` and the MPN fields are `null`.)

### Server mode
- **Start — Browser → Server (text/JSON):**

```json
{ "action": "start_server_stream", "resolution": "640x480", "source": 0 }
```

| Field | Type | Notes |
|---|---|---|
| `resolution` | string | `"320x240"`, `"640x480"`, `"1280x720"`; invalid → falls back to `640x480` |
| `source` | int/string | Camera index (`0` = default); numeric strings are coerced |

- **Stop — Browser → Server (text/JSON):** `{ "action": "stop_server_stream" }`
- **Server → Browser:** same JSON shape as client mode, with `"mode": "server"`.
- **On camera failure:** `{ "mode": "server", "error": "<message>" }`.

### Control messages (either mode)
```json
{ "action": "set_conf", "value": 0.5 }
{ "action": "set_fps",  "value": 5 }
```
- `set_conf` — confidence threshold for all subsequent frames (`session_conf`).
- `set_fps` — inference-rate cap for this session (`session_min_interval`); frames
  arriving sooner are dropped to bound latency. Governs server-camera mode and
  backstops client mode. `<=0` disables. Defaults to `VIALVISION_STREAM_MAX_FPS`
  (env, default 10) until the client sends the UI "Max FPS" slider value.

Invalid values are ignored with a warning.

## Server loop mechanics

The handler runs a single loop using `asyncio.wait_for(websocket.receive(),
timeout=0.05)`:

- **Binary received** → client-mode inference, send result.
- **Text received** → control message (`start_server_stream` / `stop_server_stream`
  / `set_conf` / `set_fps`).
- **Timeout (no message in 50 ms)** → if a server camera is running, grab a frame,
  encode (`cv2.imencode(".jpg", ...)`), run inference, send result; then
  `await asyncio.sleep(0.05)`.

This timeout-driven design lets one socket interleave inbound client frames /
controls with outbound server-camera frames without separate tasks.

## Lifecycle & cleanup

- A `Camera` instance is created per WebSocket connection; `session_conf` defaults to
  `0.4`.
- On `WebSocketDisconnect` or any error, the `finally` block calls `camera.stop()`
  and attempts `websocket.close()` — the camera is always released when the socket
  ends.

## Dependency note

WebSocket support requires the `websockets` library (in `requirements.txt`). Without
it, Uvicorn cannot upgrade the connection and `/ws` returns 404 — this was a real
bug. See [../CHANGELOG.md](../CHANGELOG.md) entry _2026-04-16 — missing WebSocket
dependencies_ and [ERROR_HANDLING.md](ERROR_HANDLING.md).

## Frontend usage

- **Client mode:** `getUserMedia()` → draw to a canvas at `1/fps` → `canvas.toBlob()`
  → send binary → `onmessage` updates the `<img>` and detection table.
- **Server mode:** send `start_server_stream`; the server pushes frames until
  `stop_server_stream`. See [MODULES.md](MODULES.md).
