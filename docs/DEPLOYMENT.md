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

---

## VPS deployment (Docker + CI/CD)

A **separate** deployment (does not replace the Pi appliance): a public web version where
users use their **device camera** (client mode) or upload photos. Pattern mirrors the
AccounTrack project — build once in CI, ship a prebuilt image to the VPS.

### How it works

```
push to main ──► GitHub Actions: build image ──► push to GHCR
                                                    │
                                SSH into VPS ◄──────┘
                                docker compose -f docker-compose.prod.yml pull && up -d
```

The **VPS builds nothing** — it pulls the ready image. The trained model is **baked into
the image** (`models/vialvision_yolo26.pt`, committed to git), so builds are reproducible
and a **model update = commit new weights + push** (CI rebuilds and redeploys).

### Files
- `Dockerfile` — the app image (CPU torch + headless OpenCV + model).
- `docker-compose.prod.yml` — **pulls** `ghcr.io/yvnalv/vialvision`, `mem_limit: 1g`,
  publishes a host port, persists `data/` in a volume.
- `.github/workflows/deploy.yml` — build → push GHCR → SSH deploy (also manual via
  *Actions → Deploy → Run workflow*).

### TLS & routing — your existing reverse proxy
TLS + subdomain routing are **not** in this stack. Your VPS's existing reverse proxy
terminates HTTPS (Let's Encrypt) and forwards `vialvision.yvnalvworks.com` to the
container. Two wiring options:
- **Host-level proxy** (Nginx / Caddy / Nginx Proxy Manager on the host): keep the
  compose `ports` (`127.0.0.1:8095:8000`) and point the proxy at `http://127.0.0.1:8095`.
- **Dockerized proxy**: remove `ports`, attach `app` to the proxy's external network, and
  route by container name `vialvision-app:8000`.

A real cert also means the **phone live camera works with no warning**.

### One-time VPS setup
1. Docker + Compose installed; your reverse proxy already running.
2. Create the app dir (`VPS_APP_DIR`), put `docker-compose.prod.yml` there (copy or
   `git clone`).
3. **GHCR login** (image is private):
   `echo <GHCR_PAT> | docker login ghcr.io -u yvnalv --password-stdin`
   (PAT needs `read:packages`).
4. **Reverse proxy:** add `vialvision.yvnalvworks.com` → `http://127.0.0.1:8095` (or the
   container).
5. **GitHub secrets** (repo → Settings → Secrets → Actions): `VPS_HOST`, `VPS_USER`,
   `VPS_SSH_KEY` (a private key whose public half is in the VPS user's
   `~/.ssh/authorized_keys`), `VPS_APP_DIR`.
6. **RAM:** the app needs ~400 MiB. On a 1 GB box, **stop other apps first** (e.g.
   `docker stop n8n` / pause the relevant compose) to free memory.

### First deploy
Set up the VPS + secrets, then merge to `main` (or run the workflow manually). Verify:
```bash
curl -s https://vialvision.yvnalvworks.com/health     # {"status":"ok",...}
```

### Rollback
*Actions → Deploy → Run workflow →* enter a previous image `tag` or git SHA.

### Networking (this VPS)
The container joins the existing nginx network **`app_default`** and is reached by name
`vialvision-app:8000` — **no host port is published**. nginx routes
`vialvision.yvnalvworks.com` → `http://vialvision-app:8000` (see the server block in the
proxy config). The cert (`/etc/letsencrypt/live/yvnalvworks.com/`) was expanded to include
the subdomain via `certbot --standalone` with nginx stop/start hooks.

### Environment variables (`docker-compose.prod.yml`)
| Var | Default | Purpose |
|---|---|---|
| `VIALVISION_TAG` | `latest` | Image tag to run (set by the deploy workflow) |
