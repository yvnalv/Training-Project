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
      total_count (int)
      annotated_image_bytes (bytes)
    """

    # ---- Load image ----
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # ---- Downscale (50%) ----
    scale_factor = 0.2
    new_w = int(image.width * scale_factor)
    new_h = int(image.height * scale_factor)

    image = image.resize((new_w, new_h), Image.LANCZOS)

    # ---- Run YOLO ----
    results = model(image, conf=0.4, iou=0.6, agnostic_nms=True)
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

    # Remove duplicate tubes
    detections = suppress_duplicate_tubes(detections)
    total_count = len(detections)

    # ---- Drawing Setup ----
    im = image.copy()
    draw = ImageDraw.Draw(im)

    img_width, img_height = im.size

    # Proportional thickness
    box_thickness = max(3, img_width // 220)

    # Estimate tube height
    if detections:
        sample_box = detections[0]["bbox"]
        tube_height = int(sample_box[3] - sample_box[1])
    else:
        tube_height = img_height // 4

    # Proportional font
    font_size = int(tube_height * 0.30)
    font_size = max(60, font_size)

    try:
        font = ImageFont.truetype(
            "fonts/DejaVuSans-Bold.ttf",
            font_size
        )
    except:
        font = ImageFont.load_default()

    padding = font_size // 4

    # ---- Draw Detections ----
    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])

        if det["label"] == "Yellow_NoBubble":
            label_text = "1"
            color = (0, 180, 0)
        else:
            label_text = "0"
            color = (120, 120, 120)

        # Draw box
        draw.rectangle([x1, y1, x2, y2],
                       outline=color,
                       width=box_thickness)

        # Text size
        text_bbox = draw.textbbox((0, 0), label_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        # Position top-left inside box
        text_x = x1 + padding
        text_y = y1 + padding

        # Background
        draw.rectangle(
            [
                text_x - padding,
                text_y - padding,
                text_x + text_w + padding,
                text_y + text_h + padding
            ],
            fill=color
        )

        # Text
        draw.text((text_x, text_y),
                  label_text,
                  fill=(255, 255, 255),
                  font=font)

    # ---- Draw Total Tubes (Bottom Right of Image) ----
    count_text = f"Total Tubes: {total_count}"

    count_bbox = draw.textbbox((0, 0), count_text, font=font)
    count_w = count_bbox[2] - count_bbox[0]
    count_h = count_bbox[3] - count_bbox[1]

    margin = 30

    count_x = img_width - count_w - padding*2 - margin
    count_y = img_height - count_h - padding*2 - margin

    draw.rectangle(
        [
            count_x,
            count_y,
            count_x + count_w + padding*2,
            count_y + count_h + padding*2
        ],
        fill=(0, 0, 0)
    )

    draw.text(
        (count_x + padding, count_y + padding),
        count_text,
        fill=(255, 255, 255),
        font=font
    )

    # ---- Convert to JPEG ----
    buf = io.BytesIO()
    im.save(buf, format="JPEG")

    return detections, total_count, buf.getvalue()
