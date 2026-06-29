# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this project is

**VialVision** is a web-based bacterial-contamination detection system. It uses a
YOLOv8 Nano model (`best.pt`) to read a **9-tube MPN (Most Probable Number)** test
rack from a photo or a live camera stream, counts the positive tubes, maps the
pattern to a standardized MPN value with a 95 % confidence interval, and classifies
a food-safety risk level. It is designed to run on a **Raspberry Pi 4** (with the Pi
camera) as well as on a desktop for development.

This is **not** an accounting/ERP system. If documentation templates ever reference
accounting, inventory, posting rules, or multi-tenancy, those slots have been
**repurposed** to the computer-vision domain (see `docs/README.md`).

## Tech stack

- **Backend:** FastAPI (async Python), served by Uvicorn (ASGI)
- **ML:** Ultralytics YOLOv8 Nano (`best.pt`)
- **Vision:** Pillow, OpenCV (`opencv-python-headless`), NumPy
- **Database:** SQLite (WAL mode), no ORM — raw `sqlite3`
- **Realtime:** WebSockets (`websockets` library)
- **Frontend:** vanilla HTML5 + CSS3 + JavaScript (no framework), Jinja2 shell
- **Camera:** `picamera2` on Raspberry Pi, OpenCV fallback elsewhere

## Repository map

```
app/
  main.py            FastAPI app: startup tasks + static mounts + router include
  api.py             All REST routes + the /ws WebSocket handler
  inference.py       YOLO inference, greedy-NMS dedup, annotation, tube→xyz
  camera.py          Camera abstraction (picamera2 / OpenCV), background thread
  db/database.py     SQLite schema, connection, pruning (MAX_HISTORY=500)
  db/queries.py      All DB read/write operations
  mpn/mpn_lookup.py  In-memory MPN table cache + lookup
  mpn/mpn_table.csv  40-pattern MPN reference data
  fonts/             Bundled font for annotation
static/css, static/js   Frontend design system + logic
templates/index.html    Single-page app shell (6 views)
scripts/                Raspberry Pi autostart scripts
data/                   Runtime: vialvision.db + results/ (gitignored content)
best.pt                 Trained model weights
docs/                   Project documentation (start at docs/README.md)
```

## How to run

```bash
pip install -r requirements.txt
# HTTP (no camera from phone browsers):
uvicorn app.main:app --host 0.0.0.0 --port 8000
# HTTPS (required for getUserMedia / phone camera):
uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Open `https://<device-ip>:8000` and accept the self-signed certificate once.

## Conventions that matter

- **Positive tube = `Yellow_Bubble` → value `1`.** Everything else → `0`. This was
  reversed once (a real bug, see CHANGELOG 2026-04-16) — do not flip it.
- **The rack always has exactly 9 tubes.** `inference.py` enforces a hard cap of 9
  after NMS. MPN fields are `null` whenever `total_tubes != 9`.
- **Frames are stored internally in BGR (OpenCV convention).** The Pi camera path
  captures RGB then converts to BGR. JPEG encoding of camera stills uses PIL to
  avoid ARM libjpeg channel-order bugs. Do not "simplify" this — it fixed a real
  blue/red swap.
- **A DB failure must never crash a prediction response.** `/predict` returns the
  result even if `save_prediction` raises.
- **MPN lookup never crashes on an unknown pattern** — it logs and returns `None`s.

## Where to read more

- `docs/README.md` — documentation index
- `docs/ARCHITECTURE.md` — system design and data flow
- `docs/MPN_DESIGN.md` — the MPN method and risk model
- `docs/INFERENCE_PIPELINE.md` — detection → dedup → annotate → MPN
- `docs/API_SPEC.md` — REST + WebSocket contract
- `CHANGELOG.md` — full timestamped history of changes and fixes

## Working agreement

- Keep docs in sync with code when you change behavior — especially
  `API_SPEC.md`, `DATABASE.md`, and `CHANGELOG.md`.
- Match the surrounding code style (see `docs/CODING_STANDARDS.md`).
- This repo has no automated test suite yet; verify changes by running the app
  (see `docs/TESTING.md`).
