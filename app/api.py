from fastapi import APIRouter, UploadFile, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import base64
from . import inference

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
    detections, annotated_img_bytes = inference.run_inference(image_bytes)
    
    # Encode image to base64 for easy frontend display
    img_b64 = base64.b64encode(annotated_img_bytes).decode('utf-8')
    
    return JSONResponse(content={
        "detections": detections,
        "image": img_b64
    })

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive image bytes from client
            data = await websocket.receive_bytes()
            
            # Run inference
            detections, annotated_img_bytes = inference.run_inference(data)
            
            # Encode to base64
            img_b64 = base64.b64encode(annotated_img_bytes).decode('utf-8')
            
            # Send results back
            await websocket.send_json({
                "detections": detections,
                "image": img_b64
            })
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        # Try to close if still open, or just break
        try:
            await websocket.close()
        except:
            pass
