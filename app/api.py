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

    # --- MPN integration (NEW) ---
    from .inference import detections_to_tubes, tubes_to_xyz
    from .mpn.mpn_lookup import lookup_mpn

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
    
    # Import here to avoid circular dependencies if any, or just convenience
    from .camera import Camera
    import asyncio
    import cv2
    import numpy as np

    # Server-side camera instance (singleton-ish for this connection)
    camera = Camera()
    
    try:
        while True:
            # Check for messages (non-blocking if possible, but receive is blocking)
            # We need to handle two cases: 
            # TOPIC 1: Client sends image (Client Mode)
            # TOPIC 2: Client sends status/command (Server Mode)
            
            # Since fastAPI receive is async, we can wait for it.
            # But in Server Mode, we need to push images without waiting for input.
            # So we use asyncio.wait_for with a timeout to allow a loop.
            
            try:
                # Wait for a message with a short timeout
                data = await asyncio.wait_for(websocket.receive(), timeout=0.05)
                
                if data["type"] == "websocket.disconnect":
                    break
                
                if "bytes" in data:
                    # CLIENT MODE: Received image bytes
                    image_bytes = data["bytes"]
                    detections, annotated_img_bytes = inference.run_inference_with_count(image_bytes)
                    img_b64 = base64.b64encode(annotated_img_bytes).decode('utf-8')
                    await websocket.send_json({
                        "mode": "client",
                        "detections": detections,
                        "image": img_b64
                    })
                elif "text" in data:
                    # Control message (e.g., {"action": "start_server_stream", "resolution": "640x480"})
                    import json
                    msg = json.loads(data["text"])
                    if msg.get("action") == "start_server_stream":
                        # Start Camera
                        if not camera.is_running:
                            camera.start(0) # Default to 0 for Pi/Webcam
                            
                    elif msg.get("action") == "stop_server_stream":
                        camera.stop()
                        
            except asyncio.TimeoutError:
                # No message from client, check if we should stream from server
                if camera.is_running:
                    frame = camera.get_frame()
                    if frame is not None:
                        # Convert BGR (OpenCV) to RGB (for Pillow) or keep BGR if inference expects it
                        # YOLO internal usually handles it, but inference.py uses PIL.Image.open(io.BytesIO(bytes))
                        # So we need to encode frame to jpg bytes
                        success, encoded_img = cv2.imencode('.jpg', frame)
                        if success:
                            image_bytes = encoded_img.tobytes()
                            detections, annotated_img_bytes = inference.run_inference_with_count(image_bytes)
                            img_b64 = base64.b64encode(annotated_img_bytes).decode('utf-8')
                            
                            await websocket.send_json({
                                "mode": "server",
                                "detections": detections,
                                "image": img_b64
                            })
                            
                    # Control FPS slightly
                    await asyncio.sleep(0.05) # ~20 FPS max loop
                    
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
