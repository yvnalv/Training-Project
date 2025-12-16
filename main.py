from fastapi import FastAPI, UploadFile, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import inference
import base64

app = FastAPI()

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok", "model": "yolov8n"}

@app.post("/predict")
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

@app.websocket("/ws")
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
