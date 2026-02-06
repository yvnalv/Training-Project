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


def suppress_duplicate_tubes(detections, x_thresh_ratio=0.4):
    """
    Removes duplicate detections that belong to the same physical tube
    based on horizontal (x-axis) proximity.
    Keeps the highest-confidence detection per tube.
    """
    if not detections:
        return []

    # Compute average tube width dynamically
    widths = [d["bbox"][2] - d["bbox"][0] for d in detections]
    avg_width = sum(widths) / len(widths)
    x_thresh = avg_width * x_thresh_ratio

    # Sort left → right
    detections = sorted(detections, key=lambda d: d["bbox"][0])
    filtered = []

    for det in detections:
        cx = (det["bbox"][0] + det["bbox"][2]) / 2

        if not filtered:
            filtered.append(det)
            continue

        prev = filtered[-1]
        prev_cx = (prev["bbox"][0] + prev["bbox"][2]) / 2

        # Same tube → keep higher confidence
        if abs(cx - prev_cx) < x_thresh:
            if det["confidence"] > prev["confidence"]:
                filtered[-1] = det
        else:
            filtered.append(det)

    return filtered

def detections_to_tubes(detections):
    """
    Convert ordered detections (left → right) into 9 tube values (0/1).

    Rule:
      Yellow_NoBubble → 1 (positive)
      otherwise → 0
    """
    tubes = []

    for d in detections:
        value = 1 if d["label"] == "Yellow_NoBubble" else 0
        tubes.append(value)

    if len(tubes) != 9:
        raise ValueError(f"Expected 9 tubes, got {len(tubes)}")

    return tubes

def tubes_to_xyz(tubes):
    """
    Convert 9 tubes into MPN (x, y, z) counts.
    """
    x = sum(tubes[0:3])  # 0.1 g
    y = sum(tubes[3:6])  # 0.01 g
    z = sum(tubes[6:9])  # 0.001 g
    return x, y, z

def run_inference_with_count(image_bytes: bytes):
    """
    Returns:
      detections (list)
      total_count (int)  # EXACT number of predicted boxes
      annotated_image_bytes (bytes)
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results = model(image,conf=0.4, iou=0.6, agnostic_nms=True)
    
    result = results[0]

    boxes = result.boxes

    detections = []
    if boxes is not None and len(boxes) > 0:
        for b in boxes:
            detections.append({
                "label": result.names[int(b.cls)],
                "confidence": float(b.conf),
                "bbox": b.xyxy.tolist()[0]
            })

    # ✅ NEW: suppress duplicate tubes
    detections = suppress_duplicate_tubes(detections)

    # ✅ NEW: source of truth AFTER de-duplication
    total_count = len(detections)

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