from fastapi import APIRouter, UploadFile, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import base64
from . import inference
from .mpn.mpn_lookup import lookup_mpn
from .inference import detections_to_tubes, tubes_to_xyz

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/health")
async def health():
    return {"status": "ok", "model": "yolov8n"}

@router.post("/predict")
async def predict(file: UploadFile):
    # Read image bytes
    image_bytes = await file.read()
    
    # Run inference
    detections, total_count, annotated_img_bytes = inference.run_inference_with_count(image_bytes)
    
    # Encode image to base64 for easy frontend display
    img_b64 = base64.b64encode(annotated_img_bytes).decode('utf-8')

    tubes = detections_to_tubes(detections)   # [0,1,0,1,...] length = 9
    x, y, z = tubes_to_xyz(tubes)              # positives per dilution
    mpn_result = lookup_mpn(x, y, z)            # lookup from CSV

    return JSONResponse(content={
        "detections": detections,
        "total_tubes": total_count,
        "tubes": tubes,                 # e.g. [1,0,1, 0,1,0, 0,0,1]
        "pattern": mpn_result["pattern"],# e.g. P101
        "mpn": mpn_result["mpn"],        # MPN/g
        "ci_low": mpn_result["low"],     # 95% CI low
        "ci_high": mpn_result["high"],   # 95% CI high
        "image": img_b64
    })


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    from .camera import Camera
    import asyncio
    import cv2
    import numpy as np
    from .inference import detections_to_tubes, tubes_to_xyz
    from .mpn.mpn_lookup import lookup_mpn

    camera = Camera()
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=0.05)
                
                if data["type"] == "websocket.disconnect":
                    break
                
                # -------------------------
                # CLIENT MODE
                # -------------------------
                if "bytes" in data:
                    image_bytes = data["bytes"]

                    detections, total_count, annotated_img_bytes = \
                        inference.run_inference_with_count(image_bytes)

                    img_b64 = base64.b64encode(
                        annotated_img_bytes
                    ).decode('utf-8')

                    # ---- MPN Integration ----
                    tubes = []
                    pattern = None
                    mpn = None
                    ci_low = None
                    ci_high = None

                    if total_count == 9:
                        tubes = detections_to_tubes(detections)
                        x, y, z = tubes_to_xyz(tubes)
                        mpn_result = lookup_mpn(x, y, z)

                        pattern = mpn_result["pattern"]
                        mpn = mpn_result["mpn"]
                        ci_low = mpn_result["low"]
                        ci_high = mpn_result["high"]

                    await websocket.send_json({
                        "mode": "client",
                        "detections": detections,
                        "total_tubes": total_count,
                        "tubes": tubes,
                        "pattern": pattern,
                        "mpn": mpn,
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                        "image": img_b64
                    })

                # -------------------------
                # CONTROL MESSAGES
                # -------------------------
                elif "text" in data:
                    import json
                    msg = json.loads(data["text"])

                    if msg.get("action") == "start_server_stream":
                        if not camera.is_running:
                            camera.start(0)
                            
                    elif msg.get("action") == "stop_server_stream":
                        camera.stop()
                        
            except asyncio.TimeoutError:
                # -------------------------
                # SERVER MODE (Raspberry Pi)
                # -------------------------
                if camera.is_running:
                    frame = camera.get_frame()

                    if frame is not None:
                        success, encoded_img = cv2.imencode('.jpg', frame)

                        if success:
                            image_bytes = encoded_img.tobytes()

                            detections, total_count, annotated_img_bytes = \
                                inference.run_inference_with_count(image_bytes)

                            img_b64 = base64.b64encode(
                                annotated_img_bytes
                            ).decode('utf-8')

                            # ---- MPN Integration ----
                            tubes = []
                            pattern = None
                            mpn = None
                            ci_low = None
                            ci_high = None

                            if total_count == 9:
                                tubes = detections_to_tubes(detections)
                                x, y, z = tubes_to_xyz(tubes)
                                mpn_result = lookup_mpn(x, y, z)

                                pattern = mpn_result["pattern"]
                                mpn = mpn_result["mpn"]
                                ci_low = mpn_result["low"]
                                ci_high = mpn_result["high"]

                            await websocket.send_json({
                                "mode": "server",
                                "detections": detections,
                                "total_tubes": total_count,
                                "tubes": tubes,
                                "pattern": pattern,
                                "mpn": mpn,
                                "ci_low": ci_low,
                                "ci_high": ci_high,
                                "image": img_b64
                            })
                            
                    await asyncio.sleep(0.05)
                    
    except WebSocketDisconnect:
        print("Client disconnected")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        camera.stop()
        try:
            await websocket.close()
        except:
            pass