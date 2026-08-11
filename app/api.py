import asyncio
import base64
import importlib
import io
import json
import logging
import os
import socket
import sys
import time

from PIL import Image as _PIL_Image

import cv2
from fastapi import APIRouter, UploadFile, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from . import inference
from .camera import Camera
from .db.queries import (
    save_prediction,
    list_predictions,
    count_predictions,
    delete_prediction,
    export_csv,
    get_all_settings,
    set_settings,
)
from .inference import detections_to_tubes, tubes_to_xyz
from .mpn.mpn_lookup import lookup_mpn

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Static-asset cache-buster. Stamped onto style.css / script.js URLs in index.html as
# ?v=<this>. It's the process start time, so it changes on every container restart (i.e.
# every deploy recreates the container) — the browser then fetches fresh JS/CSS instead of
# serving stale cached copies. Stable within a single container's life, so normal caching
# still works between deploys. Replaces the old hand-bumped ?v=N (which was easy to forget).
_ASSET_VERSION = str(int(time.time()))


# Live-stream throttle (see docs/STREAM_PERFORMANCE.md, Option B). On a slow CPU,
# processing every frame builds an ever-growing latency backlog. We cap inference to
# a maximum rate and DROP frames that arrive sooner — always processing the most
# recent one — so displayed latency stays bounded. Tune via VIALVISION_STREAM_MAX_FPS
# (frames/sec); <=0 disables the cap.
try:
    _STREAM_MAX_FPS = float(os.getenv("VIALVISION_STREAM_MAX_FPS", "10"))
except ValueError:
    _STREAM_MAX_FPS = 10.0
_STREAM_MIN_INTERVAL = 1.0 / _STREAM_MAX_FPS if _STREAM_MAX_FPS > 0 else 0.0


# ---------------------------------------------------------------------------
# Helper: MPN calculation
# ---------------------------------------------------------------------------

def _active_rois():
    """
    Return the 9 saved ROI boxes if fixed-ROI (jig) mode is ON and calibrated to exactly
    9 valid boxes; otherwise None (caller falls back to full-frame detection).

    ROIs are stored in settings as `roiBoxes` (JSON string: 9× normalised [x1,y1,x2,y2],
    tube order) with `roiMode` truthy. See docs/FIXED_ROI_DESIGN.md.
    """
    try:
        s = get_all_settings()
    except Exception:
        return None
    if str(s.get("roiMode", "")).strip().lower() not in ("1", "true", "on", "yes"):
        return None
    raw = s.get("roiBoxes")
    if not raw:
        return None
    try:
        boxes = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    if not isinstance(boxes, list) or len(boxes) != 9:
        return None
    for b in boxes:
        if not (isinstance(b, (list, tuple)) and len(b) == 4):
            return None
    return boxes


def _compute_mpn(detections: list, total_count: int) -> dict:
    """
    Return MPN fields for a given detection list.
    If total_count != 9, all MPN fields are None — no crash.
    """
    if total_count != 9:
        return {
            "tubes": [],
            "pattern": None,
            "mpn": None,
            "ci_low": None,
            "ci_high": None,
        }

    tubes = detections_to_tubes(detections)
    x, y, z = tubes_to_xyz(tubes)
    result = lookup_mpn(x, y, z)

    return {
        "tubes": tubes,
        "pattern": result["pattern"],
        "mpn": result["mpn"],
        "ci_low": result["low"],
        "ci_high": result["high"],
    }


# ---------------------------------------------------------------------------
# REST — pages
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"v": _ASSET_VERSION})


@router.get("/health")
async def health():
    return {"status": "ok", "model": "best.pt"}


# ---------------------------------------------------------------------------
# REST — prediction
# ---------------------------------------------------------------------------

