import io
import logging
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# FIX: Use an absolute path derived from this file's own location instead of a
# relative path. The relative "fonts/..." path was resolved from wherever uvicorn
# was launched (the project root), but the fonts/ folder lives inside app/, so
# it never matched. Path(__file__).parent points to the app/ directory regardless
# of where the server is started from.
_FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"

# The positive tube class emitted by the YOLO26 model. Everything else -> 0.
# Single source of truth (renamed from the old "Yellow_Bubble" — see CHANGELOG /
# docs/LABELING_STRATEGY.md). If the model's class name changes, change it here only.
POSITIVE_LABEL = "yellow_positive"

# Model location, resolved absolutely from this file so it works regardless of the
# directory uvicorn is started from. Prefer the NCNN model (fast on the Pi) when the
# ncnn runtime is installed; otherwise use the PyTorch weights (fine on a dev machine).
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_NCNN_DIR = _MODELS_DIR / "best_ncnn_model"
_PT_PATH = _MODELS_DIR / "vialvision_yolo26.pt"


# Which backend actually loaded — exposed to the UI (Settings shows an NCNN/PyTorch
# badge) so it's obvious on each deployment whether the fast path is in use.
MODEL_BACKEND = "unknown"


def _resolve_model_path() -> str:
    global MODEL_BACKEND
    if _NCNN_DIR.exists():
        try:
            import ncnn  # noqa: F401 — is the NCNN runtime available?
            logger.info("Using NCNN model at %s", _NCNN_DIR)
            MODEL_BACKEND = "ncnn"
            return str(_NCNN_DIR)
        except Exception:
            logger.info("ncnn runtime not installed; falling back to PyTorch weights.")
    if _PT_PATH.exists():
        logger.info("Using PyTorch model at %s", _PT_PATH)
        MODEL_BACKEND = "pytorch"
        return str(_PT_PATH)
    raise FileNotFoundError(
        f"No model found in {_MODELS_DIR}. Copy the trained model there "
        f"(vialvision_yolo26.pt and/or best_ncnn_model/) — see docs/DEV_ENVIRONMENT.md."
    )


# Load the model once at import time. task="detect" is explicit so the NCNN export
# (which has no embedded task metadata) doesn't emit a "guessing task" warning.
model = YOLO(_resolve_model_path(), task="detect")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_TUBES = 9

# Fixed-ROI (jig) mode — see docs/FIXED_ROI_DESIGN.md.
# ROI_PAD expands each auto-seeded box outward (fraction of its size) so a slightly
# shifted tube still falls inside its crop. UNCERTAIN_LABEL marks a crop the model
# couldn't classify (rendered "?" and counted as negative for MPN, but surfaced).
_ROI_PAD = 0.08
UNCERTAIN_LABEL = "uncertain"


