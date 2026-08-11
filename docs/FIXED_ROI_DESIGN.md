# Fixed-ROI classification (jig mode)

> **Status:** design / in progress on `feature/fixed-roi-jig` (2026-08-11).
> Applies to the **controlled Pi appliance** use case only — see the two use cases in
> [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md#the-two-deployment-use-cases-they-are-genuinely-different-products).

## Why

On a fixed jig the rack sits in the **same place every time**, so we do not need the
detector to *find* the tubes — we already know where all 9 are. Full-frame detection keeps
losing **edge tubes** when lens distortion + angle + a white rig make them blend into the
background (see the 2026-08-11 problem in ACCURACY_IMPROVEMENT.md — 7/9 detected).

**Fixed-ROI turns "find + classify" into just "classify":**

```
Full-frame detection (today):   frame → detect N tubes → dedup → if N==9 → MPN
                                        ^ fails to FIND low-contrast edge tubes → N=7 → no MPN

Fixed-ROI (jig mode):           frame → crop 9 known ROIs → classify each → always 9 → MPN
                                        ^ an edge tube that blends in is impossible to detect,
                                          but trivial to classify once its crop fills the frame
```

Cropping a single tube also **removes the three edge effects at once**: the crop is taken
from a known location (no "where is it"), the tube fills the crop (contrast restored), and
the crop can be upscaled before classification.

## Pipeline

### 1. Calibration (once per jig setup)
1. Operator places the rack in the jig and hits **Calibrate** in Settings.
2. Server captures a reference frame and runs **full-frame detection** on it.
3. If exactly 9 tubes are found, their boxes (sorted left→right) become the 9 ROIs.
   Each ROI is expanded by a small padding and stored as **normalised** `[x1,y1,x2,y2]`
   (fractions of width/height, so they survive resolution changes).
4. The UI overlays the 9 ROIs on the reference frame for the operator to **confirm / nudge**
   (manual adjust covers the case where auto-detect finds ≠ 9).
5. Save → persisted in settings as `roiBoxes` (JSON, 9 boxes in tube order 0–8) plus
   `roiCalibratedAt`. Recalibrate only if the camera or rack moves.

### 2. Inference (per capture / per frame)
For each of the 9 stored ROIs, in order:
1. Crop the ROI from the frame (with padding already baked in).
2. Optionally upscale the crop to a minimum size.
3. Classify the crop → `yellow_positive` / `yellow_negative` / `purple_negative`
   → tube value `1` if `yellow_positive` else `0`.
4. If the classifier returns nothing, mark the tube **uncertain** (rendered distinctly;
   counted as `0` for MPN but surfaced so the operator can re-shoot).

Because there are always 9 results, `total_tubes == 9` **always**, so MPN is always
computed (no more `null` from a miscount). The 9 values feed the existing
`tubes_to_xyz` → MPN lookup unchanged.

### 3. Annotation
Draw the 9 fixed ROI boxes with their `0` / `1` (and an "?" style for uncertain), plus the
usual "Total Tubes: 9" — reusing the drawing code in `inference.py`.

## How each crop is classified

Reuse the **existing detection model** on the crop (no new model to train, ships now):
run `model(crop, conf=<low>)`, take the highest-confidence detection's class. A tight crop
of one tube is an easy input for the model even when the same tube was unfindable in the
full frame. If no detection fires, the tube is **uncertain** (see above).

> A dedicated tube **classifier** (YOLO-cls or a small CNN on crops) is a possible future
> upgrade for robustness, but is **out of scope** for the first version — we reuse the
> trained detection weights to avoid a second training pipeline.

## Data model & API (planned)

- **Settings keys** (existing settings store): `roiMode` (bool), `roiBoxes` (JSON: 9×
  `[x1,y1,x2,y2]` normalised, tube order), `roiCalibratedAt` (ISO string).
- **`POST /calibrate`** — capture/accept a frame, run full-frame detection, return the 9
  proposed ROIs (normalised) for the UI to confirm. Does **not** save; the client saves via
  the existing settings endpoint after the operator confirms.
- **Inference entry point** — `run_inference_fixed_roi(image_bytes, rois, conf)` in
  `inference.py`, mirroring `run_inference_with_count`'s return shape
  `(detections, total_count, annotated_jpeg)` so callers are drop-in.
- **`/predict`** and the **WS `capture_now`** path use the ROI pipeline **iff** `roiMode`
  is on and `roiBoxes` is calibrated; otherwise they fall back to full-frame detection.
- **Platform default:** Pi → ROI mode *available* (off until calibrated); phone/VPS → ROI
  controls **hidden** (no fixed jig, so ROIs are meaningless).

## Guardrails / edge cases

- **Not calibrated but roiMode on** → fall back to full-frame detection and warn in the UI.
- **Auto-detect finds ≠ 9 at calibration** → keep whatever it found as draggable seeds and
  require manual completion to exactly 9 before save.
- **Rack/camera moved** → ROIs drift off the tubes; the operator recalibrates. (A future
  check could flag drift automatically.)
- **This mode does not fix the phone use case** — it is jig-only by definition.

## Relationship to existing features

- Independent of **NCNN vs PyTorch** (backend = speed only).
- Complements **Aim & Capture** — ROI classification is most valuable on the full-res
  single-shot path, and can also run per-frame in Live mode on the jig.
- Does **not** replace full-frame detection — that remains the phone/VPS path and the
  fallback when uncalibrated.