@router.post("/predict")
async def predict(
    file: UploadFile,
    conf: float = Form(default=0.4),
    full: bool = Form(default=False),   # True = full-res (Aim & Capture); else 50% downscale
):
    image_bytes = await file.read()

    # Fixed-ROI (jig) mode takes precedence when calibrated: classify the 9 known tube
    # positions instead of detecting them (always full-res crops). See FIXED_ROI_DESIGN.md.
    rois = _active_rois()
    if rois:
        detections, total_count, annotated_img_bytes = inference.run_inference_fixed_roi(
            image_bytes, rois, conf=conf
        )
    else:
        detections, total_count, annotated_img_bytes = inference.run_inference_with_count(
            image_bytes, conf=conf, scale_factor=(1.0 if full else 0.5)
        )

    if total_count != 9:
        logger.warning(
            "/predict: expected 9 tubes, got %d. MPN will be None.", total_count
        )

    img_b64 = base64.b64encode(annotated_img_bytes).decode("utf-8")
    mpn = _compute_mpn(detections, total_count)

    # ---- Persist to database ------------------------------------------------
    # We save regardless of tube count so partial results are also recorded.
    try:
        record_id = save_prediction(
            filename              = file.filename or "unknown",
            total_tubes           = total_count,
            pattern               = mpn["pattern"],
            mpn                   = mpn["mpn"],
            ci_low                = mpn["ci_low"],
            ci_high               = mpn["ci_high"],
            tubes                 = mpn["tubes"],
            detections            = detections,
            annotated_image_bytes = annotated_img_bytes,
        )
        logger.info("/predict saved as record id=%d", record_id)
    except Exception:
        # A DB failure must never crash the predict response.
        # The user still gets their result; we just log the error.
        logger.exception("/predict: failed to save result to database.")
        record_id = None

    return JSONResponse(content={
        "id":          record_id,
        "detections":  detections,
        "total_tubes": total_count,
        "tubes":       mpn["tubes"],
        "pattern":     mpn["pattern"],
        "mpn":         mpn["mpn"],
        "ci_low":      mpn["ci_low"],
        "ci_high":     mpn["ci_high"],
        "image":       img_b64,
    })


# ---------------------------------------------------------------------------
# REST — fixed-ROI calibration (jig mode)
# ---------------------------------------------------------------------------

@router.post("/calibrate")
async def calibrate(file: UploadFile, conf: float = Form(default=0.4)):
    """
    Seed the fixed-ROI positions from a reference frame (jig mode).

    Runs full-frame detection on the uploaded image and returns the detected tube boxes as
    normalised [x1,y1,x2,y2] (0..1), left→right, padded — for the frontend to overlay and
    let the operator confirm/nudge before saving. Does NOT persist; the client saves the
    (possibly edited) boxes via PUT /settings as `roiBoxes`. See docs/FIXED_ROI_DESIGN.md.

    Response: {"rois": [[x1,y1,x2,y2], ...], "count": <int>, "expected": 9}
    """
    image_bytes = await file.read()
    try:
        rois, count = inference.detect_rois_normalized(image_bytes, conf=conf)
    except Exception as e:
        logger.exception("/calibrate: detection failed")
        return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(content={"rois": rois, "count": count, "expected": 9})


# ---------------------------------------------------------------------------
# REST — history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(limit: int = 20, offset: int = 0):
    """
    Return a paginated list of past predictions.

    Query params:
        limit  — records per page  (default 20, max 100)
        offset — records to skip   (default 0)

    Response shape:
        {
            "total":   <int>,
            "limit":   <int>,
            "offset":  <int>,
            "records": [ { ...row } ]
        }
    """
    records = list_predictions(limit=limit, offset=offset)
    total   = count_predictions()

    # Convert stored relative path to a servable URL
    for rec in records:
        if rec.get("image_path"):
            filename = rec["image_path"].split("/")[-1]
            rec["image_url"] = f"/results/{filename}"
        else:
            rec["image_url"] = None

    return JSONResponse(content={
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "records": records,
    })


@router.get("/history/export")
async def export_history():
    """
    Stream all prediction records as a CSV file download.
    """
    csv_text = export_csv()

    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=vialvision_history.csv"
        },
    )


@router.delete("/history/{record_id}")
async def delete_history_record(record_id: int):
    """
    Delete a single prediction record and its image file.
    Returns 404 if the record does not exist.
    """
    deleted = delete_prediction(record_id)

    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"error": f"Record {record_id} not found."},
        )

    return JSONResponse(content={"deleted": record_id})


# ---------------------------------------------------------------------------
# REST — settings (persist UI preferences to DB)
# ---------------------------------------------------------------------------

