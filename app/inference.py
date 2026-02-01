from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
import io

# Load the model (downloads automatically if not found)
model = YOLO("best.pt")
# model = YOLO("yolov8n.pt")

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


def run_inference_with_count(image_bytes: bytes):
    """
    Returns:
      detections (list)
      total_count (int)  # EXACT number of predicted boxes
      annotated_image_bytes (bytes)
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results = model(image)
    result = results[0]

    boxes = result.boxes
    total_count = int(len(boxes)) if boxes is not None else 0  # ✅ source of truth

    detections = []
    if boxes is not None and total_count > 0:
        for i in range(total_count):
            b = boxes[i]
            detections.append({
                "label": result.names[int(b.cls)],
                "confidence": float(b.conf),
                "bbox": b.xyxy.tolist()[0]
            })

    # Annotated image from YOLO
    im_array = result.plot()                 # BGR numpy array
    im = Image.fromarray(im_array[..., ::-1])  # RGB PIL

    # Overlay count text
    draw = ImageDraw.Draw(im)
    text = f"Total Tubes: {total_count}"

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
    except:
        font = ImageFont.load_default()

    x, y = 10, 10
    text_bbox = draw.textbbox((x, y), text, font=font)
    draw.rectangle(text_bbox, fill=(0, 0, 0))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    im.save(buf, format="JPEG")

    return detections, total_count, buf.getvalue()