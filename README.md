# Raspberry Pi YOLO Object Detection Demo

This project is a lightweight, real-time object detection system designed for the Raspberry Pi 4. It uses the **YOLOv8 Nano** model to provide fast inference with a modern web interface.

## 🚀 Features

*   **Fast Inference**: Uses `yolov8n` (Nano version) optimized for speed on edge devices.
*   **Web Interface**: Simple, responsive UI for uploading images and viewing results.
*   **Real-time WebSocket Streaming**: Supports continuous inference via WebSockets.
*   **Camera Integration**: Can capture from the Raspberry Pi Camera or USB webcam directly on the server.
*   **API-First Design**: Backend logic is exposed via standard REST and WebSocket endpoints.

## 🛠 Tech Stack

*   **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
*   **AI Model**: [Ultralytics YOLOv8](https://docs.ultralytics.com/)
*   **Computer Vision**: OpenCV (`cv2`), Pillow (`PIL`)
*   **Frontend**: HTML5, JavaScript (Vanilla), CSS
*   **Server**: Uvicorn (ASGI)

## 📂 Project Structure

```
├── app/
│   ├── main.py         # Entry point, mounts static files and API
│   ├── api.py          # API Routes (REST endpoints & WebSocket logic)
│   ├── inference.py    # YOLOv8 model loading and inference logic
│   └── camera.py       # Camera handling for server-side streaming
├── static/             # CSS and JavaScript files
├── templates/          # HTML templates
├── requirements.txt    # Python dependencies
├── raspberry_pi_startup_guide.md # Instructions for auto-start on Pi
└── README.md           # This file
```

## ⚡ How It Works

### Flow 1: Image Upload (REST API)
1.  User selects an image in the Web UI.
2.  Image is sent to `POST /predict`.
3.  Server processes image through YOLOv8n.
4.  Server returns JSON detections + Base64 annotated image.
5.  UI displays the result.

### Flow 2: Real-time Camera (WebSocket)
1.  Frontend connects to `ws://server/ws`.
2.  **Client Mode**: Browser sends camera frames -> Server predicts -> Returns annotated frame.
3.  **This allows testing the "Pi Camera" experience even from a laptop.**

## 🏃‍♂️ Getting Started

### Prerequisites
*   Python 3.9+
*   A webcam (optional, for streaming)

### Local Setup
1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the Server**:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```
3.  **Access the UI**:
    Open [http://localhost:8000](http://localhost:8000) in your browser.

### Raspberry Pi Deployment
For instructions on running this on a Raspberry Pi 4, including auto-start configuration, see [raspberry_pi_startup_guide.md](raspberry_pi_startup_guide.md).

## 📊 Model Details

The project uses the **COCO pretrained YOLOv8 Nano** model, which can detect **80 classes** of objects including:
*   Person
*   Vehicles (Car, Bus, Bicycle...)
*   Animals (Dog, Cat, Bird...)
*   Household items (Chair, Bottle, Laptop...)
