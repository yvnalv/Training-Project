# VialVision — Project Documentation

VialVision is a web-based bacterial contamination detection system.
It uses a YOLOv8 Nano model to analyze 9-tube MPN (Most Probable Number)
test racks and calculate contamination levels from a photo or live camera stream.

---

## Documentation Index

| File | Description |
|---|---|
| [README.md](README.md) | This file — project overview and quick start |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, data flow, module breakdown |
| [API.md](API.md) | All REST endpoints and WebSocket protocol |
| [CHANGELOG.md](CHANGELOG.md) | Timestamped log of all changes, bugs, and fixes |

---

## Quick Start

### Requirements

```
Python 3.10+
pip install -r requirements.txt
```

### Run (HTTP)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Run (HTTPS with SSL)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Then open `https://<your-ip>:8000` in a browser.
Accept the self-signed certificate warning on first visit.

---

## Project Structure

```
Training Project/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── api.py               # All routes and WebSocket handler
│   ├── inference.py         # YOLO inference + deduplication pipeline
│   ├── camera.py            # Camera abstraction (picamera2 / OpenCV)
│   ├── db/
│   │   ├── database.py      # SQLite schema, connection, pruning
│   │   └── queries.py       # All DB read/write operations
│   ├── mpn/
│   │   ├── mpn_lookup.py    # In-memory MPN table cache + lookup
│   │   └── mpn_table.csv    # 40-pattern MPN reference data
│   └── fonts/
│       └── DejaVuSans-Bold.ttf
├── static/
│   ├── css/style.css        # Full design system (dark theme, responsive)
│   └── js/script.js         # All frontend logic and state
├── templates/
│   └── index.html           # Single-page app shell (6 views)
├── data/                    # Created at runtime
│   ├── vialvision.db        # SQLite database
│   └── results/             # Annotated JPEG images
├── documentation/           # This folder
├── requirements.txt
├── key.pem / cert.pem       # Self-signed SSL certificate
└── best.pt                  # Trained YOLOv8 model weights
```

---

## Features

- **Image Analysis** — Upload a photo of a 9-tube rack and get instant MPN results
- **Live Stream** — Real-time inference from webcam (client) or server camera (Raspberry Pi)
- **History** — Browse all past predictions, view annotated images, export to CSV
- **MPN Guideline** — Built-in reference table and risk interpretation guide
- **Settings** — Adjust FPS, resolution, rotation, flip, and confidence threshold
- **HTTPS** — SSL support for secure remote access

---

## MPN Method Summary

The Most Probable Number (MPN) method estimates bacterial concentration using
serial dilution. 9 tubes are arranged in 3 groups of 3 (dilutions: 0.1g, 0.01g, 0.001g).

- **Yellow + Bubble** = Positive tube (bacterial growth detected) → value **1**
- **Clear / No Bubble** = Negative tube → value **0**

The pattern of positives (e.g. `P210` = 2 positive, 1 positive, 0 positive) maps
to a standardized MPN value with a 95% confidence interval.

### Risk Levels

| MPN / g | Risk |
|---|---|
| < 3 | Safe |
| 3 – 20 | Low |
| 21 – 110 | Moderate |
| > 110 | High |

---

## Deployment Targets

| Target | Notes |
|---|---|
| Windows (dev) | Full feature support via OpenCV camera |
| Raspberry Pi | Preferred deployment; uses picamera2 for native camera |
| Docker | docker-compose.yml + Dockerfile provided |
