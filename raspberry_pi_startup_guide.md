# Raspberry Pi Autostart Guide

This guide covers how VialVision automatically starts the server and opens Chromium in fullscreen when the Raspberry Pi boots.

> **Target OS:** Raspberry Pi OS Trixie (Debian 13) with Wayfire compositor
> **User:** `pi`
> **Project path:** `/home/pi/yvnalv/projects/Training-Project`
> **Venv path:** `/home/pi/yvnalv/vialvisionenv`

---

## How It Works

VialVision uses the **XDG autostart** mechanism — a `.desktop` file placed in `~/.config/autostart/`.
Wayfire (the Wayland compositor used on RPi OS Trixie) reads this directory at login and launches the entry automatically.

> **Note:** The older systemd service approach (documented in earlier versions) only started the server but could not open a browser window in the desktop session. XDG autostart runs inside the desktop session and can launch Chromium directly.

### Boot sequence

```
Desktop login
     │
~/.config/autostart/vialvision.desktop  ← registered by setup script
     │
scripts/rpi_autostart.sh
  ├─ sleep 8               ← wait for Wayfire to fully initialize
  ├─ rpi_start_server.sh & ← uvicorn HTTPS server in background → server.log
  ├─ hostname -I           ← detect LAN IP (e.g. 192.168.1.42)
  ├─ curl -k poll          ← wait up to 90 s for server to accept connections
  └─ chromium-browser --start-fullscreen https://<IP>:8000
```

If no network is connected, the URL falls back to `https://localhost:8000`.

---

## Running Manually

If autostart is not yet set up, or you want to start VialVision without rebooting:

```bash
bash /home/pi/yvnalv/projects/Training-Project/scripts/rpi_autostart.sh
```

This does the full sequence: starts the server, detects the IP, waits for it to be ready, then opens Chromium fullscreen.

To start just the server (no browser):

```bash
cd /home/pi/yvnalv/projects/Training-Project
source ../vialvisionenv/bin/activate
bash scripts/rpi_start_server.sh
```

---

## First-Time Setup (Autostart on Boot)

Run this **once** on the Raspberry Pi from the project root:

```bash
bash scripts/rpi_setup_autostart.sh
```

This script:
1. Makes all scripts executable (`chmod +x`)
2. Converts Windows CRLF line endings to Unix LF (`dos2unix` or `sed` fallback)
3. Copies `scripts/vialvision.desktop` to `~/.config/autostart/` (XDG method)
4. Adds a `vialvision` entry to `~/.config/wayfire.ini` under `[autostart]` (Wayfire-native method — more reliable)
5. Creates an empty `server.log` file

Then reboot to test:

```bash
sudo reboot
```

### Why two methods?

- **Wayfire `[autostart]` in `wayfire.ini`** — The most reliable method on Wayfire. Wayfire reads this file directly at compositor startup.
- **XDG `.desktop` in `~/.config/autostart/`** — The standard cross-desktop fallback. Works if the `xdg-autostart` plugin is enabled in Wayfire.

The setup script installs both so at least one will work.

### Manual Wayfire config (if setup script didn't work)

Check your `~/.config/wayfire.ini` and ensure it has:

```ini
[autostart]
vialvision = /bin/bash /home/pi/yvnalv/projects/Training-Project/scripts/rpi_autostart.sh
```

If the `[autostart]` section already exists, just add the `vialvision =` line under it.

---

## Watching Logs

To see server output after boot:

```bash
tail -f /home/pi/yvnalv/projects/Training-Project/server.log
```

The log includes:
- Boot timestamp
- Server PID
- Detected target URL
- Server readiness confirmation (or timeout warning)
- Chromium stdout/stderr

---

## Stopping the Server

The server runs as a background process. To find and stop it:

```bash
# Find the uvicorn process
ps aux | grep uvicorn

# Kill by PID
kill <PID>
```

---

## Disabling Autostart

To stop VialVision from starting on boot without deleting the files:

```bash
rm ~/.config/autostart/vialvision.desktop
```

To re-enable, run the setup script again:

```bash
bash scripts/rpi_setup_autostart.sh
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Chromium does not open | Check `server.log` for startup errors; verify venv path is correct |
| Server starts but wrong URL shown | Check `hostname -I` returns the expected IP |
| Blank screen / certificate error | Accept the self-signed cert in Chromium the first time |
| Server fails to bind port 8000 | Another process may be using port 8000; check with `ss -tlnp \| grep 8000` |
| `dos2unix: command not found` | The setup script falls back to `sed`; this is handled automatically |
| `chromium-browser: command not found` | Install with `sudo apt install chromium-browser` |

---

## Script Reference

### scripts/rpi_start_server.sh

Activates the virtual environment and starts the HTTPS server.

```bash
source /home/pi/yvnalv/vialvisionenv/bin/activate
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --ssl-keyfile key.pem \
    --ssl-certfile cert.pem
```

### scripts/rpi_autostart.sh

Boot orchestrator. Waits for desktop, starts server, polls until ready, opens Chromium.

### scripts/vialvision.desktop

XDG autostart entry. Installed to `~/.config/autostart/vialvision.desktop` by the setup script.

### scripts/rpi_setup_autostart.sh

One-time setup. Run once from the project root.
