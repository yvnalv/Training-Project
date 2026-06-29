# Inference Pipeline

> _This document occupies the template slot originally named `WORKFLOW_APPROVAL`. The
> "workflow" in VialVision is the end-to-end inference flow that turns an image into a
> validated MPN result._

Implemented in `app/inference.py`, entered via `run_inference_with_count(image_bytes,
conf=0.4)`. Returns `(detections, total_count, annotated_jpeg_bytes)`.

## Stages

```
image_bytes
   │ 1. clamp conf to [0.05, 0.95]
   ▼
2. load (PIL) + downscale 50% (Lanczos)
   ▼
3. YOLOv8 detect: model(image, conf, iou=0.6, agnostic_nms=True)
   ▼
4. build detection dicts: { label, confidence, bbox=[x1,y1,x2,y2] }
   ▼
5. suppress_duplicate_tubes()  ── greedy NMS + hard cap 9 + left→right sort
   ▼
6. annotate: draw boxes, "1"/"0" labels, total-tube count
   ▼
(detections, total_count, annotated_jpeg_bytes)
```

The MPN computation (stages beyond detection) is done by the caller via
`_compute_mpn()` — see [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md).

## Stage details

### 1. Confidence clamp
`conf = max(0.05, min(0.95, conf))`. Callers may pass a user-set threshold (upload
form field or `set_conf` WebSocket control); it is always clamped.

### 2. Downscale
The image is opened as RGB and resized to **50 %** with Lanczos resampling before
inference. This is a deliberate latency optimization for the Raspberry Pi. **All
returned `bbox` coordinates are in this downscaled space**, and the annotated image
is the downscaled image.

### 3. YOLO detection
```python
results = model(image, conf=conf, iou=0.6, agnostic_nms=True)
```
- `iou=0.6` — built-in NMS IoU threshold.
- `agnostic_nms=True` — NMS treats all classes the same (tubes are one physical
  object regardless of positive/negative label).

`model = YOLO("best.pt")` is loaded once at import time.

### 5. Duplicate suppression (`suppress_duplicate_tubes`)
A second, domain-specific **greedy NMS** pass on top of YOLO's own NMS, because real
racks produce clustered false positives (rack edges, label strips, reflections).

Algorithm:
1. Sort detections by confidence, highest first.
2. Keep the top detection; suppress every lower-confidence detection that **either**:
   - has **IoU > 0.3** with it (directly overlapping boxes), **or**
   - has **x-center distance < 0.4 × average tube width** (vertically-stacked
     duplicates that share little vertical overlap, e.g. a label strip below a tube).
3. Repeat for the next surviving detection.
4. **Hard cap:** if more than `_MAX_TUBES (= 9)` survive, keep only the top-9 by
   confidence.
5. Sort the survivors left-to-right by box center.

Both suppression criteria are checked together so that 3+ detections clustered on one
physical tube always collapse to a single representative. Defaults: `iou_thresh=0.3`,
`x_thresh_ratio=0.4`.

> Rationale and history: see [../CHANGELOG.md](../CHANGELOG.md) entry _2026-04-16 —
> over-detection (>9 tubes)_.

### 6. Annotation
- Box thickness and font size scale with image/tube size.
- Each box is labeled `"1"` (green) for `Yellow_Bubble`, else `"0"` (gray).
- A `Total Tubes: N` overlay is drawn bottom-right.
- The font is loaded from an **absolute** path
  (`app/fonts/DejaVuSans-Bold.ttf`) so it resolves regardless of the working
  directory; it falls back to the PIL default font if unavailable.
- Output is JPEG bytes.

## Validity gate

The detector may return any count. MPN is only computed when `total_count == 9`
(enforced by `_compute_mpn()`); otherwise all MPN fields are `null` and a warning is
logged. There is **no automatic correction** of an over/under count — the result is
simply reported as having no MPN, prompting the operator to re-frame or adjust the
confidence threshold.

## Tuning knobs

| Parameter | Where | Effect |
|---|---|---|
| `conf` | request / `set_conf` | Higher = fewer detections / fewer false positives |
| `iou=0.6` | `model(...)` | YOLO NMS overlap threshold |
| `iou_thresh=0.3` | `suppress_duplicate_tubes` | Dedup overlap threshold |
| `x_thresh_ratio=0.4` | `suppress_duplicate_tubes` | Horizontal dedup distance (× avg width) |
| `scale_factor=0.5` | downscale | Speed vs. detail trade-off |
| `_MAX_TUBES=9` | hard cap | Maximum tubes ever reported |
