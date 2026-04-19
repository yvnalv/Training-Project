#!/bin/bash
# rpi_autostart.sh
# Launched at login by the XDG autostart entry (vialvision.desktop).
# Steps:
#   1. Wait for the desktop environment to fully initialise.
#   2. Start the uvicorn server in the background (logs → server.log).
#   3. Detect the connected network IP; fall back to localhost.
#   4. Poll until the server is accepting HTTPS connections.
#   5. Open Chromium in full-screen at the correct URL.

PROJECT_DIR="/home/pi/yvnalv/projects/Training-Project"
LOG_FILE="$PROJECT_DIR/server.log"

# ── 1. Give the Wayfire compositor time to finish starting ───────
sleep 8

# ── 2. Start server in background, all output → server.log ───────
echo "--- VialVision boot $(date) ---" >> "$LOG_FILE"
bash "$PROJECT_DIR/scripts/rpi_start_server.sh" >> "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID" >> "$LOG_FILE"

# ── 3. Resolve target URL ─────────────────────────────────────────
# hostname -I returns all interface IPs space-separated; take the first
# non-loopback one (WiFi or Ethernet).
IP=$(hostname -I 2>/dev/null | awk '{print $1}' | tr -d '[:space:]')

if [ -n "$IP" ]; then
    URL="https://$IP:8000"
else
    URL="https://localhost:8000"
fi

echo "Target URL: $URL" >> "$LOG_FILE"

# ── 4. Wait for the server to accept connections (max 90 s) ───────
READY=0
for i in $(seq 1 90); do
    if curl -k --silent --max-time 2 "$URL" > /dev/null 2>&1; then
        echo "Server ready after ${i}s." >> "$LOG_FILE"
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -eq 0 ]; then
    echo "Warning: server did not respond within 90 s. Opening browser anyway." >> "$LOG_FILE"
fi

# ── 5. Open Chromium in full-screen ──────────────────────────────
# Try chromium-browser first (standard name on Raspberry Pi OS),
# fall back to 'chromium' if not found.
CHROMIUM_CMD=""
if command -v chromium-browser &> /dev/null; then
    CHROMIUM_CMD="chromium-browser"
elif command -v chromium &> /dev/null; then
    CHROMIUM_CMD="chromium"
else
    echo "Error: Chromium not found. Install with: sudo apt install chromium-browser" >> "$LOG_FILE"
    exit 1
fi

"$CHROMIUM_CMD" \
    --start-fullscreen \
    --ignore-certificate-errors \
    --test-type \
    --disable-restore-session-state \
    --noerrdialogs \
    --disable-infobars \
    "$URL" >> "$LOG_FILE" 2>&1
