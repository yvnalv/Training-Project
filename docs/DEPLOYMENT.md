# Deployment

VialVision runs on a desktop (development) and on a **Raspberry Pi 4** (primary
appliance). For a complete first-time install and feature walkthrough, see
[../Setup.md](../Setup.md). For the full Pi autostart reference, see
[../raspberry_pi_startup_guide.md](../raspberry_pi_startup_guide.md).

> **Choosing hardware?** See [HARDWARE.md](HARDWARE.md) for a benchmarked
> recommendation (short version: Raspberry Pi 5 (8 GB) + NCNN export, and spend the
> rest of the budget on camera + lighting rather than a faster chip).

## Prerequisites

- Python **3.10+**
- `pip install -r requirements.txt`
- `best.pt` present in the **project root** (the model is loaded as `"best.pt"`
  relative to the working directory, so always start the server from the repo root)
- For HTTPS / browser camera: `key.pem` + `cert.pem` (generate with
  `python generate_cert.py`)

## Desktop (development)

```bash
python -m venv venv
# Windows:        venv\Scripts\activate
# macOS/Linux:    source venv/bin/activate
pip install -r requirements.txt

# HTTP (no phone camera):
uvicorn app.main:app --host 0.0.0.0 --port 8000

# HTTPS (recommended):
python generate_cert.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Open `https://localhost:8000` (or `https://<device-ip>:8000` from another device) and
accept the certificate warning once.

On Windows there is also `run_https.bat` for convenience.

## Raspberry Pi

Target: Raspberry Pi OS **Trixie (Debian 13)** with the **Wayfire** compositor.

```
Project path:  /home/pi/yvnalv/projects/Training-Project
Venv path:     /home/pi/yvnalv/vialvisionenv
```

### Install
```bash
cd /home/pi/yvnalv
python3 -m venv vialvisionenv
source vialvisionenv/bin/activate
cd projects/Training-Project
pip install -r requirements.txt
# place best.pt in the project root
```
`picamera2` is preinstalled on Raspberry Pi OS and is **not** in `requirements.txt`.

### Run manually
```bash
# server only:
bash scripts/rpi_start_server.sh
# full appliance flow (server + detect IP + open Chromium fullscreen):
bash scripts/rpi_autostart.sh
```

### Autostart on boot (run once)
```bash
bash scripts/rpi_setup_autostart.sh
sudo reboot
```
This marks scripts executable, converts CRLF→LF, installs
`scripts/vialvision.desktop` to `~/.config/autostart/`, adds a `[autostart]` entry to
`~/.config/wayfire.ini` (both methods for reliability), and creates `server.log`.

### Boot sequence
```
Desktop login → vialvision.desktop / wayfire [autostart]
  → scripts/rpi_autostart.sh
      ├─ sleep 8 (wait for Wayfire)
      ├─ rpi_start_server.sh & (uvicorn HTTPS → server.log)
      ├─ hostname -I (detect LAN IP, fallback localhost)
      ├─ curl -k poll (up to 90 s until ready)
      └─ chromium-browser --start-fullscreen --ignore-certificate-errors https://<IP>:8000
```

### Scripts
| Script | Role |
|---|---|
| `scripts/rpi_start_server.sh` | Activate venv, start uvicorn HTTPS server |
| `scripts/rpi_autostart.sh` | Boot orchestrator (server + IP + poll + Chromium) |
| `scripts/vialvision.desktop` | XDG autostart entry |
| `scripts/rpi_setup_autostart.sh` | One-time setup |

## Operations

- **Logs:** `tail -f server.log` (on the Pi).
- **Stop server:** `ps aux | grep uvicorn` then `kill <PID>`.
- **Disable autostart:** `rm ~/.config/autostart/vialvision.desktop` (re-run setup to
  re-enable).
- **Port in use:** `ss -tlnp | grep 8000`.
- **Data/backups:** copy `data/vialvision.db` (server stopped) to back up history +
  settings. See [DATABASE.md](DATABASE.md).

## Health & smoke check

```bash
curl -k https://<host>:8000/health   # {"status":"ok","model":"best.pt"}
```

Common issues are tabulated in [../Setup.md](../Setup.md#troubleshooting) and
[ERROR_HANDLING.md](ERROR_HANDLING.md).