def _get_network_ip() -> str | None:
    """Return the machine's primary LAN/WiFi IP, or None if offline."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _platform_info() -> dict:
    """Return platform detection hints used by the frontend to pick defaults."""
    is_linux = sys.platform.startswith("linux")
    try:
        importlib.import_module("picamera2")
        has_picamera2 = True
    except Exception:
        has_picamera2 = False
    is_raspi = is_linux and has_picamera2
    return {
        "is_raspi": is_raspi,
        "has_picamera2": has_picamera2,
        "default_camera_mode": "server" if has_picamera2 else "client",
        # Which inference backend actually loaded ("ncnn" = fast CPU path, "pytorch" =
        # slower fallback). Shown as a badge in Settings. See docs/STREAM_PERFORMANCE.md.
        "model_backend": inference.MODEL_BACKEND,
        # Default inference mode: the Pi (NCNN + multiple cores) can do live video;
        # elsewhere (e.g. the 1-vCPU VPS) default to "snapshot" (smooth preview + one
        # accurate capture). User can override in Settings; the choice is persisted.
        "default_inference_mode": "live" if is_raspi else "snapshot",
    }


@router.get("/settings")
async def get_settings_endpoint():
    """
    Return saved UI settings plus platform detection hints.

    Response shape:
        {
            "is_raspi":            bool,
            "has_picamera2":       bool,
            "default_camera_mode": "client" | "server",
            "settings":            { key: value, ... }
        }
    """
    saved = get_all_settings()
    return JSONResponse(content={
        **_platform_info(),
        "network_ip": _get_network_ip(),
        "settings": saved,
    })


@router.put("/settings")
async def put_settings_endpoint(request: Request):
    """
    Upsert UI settings. Accepts a JSON body of {key: value} pairs.
    Only known setting keys are persisted; unknown keys are silently ignored.
    """
    ALLOWED_KEYS = {"cameraMode", "fps", "resolution", "confidence", "flipHorizontal",
                    "inferenceMode",
                    # Fixed-ROI (jig) mode — see docs/FIXED_ROI_DESIGN.md
                    "roiMode", "roiBoxes", "roiCalibratedAt"}
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})

    filtered = {k: v for k, v in body.items() if k in ALLOWED_KEYS}
    set_settings(filtered)
    return JSONResponse(content={"saved": list(filtered.keys())})


# ---------------------------------------------------------------------------
# REST — single-frame server camera capture (for upload analysis)
# ---------------------------------------------------------------------------

@router.get("/capture")
async def capture_frame():
    """
    Capture one frame from the server-side camera (Pi Camera / USB webcam).
    Returns {"image": "<base64 JPEG>"} or {"error": "..."} on failure.
    Used by the frontend when camera source is set to 'server'.
    """
    cam = Camera()
    try:
        cam.start(source=0, width=640, height=480)

        # Phase 1 — wait up to 3 s for the capture thread to produce any frame
        frame = None
        for _ in range(30):
            frame = cam.get_frame()
            if frame is not None:
                break
            await asyncio.sleep(0.1)

        if frame is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Camera not ready — no frame captured within timeout."},
            )

        # Phase 2 — let the camera fully stabilise: autofocus locks on the
        # subject, auto-exposure finds the right level, and any initial
        # colour-balance transients settle.  2 s is enough for CM2/CM3.
        await asyncio.sleep(2.0)
        frame = cam.get_frame()  # grab the now-stable frame

        # Convert BGR (OpenCV) → RGB (PIL) and encode as JPEG with PIL.
        # Using PIL end-to-end avoids any BGR/RGB confusion that can occur
        # when cv2.imencode's libjpeg binding handles channel order on ARM.
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = _PIL_Image.fromarray(frame_rgb)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=92)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return JSONResponse(content={"image": img_b64})

    except Exception as e:
        logger.exception("capture_frame: error")
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        cam.stop()


# ---------------------------------------------------------------------------
# WebSocket — live stream (no DB storage)
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    camera = Camera()
    session_conf: float = 0.4
    # Server-camera inference toggle. True (default) = "live" mode: run inference on every
    # frame. False = "snapshot/preview" mode: stream raw camera frames (smooth, no
    # inference) and only run a full-res reading when a "capture_now" arrives.
    server_infer: bool = True
    last_infer: float = 0.0  # monotonic timestamp of the last processed frame
    # Per-session inference-rate cap (see docs/STREAM_PERFORMANCE.md, Option B).
    # Starts from the env default; the client's "Max FPS" slider overrides it live via
    # a set_fps control message, so the rate is UI-tunable (no redeploy) — useful when
    # the hardware's throughput is unknown (e.g. Raspberry Pi 5 server-camera mode).
    session_min_interval: float = _STREAM_MIN_INTERVAL

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=0.05)

                if data["type"] == "websocket.disconnect":
                    break

                # ---------------------------------------------------------
                # CLIENT MODE
                # ---------------------------------------------------------
                if "bytes" in data:
                    # Throttle: drop frames arriving faster than the FPS cap so a
                    # slow CPU can't build a latency backlog (see Option B docs).
                    now = time.monotonic()
                    if now - last_infer < session_min_interval:
                        continue
                    last_infer = now

                    image_bytes = data["bytes"]
                    detections, total_count, annotated_img_bytes = \
                        inference.run_inference_with_count(image_bytes, conf=session_conf)

                    img_b64 = base64.b64encode(annotated_img_bytes).decode("utf-8")
                    mpn = _compute_mpn(detections, total_count)

                    await websocket.send_json({
                        "mode": "client",
                        "detections": detections,
                        "total_tubes": total_count,
                        **mpn,
                        "image": img_b64,
                    })

                # ---------------------------------------------------------
                # CONTROL MESSAGES
                # ---------------------------------------------------------
                elif "text" in data:
                    msg = json.loads(data["text"])

                    if msg.get("action") == "start_server_stream":
                        # "preview": true → snapshot mode (raw frames, no per-frame
                        # inference). Default false → live inference.
                        server_infer = not bool(msg.get("preview", False))
                        if not camera.is_running:
                            resolution = msg.get("resolution", "640x480")
                            source = msg.get("source", 0)
                            try:
                                width, height = map(int, resolution.split("x"))
                            except ValueError:
                                width, height = 640, 480
                                logger.warning(
                                    "Invalid resolution '%s', using 640x480.", resolution
                                )
                            if isinstance(source, str) and source.isdigit():
                                source = int(source)
                            try:
                                camera.start(source, width=width, height=height)
                            except Exception as e:
                                logger.exception("Failed to start server camera.")
                                await websocket.send_json({"mode": "server", "error": str(e)})

                    elif msg.get("action") == "stop_server_stream":
                        camera.stop()

                    elif msg.get("action") == "set_conf":
                        try:
                            session_conf = float(msg.get("value", 0.4))
                        except (TypeError, ValueError):
                            logger.warning("Invalid conf value: %s", msg.get("value"))

                    elif msg.get("action") == "set_fps":
                        # UI "Max FPS" slider → per-session inference-rate cap. <=0
                        # disables the cap. Governs server-camera mode and backstops
                        # client mode. See docs/STREAM_PERFORMANCE.md (Option B).
                        try:
                            fps = float(msg.get("value", 0))
                            session_min_interval = (1.0 / fps) if fps > 0 else 0.0
                        except (TypeError, ValueError):
                            logger.warning("Invalid fps value: %s", msg.get("value"))

                    elif msg.get("action") == "capture_now":
                        # Aim & Capture (server camera): one FULL-RESOLUTION reading from
                        # the current camera frame. Runs regardless of the FPS throttle.
                        if camera.is_running:
                            frame = camera.get_frame()
                            if frame is not None:
                                ok, enc = cv2.imencode(".jpg", frame)
                                if ok:
                                    rois = _active_rois()
                                    if rois:
                                        dets, cnt, ann = inference.run_inference_fixed_roi(
                                            enc.tobytes(), rois, conf=session_conf
                                        )
                                    else:
                                        dets, cnt, ann = inference.run_inference_with_count(
                                            enc.tobytes(), conf=session_conf, scale_factor=1.0
                                        )
                                    await websocket.send_json({
                                        "mode": "server",
                                        "capture": True,
                                        "detections": dets,
                                        "total_tubes": cnt,
                                        **_compute_mpn(dets, cnt),
                                        "image": base64.b64encode(ann).decode("utf-8"),
                                    })
                        else:
                            await websocket.send_json(
                                {"mode": "server", "error": "Camera not running"}
                            )

            except asyncio.TimeoutError:
                # ---------------------------------------------------------
                # SERVER MODE
                # ---------------------------------------------------------
                if not camera.is_running:
                    continue

                # Throttle: cap inference rate. get_frame() returns the latest frame,
                # so skipping ticks just drops stale frames and keeps latency bounded.
                now = time.monotonic()
                if now - last_infer < session_min_interval:
                    continue

                frame = camera.get_frame()
                if frame is None:
                    continue

                last_infer = now

                success, encoded_img = cv2.imencode(".jpg", frame)
                if not success:
                    continue

                # Snapshot/preview mode: stream the raw camera frame (no inference) so
                # the operator can aim smoothly. The reading runs on "capture_now".
                if not server_infer:
                    await websocket.send_json({
                        "mode": "server",
                        "preview": True,
                        "image": base64.b64encode(encoded_img.tobytes()).decode("utf-8"),
                    })
                    await asyncio.sleep(0.03)
                    continue

                image_bytes = encoded_img.tobytes()
                detections, total_count, annotated_img_bytes = \
                    inference.run_inference_with_count(image_bytes, conf=session_conf)

                img_b64 = base64.b64encode(annotated_img_bytes).decode("utf-8")
                mpn = _compute_mpn(detections, total_count)

                await websocket.send_json({
                    "mode": "server",
                    "detections": detections,
                    "total_tubes": total_count,
                    **mpn,
                    "image": img_b64,
                })

                await asyncio.sleep(0.05)

    except WebSocketDisconnect:
        logger.info("WebSocket: client disconnected.")

    except Exception:
        logger.exception("WebSocket: unexpected error.")

    finally:
        camera.stop()
        try:
            await websocket.close()
        except Exception:
            pass