import asyncio
import base64
import importlib
import io
import json
import logging
import sys

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


# ---------------------------------------------------------------------------
# Helper: MPN calculation
# ---------------------------------------------------------------------------

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
    return templates.TemplateResponse(request, "index.html")


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
):
    image_bytes = await file.read()

    detections, total_count, annotated_img_bytes = inference.run_inference_with_count(
        image_bytes, conf=conf
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

def _platform_info() -> dict:
    """Return platform detection hints used by the frontend to pick defaults."""
    is_linux = sys.platform.startswith("linux")
    try:
        importlib.import_module("picamera2")
        has_picamera2 = True
    except Exception:
        has_picamera2 = False
    return {
        "is_raspi": is_linux and has_picamera2,
        "has_picamera2": has_picamera2,
        "default_camera_mode": "server" if has_picamera2 else "client",
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
    return JSONResponse(content={**_platform_info(), "settings": saved})


@router.put("/settings")
async def put_settings_endpoint(request: Request):
    """
    Upsert UI settings. Accepts a JSON body of {key: value} pairs.
    Only known setting keys are persisted; unknown keys are silently ignored.
    """
    ALLOWED_KEYS = {"cameraMode", "fps", "resolution", "confidence", "flipHorizontal"}
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

        # Wait up to 3 s for the capture thread to produce a frame
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

            except asyncio.TimeoutError:
                # ---------------------------------------------------------
                # SERVER MODE
                # ---------------------------------------------------------
                if not camera.is_running:
                    continue

                frame = camera.get_frame()
                if frame is None:
                    continue

                success, encoded_img = cv2.imencode(".jpg", frame)
                if not success:
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