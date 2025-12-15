from ultralytics import YOLO
from PIL import Image
import io

# Load the model (downloads automatically if not found)
model = YOLO("yolov8n.pt")

def run_inference(image_bytes: bytes):
    """
    Runs YOLOv8 inference on the provided image bytes.
    Returns:
        detections (list): List of dicts with label, confidence, and box.
        annotated_image_bytes (bytes): The image with bounding boxes drawn, as JPEG.
    """
    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(image_bytes))

    # Run inference
    results = model(image)
    
    # Process results (usually just one result for one image)
    result = results[0]
    
    # Extract detections
    detections = []
    for box in result.boxes:
        d = {
            "label": result.names[int(box.cls)],
            "confidence": float(box.conf),
            "bbox": box.xyxy.tolist()[0] # [x1, y1, x2, y2]
        }
        detections.append(d)
        
    # Get annotated image (numpy array -> PIL -> bytes)
    im_array = result.plot()  # plot() returns BGR numpy array
    im = Image.fromarray(im_array[..., ::-1]) # RGB
    
    img_byte_arr = io.BytesIO()
    im.save(img_byte_arr, format='JPEG')
    return detections, img_byte_arr.getvalue()

if __name__ == "__main__":
    # Simple test if run directly
    print("Model loaded. Run this module via main.py or direct test.")
