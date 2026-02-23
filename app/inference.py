import io
import logging
from pathlib import Path

from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# FIX: Use an absolute path derived from this file's own location instead of a
# relative path. The relative "fonts/..." path was resolved from wherever uvicorn
# was launched (the project root), but the fonts/ folder lives inside app/, so
# it never matched. Path(__file__).parent points to the app/ directory regardless
# of where the server is started from.
_FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"

# Load the model once at import time (downloads automatically if not found)
model = YOLO("best.pt")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def suppress_duplicate_tubes(detections, x_thresh_ratio=0.4):
    """
    Removes duplicate detections that belong to the same physical tube
    based on horizontal (x-axis) proximity.
    Keeps the highest-confidence detection per tube.

    NOTE: This is a single left-to-right sweep, so it only merges adjacent
    duplicates. If three or more detections cluster together, the first pair
    is merged but a straggler further right may still pass through. For the
    typical 9-tube layout this has not been a problem in practice, but a
    full grouping pass would be more robust if it becomes one.
    """
    if not detections:
        return []

    widths = [d["bbox"][2] - d["bbox"][0] for d in detections]
    avg_width = sum(widths) / len(widths)
    x_thresh = avg_width * x_thresh_ratio

    detections = sorted(detections, key=lambda d: d["bbox"][0])
    filtered = []

    for det in detections:
        cx = (det["bbox"][0] + det["bbox"][2]) / 2

        if not filtered:
            filtered.append(det)
            continue

        prev = filtered[-1]
        prev_cx = (prev["bbox"][0] + prev["bbox"][2]) / 2

        if abs(cx - prev_cx) < x_thresh:
            if det["confidence"] > prev["confidence"]:
                filtered[-1] = det
        else:
            filtered.append(det)

    return filtered


def detections_to_tubes(detections):
    """
    Convert ordered detections (left -> right) into 9 tube values (0/1).

    Rule:
      Yellow_NoBubble -> 1 (positive)
      otherwise       -> 0 (negative)

    Raises:
        ValueError: if the number of detections is not exactly 9.
    """
    tubes = [1 if d["label"] == "Yellow_NoBubble" else 0 for d in detections]

    if len(tubes) != 9:
        raise ValueError(f"Expected 9 tubes, got {len(tubes)}")

    return tubes


def tubes_to_xyz(tubes):
    """
    Convert 9 tube values into MPN (x, y, z) positive counts.

    Returns:
        x (int): positives in the 0.1 g dilution group (tubes 0-2)
        y (int): positives in the 0.01 g dilution group (tubes 3-5)
        z (int): positives in the 0.001 g dilution group (tubes 6-8)
    """
    return sum(tubes[0:3]), sum(tubes[3:6]), sum(tubes[6:9])


# ---------------------------------------------------------------------------
# Public inference entry point
# ---------------------------------------------------------------------------

def run_inference_with_count(image_bytes: bytes, conf: float = 0.4):
    """
    Full inference pipeline: load image -> downscale -> YOLO -> deduplicate ->
    annotate -> return results.

    Args:
        image_bytes: Raw image file contents (any format PIL can open).
        conf:        YOLO confidence threshold (0.0-1.0). Defaults to 0.4.

    Returns:
        detections (list[dict]): Each dict has 'label', 'confidence', 'bbox'.
        total_count (int):       Number of unique tubes detected after dedup.
        annotated_image (bytes): JPEG image with bounding boxes drawn.
    """
    conf = max(0.05, min(0.95, conf))

    # ---- Load & downscale image (50%) ----
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    scale_factor = 0.5
    new_w = int(image.width * scale_factor)
    new_h = int(image.height * scale_factor)
    image = image.resize((new_w, new_h), Image.LANCZOS)

    # ---- Run YOLO ----
    results = model(image, conf=conf, iou=0.6, agnostic_nms=True)
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

    # ---- Remove duplicate tubes ----
    detections = suppress_duplicate_tubes(detections)
    total_count = len(detections)

    # ---- Drawing setup ----
    im = image.copy()
    draw = ImageDraw.Draw(im)
    img_width, img_height = im.size

    box_thickness = max(3, img_width // 220)

    if detections:
        tube_height = int(detections[0]["bbox"][3] - detections[0]["bbox"][1])
    else:
        tube_height = img_height // 4

    font_size = max(18, int(tube_height * 0.13))

    # FIX: use _FONT_PATH (absolute, based on this file's location) instead of
    # the old relative string which was resolved from the working directory.
    try:
        font = ImageFont.truetype(str(_FONT_PATH), font_size)
    except (OSError, IOError):
        logger.warning(
            "Could not load font at '%s'. Falling back to PIL default font.",
            _FONT_PATH,
        )
        font = ImageFont.load_default()

    padding = font_size // 4

    # ---- Draw detections ----
    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])

        if det["label"] == "Yellow_NoBubble":
            label_text, color = "1", (0, 180, 0)
        else:
            label_text, color = "0", (120, 120, 120)

        draw.rectangle([x1, y1, x2, y2], outline=color, width=box_thickness)

        text_bbox = draw.textbbox((0, 0), label_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        text_x = x1 + padding
        text_y = y1 + padding

        draw.rectangle(
            [text_x - padding, text_y - padding,
             text_x + text_w + padding, text_y + text_h + padding],
            fill=color
        )
        draw.text((text_x, text_y), label_text, fill=(255, 255, 255), font=font)

    # ---- Draw total tube count (bottom-right) ----
    count_text = f"Total Tubes: {total_count}"
    count_bbox = draw.textbbox((0, 0), count_text, font=font)
    count_w = count_bbox[2] - count_bbox[0]
    count_h = count_bbox[3] - count_bbox[1]
    margin = 30
    count_x = img_width - count_w - padding * 2 - margin
    count_y = img_height - count_h - padding * 2 - margin

    draw.rectangle(
        [count_x, count_y,
         count_x + count_w + padding * 2,
         count_y + count_h + padding * 2],
        fill=(0, 0, 0)
    )
    draw.text(
        (count_x + padding, count_y + padding),
        count_text,
        fill=(255, 255, 255),
        font=font
    )

    # ---- Return ----
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return detections, total_count, buf.getvalue()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Model loaded. Run this module via main.py or direct test.")