def _iou(a, b):
    """Intersection-over-Union for two [x1, y1, x2, y2] boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def suppress_duplicate_tubes(detections, iou_thresh=0.3, x_thresh_ratio=0.4):
    """
    Removes duplicate detections that belong to the same physical tube.

    Uses a full greedy-NMS pass (highest confidence first) with two
    suppression criteria:
      1. IoU overlap > iou_thresh  — catches boxes that overlap in 2-D.
      2. x-centre distance < avg_width * x_thresh_ratio — catches stacked
         duplicates with little vertical overlap (e.g. label vs tube body).

    Both criteria are checked so that 3+ clustered detections are always
    collapsed to a single representative, regardless of how many there are.
    The result is sorted left-to-right for consistent tube ordering.
    """
    if not detections:
        return []

    widths = [d["bbox"][2] - d["bbox"][0] for d in detections]
    avg_width = sum(widths) / len(widths)
    x_thresh = avg_width * x_thresh_ratio

    # Process highest-confidence detections first
    ranked = sorted(detections, key=lambda d: d["confidence"], reverse=True)

    kept = []
    suppressed = set()

    for i, det in enumerate(ranked):
        if i in suppressed:
            continue
        kept.append(det)
        cx_i = (det["bbox"][0] + det["bbox"][2]) / 2

        for j in range(i + 1, len(ranked)):
            if j in suppressed:
                continue
            other = ranked[j]
            cx_j = (other["bbox"][0] + other["bbox"][2]) / 2
            if (
                _iou(det["bbox"], other["bbox"]) > iou_thresh
                or abs(cx_i - cx_j) < x_thresh
            ):
                suppressed.add(j)

    # Hard cap: the physical rack always has exactly _MAX_TUBES tubes.
    # If anything still slips through, keep only the top-confidence ones.
    if len(kept) > _MAX_TUBES:
        kept = sorted(kept, key=lambda d: d["confidence"], reverse=True)[:_MAX_TUBES]

    # Final left-to-right sort for correct tube ordering
    kept.sort(key=lambda d: (d["bbox"][0] + d["bbox"][2]) / 2)
    return kept


def detections_to_tubes(detections):
    """
    Convert ordered detections (left -> right) into 9 tube values (0/1).

    Rule:
      yellow_positive -> 1 (positive)
      otherwise       -> 0 (negative)

    Raises:
        ValueError: if the number of detections is not exactly 9.
    """
    tubes = [1 if d["label"] == POSITIVE_LABEL else 0 for d in detections]

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
# Lens distortion correction (option C1 — calibration-free)
# ---------------------------------------------------------------------------

def _undistort(image, k1: float):
    """
    Approximate, calibration-free barrel/"fisheye" correction for phone cameras.

    A proper fix needs a per-phone checkerboard calibration; that's impractical for a
    common user. Instead we assume the principal point is the image centre and the focal
    length ~ the image width, and expose a single radial coefficient `k1` the user nudges
    (a Settings slider) until the rack edges look straight in the captured result. 0 = off.
    getOptimalNewCameraMatrix(alpha=1) keeps the whole frame (edges may gain a small black
    border, but the tubes move inward, off the distorted edge). See docs/ACCURACY_IMPROVEMENT.md.
    """
    if not k1 or abs(k1) < 1e-6:
        return image
    arr = np.asarray(image)
    h, w = arr.shape[:2]
    f = float(w)
    K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1]], dtype=np.float64)
    dist = np.array([float(k1), 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    new_k, _ = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 1, (w, h))
    undist = cv2.undistort(arr, K, dist, None, new_k)
    return Image.fromarray(undist)


# ---------------------------------------------------------------------------
# Shared annotation
# ---------------------------------------------------------------------------

def _draw_annotations(image, detections, total_count):
    """
    Draw tube boxes (with 1 / 0 / ? labels) and the total-count badge onto a copy
    of `image`, returning the annotated JPEG bytes. Shared by the full-frame path
    (run_inference_with_count) and the fixed-ROI path (run_inference_fixed_roi).

    Label rules:
      yellow_positive  -> "1" (green)
      uncertain        -> "?" (amber)  — fixed-ROI crop the model couldn't classify
      otherwise        -> "0" (grey)
    """
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

    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])

        if det["label"] == POSITIVE_LABEL:
            label_text, color = "1", (0, 180, 0)
        elif det["label"] == UNCERTAIN_LABEL:
            label_text, color = "?", (210, 150, 0)
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

    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public inference entry point
# ---------------------------------------------------------------------------

def run_inference_with_count(image_bytes: bytes, conf: float = 0.4,
                             scale_factor: float = 0.5, k1: float = 0.0):
    """
    Full inference pipeline: load image -> downscale -> YOLO -> deduplicate ->
    annotate -> return results.

    Args:
        image_bytes:  Raw image file contents (any format PIL can open).
        conf:         YOLO confidence threshold (0.0-1.0). Defaults to 0.4.
        scale_factor: Pre-inference resize factor. 0.5 (default) is the fast live-stream
                      path; pass 1.0 for a full-resolution "Aim & Capture" reading (most
                      accurate). See docs/STREAM_PERFORMANCE.md (Two inference modes).

    Returns:
        detections (list[dict]): Each dict has 'label', 'confidence', 'bbox'.
        total_count (int):       Number of unique tubes detected after dedup.
        annotated_image (bytes): JPEG image with bounding boxes drawn.
    """
    conf = max(0.05, min(0.95, conf))
    scale_factor = max(0.1, min(1.0, scale_factor))

    # ---- Load, (optionally) undistort, then (optionally) downscale image ----
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = _undistort(image, k1)
    if scale_factor < 1.0:
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

    # ---- Annotate & return ----
    annotated = _draw_annotations(image, detections, total_count)
    return detections, total_count, annotated


# ---------------------------------------------------------------------------
# Fixed-ROI (jig) mode — see docs/FIXED_ROI_DESIGN.md
# ---------------------------------------------------------------------------

def detect_rois_normalized(image_bytes: bytes, conf: float = 0.4):
    """
    Calibration seed: run full-frame detection and return the detected tube boxes as
    **normalised** [x1, y1, x2, y2] (fractions of width/height), sorted left→right, each
    padded outward by _ROI_PAD. The frontend overlays these for the operator to confirm /
    nudge before saving as the fixed ROIs.

    Returns:
        rois (list[list[float]]): normalised, padded boxes (0..1), left→right.
        count (int):              how many were found (may be != 9; operator fixes up).
    """
    conf = max(0.05, min(0.95, conf))
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = image.width, image.height

    results = model(image, conf=conf, iou=0.6, agnostic_nms=True)
    result = results[0]

    boxes = result.boxes
    detections = []
    if boxes is not None and len(boxes) > 0:
        for b in boxes:
            detections.append({
                "label": result.names[int(b.cls)],
                "confidence": float(b.conf),
                "bbox": b.xyxy.tolist()[0],
            })

    detections = suppress_duplicate_tubes(detections)

    rois = []
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        pad_x = (x2 - x1) * _ROI_PAD
        pad_y = (y2 - y1) * _ROI_PAD
        rois.append([
            max(0.0, (x1 - pad_x) / W),
            max(0.0, (y1 - pad_y) / H),
            min(1.0, (x2 + pad_x) / W),
            min(1.0, (y2 + pad_y) / H),
        ])
    return rois, len(rois)


def _classify_crop(crop, conf: float):
    """
    Classify a single tube crop. Because the crop is a known tube position, we run the
    detection model on it and take the highest-confidence detection's class. A lower
    threshold is used than full-frame detection (the crop contains exactly one tube, so
    false positives aren't a concern and we'd rather classify than miss).

    Returns (label, confidence). If nothing fires, returns (UNCERTAIN_LABEL, 0.0).
    """
    crop_conf = max(0.10, conf * 0.5)
    results = model(crop, conf=crop_conf, iou=0.6, agnostic_nms=True)
    result = results[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return UNCERTAIN_LABEL, 0.0
    best = max(boxes, key=lambda b: float(b.conf))
    return result.names[int(best.cls)], float(best.conf)


def run_inference_fixed_roi(image_bytes: bytes, rois, conf: float = 0.4, k1: float = 0.0):
    """
    Fixed-ROI pipeline (jig mode): instead of *detecting* tubes, crop the N known ROI
    positions and *classify* each. Always returns len(rois) results, so on a 9-ROI jig
    total_count == 9 and MPN is always computed — an edge tube that blends into the rig
    is impossible to miss (see docs/FIXED_ROI_DESIGN.md).

    Args:
        image_bytes: Raw full-resolution frame (any format PIL can open).
        rois:        List of normalised [x1, y1, x2, y2] boxes (0..1), in tube order 0..N.
        conf:        Confidence threshold; halved internally for per-crop classification.

    Returns:
        detections (list[dict]): one per ROI — 'label', 'confidence', 'bbox' (pixel coords).
        total_count (int):       len(rois).
        annotated_image (bytes): JPEG with the ROI boxes + 1/0/? labels drawn.
    """
    conf = max(0.05, min(0.95, conf))
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = _undistort(image, k1)
    W, H = image.width, image.height

    detections = []
    for roi in rois:
        rx1, ry1, rx2, ry2 = roi
        x1 = int(min(rx1, rx2) * W)
        y1 = int(min(ry1, ry2) * H)
        x2 = int(max(rx1, rx2) * W)
        y2 = int(max(ry1, ry2) * H)
        # Clamp to image bounds and guarantee a non-empty crop.
        x1 = max(0, min(x1, W - 1))
        y1 = max(0, min(y1, H - 1))
        x2 = max(x1 + 1, min(x2, W))
        y2 = max(y1 + 1, min(y2, H))

        crop = image.crop((x1, y1, x2, y2))
        label, confidence = _classify_crop(crop, conf)
        detections.append({
            "label": label,
            "confidence": confidence,
            "bbox": [x1, y1, x2, y2],
        })

    total_count = len(detections)
    annotated = _draw_annotations(image, detections, total_count)
    return detections, total_count, annotated


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Model loaded. Run this module via main.py or direct test.")