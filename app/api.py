import asyncio
import base64
import json
import logging

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
    return templates.TemplateResponse("index.html", {"request": request})


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
                            try:
                                width, height = map(int, resolution.split("x"))
                            except ValueError:
                                width, height = 640, 480
                                logger.warning(
                                    "Invalid resolution '%s', using 640x480.", resolution
                                )
                            camera.start(0, width=width, height=height)

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