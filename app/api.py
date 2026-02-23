import asyncio
import base64
import json
import logging

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import inference
from .camera import Camera
from .inference import detections_to_tubes, tubes_to_xyz
from .mpn.mpn_lookup import lookup_mpn

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helper: MPN calculation (extracted to eliminate copy-paste in WS handler)
# ---------------------------------------------------------------------------

def _compute_mpn(detections: list, total_count: int) -> dict:
    """
    Given a list of detections and the tube count, return a dict of MPN fields.
    If total_count != 9, all MPN fields are returned as None so the caller can
    still send a well-formed response without crashing.
    """
    if total_count != 9:
        return {
            "tubes": [],
            "pattern": None,
            "mpn": None,
            "ci_low": None,
            "ci_high": None,
        }

    tubes = detections_to_tubes(detections)  # safe: we checked count == 9
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
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/health")
async def health():
    return {"status": "ok", "model": "yolov8n"}


@router.post("/predict")
async def predict(
    file: UploadFile,
    conf: float = Form(default=0.4),  # FIX: accept confidence from frontend form data
):
    image_bytes = await file.read()

    detections, total_count, annotated_img_bytes = inference.run_inference_with_count(
        image_bytes, conf=conf  # FIX: pass through instead of using hardcoded 0.4
    )

    if total_count != 9:
        logger.warning(
            "/predict: expected 9 tubes, got %d. Returning result without MPN.",
            total_count,
        )

    img_b64 = base64.b64encode(annotated_img_bytes).decode("utf-8")
    mpn = _compute_mpn(detections, total_count)

    return JSONResponse(content={
        "detections": detections,
        "total_tubes": total_count,
        "tubes": mpn["tubes"],
        "pattern": mpn["pattern"],
        "mpn": mpn["mpn"],
        "ci_low": mpn["ci_low"],
        "ci_high": mpn["ci_high"],
        "image": img_b64,
    })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    camera = Camera()

    # Per-session confidence — updated by the frontend set_conf message
    session_conf: float = 0.4

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=0.05)

                if data["type"] == "websocket.disconnect":
                    break

                # ---------------------------------------------------------
                # CLIENT MODE — browser sends raw camera frames
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
                # CONTROL MESSAGES — start/stop server camera, update conf
                # ---------------------------------------------------------
                elif "text" in data:
                    msg = json.loads(data["text"])

                    if msg.get("action") == "start_server_stream":
                        if not camera.is_running:
                            # FIX: parse resolution from the message and pass
                            # it to camera.start() — previously this was ignored
                            # and the camera always defaulted to 640x480.
                            resolution = msg.get("resolution", "640x480")
                            try:
                                width, height = map(int, resolution.split("x"))
                            except ValueError:
                                width, height = 640, 480
                                logger.warning("Invalid resolution '%s', using 640x480.", resolution)
                            camera.start(0, width=width, height=height)

                    elif msg.get("action") == "stop_server_stream":
                        camera.stop()

                    elif msg.get("action") == "set_conf":
                        # FIX: frontend confidence slider now updates inference
                        # in real time by sending this message on slider change.
                        try:
                            session_conf = float(msg.get("value", 0.4))
                            logger.debug("Session confidence updated to %.2f", session_conf)
                        except (TypeError, ValueError):
                            logger.warning("Invalid conf value received: %s", msg.get("value"))

            except asyncio.TimeoutError:
                # ---------------------------------------------------------
                # SERVER MODE — Pi camera, polled on timeout
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
        logger.info("WebSocket: client disconnected normally.")

    except Exception:
        # FIX: use logging.exception so the full traceback appears in logs,
        # not just a one-line print with no stack trace.
        logger.exception("WebSocket: unexpected error.")

    finally:
        camera.stop()
        try:
            await websocket.close()
        except Exception:
            pass  # already closed — nothing to do