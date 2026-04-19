#!/bin/bash
# rpi_start_server.sh
# Activates the virtual environment and starts the VialVision HTTPS server.
# This script is called by rpi_autostart.sh; its stdout/stderr are redirected
# to server.log so it runs silently in the background.

set -e

PROJECT_DIR="/home/pi/yvnalv/projects/Training-Project"
VENV_ACTIVATE="/home/pi/yvnalv/projects/bin/activate"

cd "$PROJECT_DIR"
source "$VENV_ACTIVATE"

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --ssl-keyfile key.pem \
    --ssl-certfile cert.pem
