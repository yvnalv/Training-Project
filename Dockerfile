# VialVision — CPU inference web app (FastAPI + Ultralytics YOLO26).
# nginx (see docker-compose.yml) terminates TLS; this container serves plain HTTP.
FROM python:3.11-slim

# System libs needed by opencv-python-headless / numpy / torch
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the CPU-only torch build FIRST, so pip does not pull the ~2.5 GB CUDA
# wheel as an Ultralytics dependency (this is a CPU-only deployment).
RUN pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
# Ultralytics pulls the GUI build of OpenCV (opencv-python), which needs X libs
# (libxcb, libGL, …) absent from slim. Force the headless build instead — same cv2
# module, no GUI dependencies. Keep this as the last OpenCV touched.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y opencv-python opencv-python-headless \
    && pip install --no-cache-dir opencv-python-headless

# Application code, trained model, and web assets
COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY models/ models/

# Runtime data (SQLite DB + annotated result images) — mounted as a volume.
RUN mkdir -p data/results

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
