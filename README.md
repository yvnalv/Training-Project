# VialVision

**Real-time bacterial-contamination detection for 9-tube MPN test racks.**

VialVision is a lightweight web application that uses a YOLOv8 Nano model to read a
**9-tube Most Probable Number (MPN)** rack from a photo or a live camera feed. It
counts the positive tubes, maps the result to a standardized MPN value with a 95 %
confidence interval, and reports a food-safety risk level. It runs on a **Raspberry
Pi 4** with the Pi camera, and on any desktop for development.

---

## Features

- **Image analysis** — upload a photo of a rack and get an instant MPN reading
- **Live stream** — continuous inference from a browser webcam (client mode) or the
  server's Pi/USB camera (server mode), over WebSockets
- **History** — browse, view, delete, and export (CSV) all past predictions
- **MPN guideline** — built-in reference table of all 40 patterns and risk levels
- **Settings** — FPS, resolution, flip, confidence threshold; persisted to the DB
- **HTTPS** — self-signed SSL for secure remote access and browser camera permission
- **Raspberry Pi autostart** — boots straight into fullscreen Chromium

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async Python) |
| ASGI server | Uvicorn |
| ML model | Ultralytics YOLOv8 Nano (`best.pt`) |
| Vision | Pillow, OpenCV (headless), NumPy |
| Database | SQLite (WAL mode) |
| Realtime | WebSockets |
| Frontend | Vanilla HTML/CSS/JS + Jinja2 |
| Camera | picamera2 (Pi) / OpenCV (desktop) |

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Place the trained model weights (best.pt) in the project root

# 3a. Run over HTTP (camera upload from phones will NOT work)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3b. Run over HTTPS (recommended — required for browser camera access)
python generate_cert.py   # once, creates key.pem + cert.pem
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Open `https://<device-ip>:8000` and accept the self-signed certificate warning once.

Full installation and a feature walkthrough are in **[Setup.md](Setup.md)**.

---

## How it works

```
Photo / camera frame
        │
   YOLOv8 detect  ──►  greedy NMS dedup  ──►  hard cap 9 tubes
        │
   Yellow_Bubble = 1, else 0   ──►  group into (x, y, z) dilution counts
        │
   Pattern  "P{x}{y}{z}"   ──►  MPN table lookup
        │
   MPN value + 95% CI + risk level  +  annotated image
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** and
**[docs/INFERENCE_PIPELINE.md](docs/INFERENCE_PIPELINE.md)** for details.

---

## Documentation

Start at **[docs/README.md](docs/README.md)** for the full index. Highlights:

| Doc | What's in it |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product goals, scope, requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [docs/MPN_DESIGN.md](docs/MPN_DESIGN.md) | The MPN method and risk model |
| [docs/API_SPEC.md](docs/API_SPEC.md) | REST + WebSocket contract |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Running on a Raspberry Pi |
| [CHANGELOG.md](CHANGELOG.md) | Full history of changes and fixes |
| [Setup.md](Setup.md) | Installation + feature usage guide |

---

## Deployment targets

| Target | Notes |
|---|---|
| Windows / macOS / Linux (dev) | OpenCV webcam, full feature support |
| Raspberry Pi 4 | Preferred deployment; picamera2 + autostart |

See **[raspberry_pi_startup_guide.md](raspberry_pi_startup_guide.md)** for the Pi
autostart setup.

---

## MPN method in one paragraph

The Most Probable Number method estimates bacterial concentration via serial
dilution. Nine tubes are arranged in three groups of three (0.1 g, 0.01 g, 0.001 g).
A **yellow tube with a bubble is positive (1)**; anything else is negative (0). The
pattern of positives across the three groups (e.g. `P210`) maps to a standardized
MPN/g value with a 95 % confidence interval and a risk level (Safe / Low / Moderate
/ High).
