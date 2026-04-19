# VialVision — Setup & Usage Guide

This guide covers first-time installation and a full walkthrough of every feature.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
   - [Windows / macOS / Linux (Development)](#windows--macos--linux-development)
   - [Raspberry Pi (Deployment)](#raspberry-pi-deployment)
3. [SSL Certificate](#ssl-certificate)
4. [Starting the Server](#starting-the-server)
5. [Opening the App](#opening-the-app)
6. [Feature Guide](#feature-guide)
   - [Image Upload & Analysis](#image-upload--analysis)
   - [Live Camera Stream](#live-camera-stream)
   - [History](#history)
   - [MPN Guideline](#mpn-guideline)
   - [Settings](#settings)
7. [Raspberry Pi Autostart](#raspberry-pi-autostart)
8. [Troubleshooting](#troubleshooting)

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| pip | Latest recommended |
| Chromium / Chrome | Any modern version |
| (Raspberry Pi only) picamera2 | Pre-installed on RPi OS |

---

## Installation

### Windows / macOS / Linux (Development)

**1. Clone or copy the project**

```bash
git clone <repo-url>
cd Training-Project
```

**2. Create a virtual environment**

```bash
python -m venv venv
```

**3. Activate the virtual environment**

- Windows:
  ```bash
  venv\Scripts\activate
  ```
- macOS / Linux:
  ```bash
  source venv/bin/activate
  ```

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

**5. Place the model weights**

Copy `best.pt` (the trained YOLOv8 model) into the project root:
```
Training-Project/
└── best.pt
```

---

### Raspberry Pi (Deployment)

**1. Copy the project to the Pi**

Place the project at:
```
/home/pi/yvnalv/projects/Training-Project/
```

**2. Create a virtual environment**

```bash
cd /home/pi/yvnalv
python3 -m venv vialvisionenv
source vialvisionenv/bin/activate
```

**3. Install dependencies**

```bash
cd projects/Training-Project
pip install -r requirements.txt
```

> `picamera2` is pre-installed on Raspberry Pi OS and does **not** need to be in `requirements.txt`.

**4. Place the model weights**

```
/home/pi/yvnalv/projects/Training-Project/best.pt
```

---

## SSL Certificate

HTTPS is required for browser camera access (`getUserMedia`). A self-signed certificate is sufficient.

**Generate a certificate (run once):**

```bash
python generate_cert.py
```

This creates `key.pem` and `cert.pem` in the project root.

> When you first open the app in a browser, you will see a certificate warning.
> Click **Advanced → Proceed** (Chrome) or **Accept the Risk** (Firefox) to continue.
> This only needs to be done once per browser/device.

---

## Starting the Server

**With HTTPS (recommended):**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

**Without HTTPS (development only — camera upload from phone will not work):**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The server starts on port `8000`. You will see:
```
INFO:     Uvicorn running on https://0.0.0.0:8000
```

---

## Opening the App

1. Find the device's IP address:
   - Windows: `ipconfig` → look for IPv4 Address
   - Linux/Pi: `hostname -I`

2. Open in a browser:
   ```
   https://<device-ip>:8000
   ```
   For example: `https://192.168.1.42:8000`

3. Accept the self-signed certificate warning on first visit.

> If accessing from the same machine: `https://localhost:8000`

---

## Feature Guide

---

### Image Upload & Analysis

**Purpose:** Analyze a photo of a 9-tube MPN rack and get a bacterial contamination reading.

**How to use:**

1. Navigate to the **Home** view (house icon in the nav bar).
2. Tap or click **Upload Image**.
3. Choose the image source:
   - **Upload from device** — select a photo from your phone, computer, or tablet
   - **Take with server camera** — captures a still image directly from the Raspberry Pi camera (only available when server-side camera is running)
4. The image is sent to the server for analysis.
5. Results are displayed:
   - **Annotated image** — bounding boxes drawn on each detected tube (labeled 0 or 1)
   - **Tube table** — each tube's position and positive/negative value
   - **MPN value** — estimated bacterial concentration (MPN/g)
   - **95% confidence interval**
   - **Risk level** — Safe / Low / Moderate / High (color coded)

**Tips:**
- Ensure all 9 tubes are clearly visible in the frame
- Capture from approximately 19 cm above the rack for best results (Raspberry Pi camera)
- Good lighting reduces detection errors
- Adjust the confidence threshold in Settings if tubes are missed or falsely detected

---

### Live Camera Stream

**Purpose:** Real-time continuous inference — each frame is analyzed as it arrives.

**How to use:**

1. Navigate to the **Stream** view (camera icon).
2. Tap **Start Stream**.
3. The annotated feed appears with detection overlays and MPN results updating in real time.
4. Tap **Stop Stream** to end.

**Two camera modes** (configured in Settings):

| Mode | Description |
|---|---|
| **Client (Webcam)** | Browser captures frames from your device's webcam. Works on phones, tablets, and laptops. |
| **Server (Pi Camera)** | Server captures from the Raspberry Pi camera or USB camera. Browser only displays results. |

> The correct mode is selected automatically based on the platform (server mode on Pi, client mode on other devices). You can override this in Settings.

---

### History

**Purpose:** Browse all past prediction results with annotated images and export data.

**How to use:**

1. Navigate to the **History** view (clock icon).
2. Past predictions are shown as cards with:
   - Timestamp
   - Annotated thumbnail
   - MPN value and risk level
3. Tap a card to open the **detail modal** showing the full tube breakdown, detection list, and annotated image.
4. Tap the **delete** button on a card to remove that record (also deletes the saved image file).
5. Tap **Export CSV** to download all history as a spreadsheet.

**Notes:**
- History is automatically pruned to the most recent 500 records.
- Records persist across server restarts (stored in `data/vialvision.db`).

---

### MPN Guideline

**Purpose:** Reference table showing all 40 MPN patterns and their contamination values.

**How to use:**

1. Navigate to the **Guideline** view (book icon).
2. The table lists every valid pattern (`P000`–`P333`) with:
   - Tube pattern (e.g. `2-1-0`)
   - MPN per gram
   - 95% confidence interval (low–high)
3. Use this to manually verify a result or understand the detection-to-MPN mapping.

**Reading the pattern:**
- Pattern `P210` means: 2 positives in dilution group 1, 1 in group 2, 0 in group 3
- Tubes are grouped left-to-right (tubes 1–3, 4–6, 7–9)
- **Yellow + bubble = positive (1)**, everything else = negative (0)

---

### Settings

**Purpose:** Configure camera, streaming, and detection parameters. All settings are saved automatically and persist across restarts.

**How to use:**

1. Navigate to the **Settings** view (gear icon).
2. Adjust any setting — changes are saved to the database automatically (600 ms after the last change).

**Available settings:**

| Setting | Description |
|---|---|
| **Camera Source** | `Client (Webcam)` uses the browser's camera. `Server (Pi Camera)` uses the Raspberry Pi or USB camera. |
| **Resolution** | Frame resolution for streaming: 320×240, 640×480, or 1280×720 |
| **FPS** | Frames per second for the live stream (1–30) |
| **Confidence Threshold** | Minimum detection confidence (0.05–0.95). Lower = more detections, higher = fewer false positives. |
| **Flip Horizontal** | Mirror the camera feed horizontally |
| **Device IP Address** | Displays the server device's current LAN IP address (read-only) |

**Notes:**
- Settings are saved per-device (stored in the server's database, not the browser)
- The camera source default is set automatically: **Server** on Raspberry Pi, **Client** on Windows/Mac

---

## Raspberry Pi Autostart

VialVision can start automatically on boot (no keyboard/mouse needed after power on).

**One-time setup:**

```bash
bash scripts/rpi_setup_autostart.sh
sudo reboot
```

After reboot, the Pi will:
1. Start the HTTPS server in the background
2. Open Chromium in fullscreen at `https://<LAN-IP>:8000`

See [raspberry_pi_startup_guide.md](raspberry_pi_startup_guide.md) for full details, troubleshooting, and how to disable autostart.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Could not open camera source" | On Windows, make sure no other app is using the webcam. Check privacy settings allow camera access. |
| Image captured by Pi camera is too zoomed in | Ensure camera is mounted ~19 cm above the rack |
| Image is blurry (Pi camera) | Camera Module 3: autofocus is enabled, wait 2–3 s after mounting. CM1/CM2: fixed focus, ensure lighting is good |
| Wrong colors in captured image | Ensure you are running the latest version (camera pipeline was fixed 2026-04-19) |
| Certificate warning in browser | Click Advanced → Proceed to accept the self-signed certificate. Only needed once per browser. |
| MPN shows `N/A` | The model detected ≠ 9 tubes. Adjust the camera angle, lighting, or confidence threshold. |
| Server shows 500 error on `/` | Check `requirements.txt` dependencies are installed correctly; run `pip install -r requirements.txt` |
| WebSocket fails to connect | Install WebSocket support: `pip install websockets` (or `pip install "uvicorn[standard]"`) |
| History is empty after restart | The database is stored at `data/vialvision.db`. Do not delete this file. |
| Phone camera does not work | HTTPS is required for `getUserMedia`. Make sure the server is running with `--ssl-keyfile key.pem --ssl-certfile cert.pem` and you have accepted the certificate warning. |
