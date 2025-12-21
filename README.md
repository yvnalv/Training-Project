# VialVision

**VialVision** is a Raspberry Pi–based **edge-AI computer vision system** for real-time **detection, classification, and measurement of test tube outputs** using deep learning and computer vision techniques.

The system runs fully on-device (edge), enabling low-latency inference without relying on cloud resources.

---

## Features

- Image input via **camera module or image upload**
- **Deep learning–based object detection** (bounding box, label, confidence)
- **Measurement of test tube output** (e.g. level, presence, condition)
- **Edge inference** optimized for Raspberry Pi
- **Web interface** for user interaction
- **REST API** for system integration
- Modular and extensible architecture

---

## System Architecture

```text
┌──────────────┐
│   Camera /   │
│ Image Upload │
└──────┬───────┘
       │
       ▼
┌────────────────────┐
│ Raspberry Pi (Edge)│
│  - CV / YOLO Model │
│  - Inference Logic │
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│ FastAPI Web Server │
│  - REST Endpoints  │
│  - Prediction API │
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│   Web Interface    │
│  - Upload Image   │
│  - Visual Results │
└────────────────────┘
```

---

## Model Overview

- **Task Type**: Object Detection (multi-class)
- **Output**:
  - Bounding boxes
  - Class labels
  - Confidence scores (%)
- **Framework**: Ultralytics YOLO (PyTorch)
- **Deployment**: Edge inference on Raspberry Pi

> The model can be retrained or replaced without modifying the API or UI layers.

---

## Project Structure

```text
VialVision/
│
├── data/
│   ├── raw/              # Raw images
│   ├── labeled/          # Annotated dataset
│   └── samples/          # Sample test images
│
├── model/
│   ├── weights/          # Trained model weights
│   ├── train.py          # Training script
│   └── evaluate.py       # Evaluation script
│
├── app/
│   ├── main.py           # FastAPI entry point
│   ├── inference.py      # Inference logic
│   ├── schemas.py        # Request/response schemas
│   └── utils.py          # Utility functions
│
├── web/
│   ├── templates/        # HTML templates
│   └── static/           # CSS / JS assets
│
├── requirements.txt
├── README.md
└── LICENSE
```

---

## Installation

### 1️. Clone the Repository

```bash
git clone https://github.com/your-username/VialVision.git
cd VialVision
```

### 2️. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
```

### 3️. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Running the Application

### Start FastAPI Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Access Web Interface

```text
http://<raspberry-pi-ip>:8000
```

---

## API Endpoints

### 🔹 Health Check

```http
GET /
```

### 🔹 Image Prediction

```http
POST /predict
```

**Request**
- Multipart form-data
- Image file (`.jpg`, `.png`)

**Response**

```json
{
  "detections": [
    {
      "label": "test_tube",
      "confidence": 0.93,
      "bbox": [x, y, width, height]
    }
  ]
}
```

---

## Hardware Requirements

- Raspberry Pi 4 (recommended)
- Raspberry Pi Camera Module
- Vial or Test Tube Holder Set
- 16–32 GB microSD card
- Stable power supply
- Internet connection (setup only)

---

## Use Cases

- Laboratory automation
- Test tube output inspection
- Quality control and verification
- Edge AI experimentation
- Research and academic projects

---

## Roadmap

- [ ] Live camera stream inference
- [ ] Measurement calibration module
- [ ] Model quantization (INT8)
- [ ] Docker support
- [ ] Analytics dashboard
- [ ] Multi-device support

---

## Author

**Yovan Alvianto**  
Data Scientist & Software Engineer

---

## Acknowledgements

- Ultralytics YOLO
- FastAPI
- Raspberry Pi Foundation
