# Training — YOLO26 detection

Scripts to retrain VialVision's tube detector as **YOLO26 object detection** and export
it for the Raspberry Pi 5. This is the Track-B (modeling) work in
[../docs/NEXT_STEPS.md](../docs/NEXT_STEPS.md). Full label/preprocessing/augmentation
policy is in [../docs/LABELING_STRATEGY.md](../docs/LABELING_STRATEGY.md).

## Prerequisites

- The project venv (Python 3.13) with `ultralytics` (8.4.x ships YOLO26).
- The Roboflow dataset **exported in YOLO26 format** (gives `data.yaml` + `images/` +
  `labels/`). Note the path to `data.yaml`.

## Classes (3)

| Class | Meaning | Tube value |
|---|---|---|
| `yellow_positive` | yellow + bubble | **1 (positive)** |
| `yellow_negative` | yellow, no bubble | 0 |
| `purple_negative` | purple (any bubble state) | 0 |

`purple_negative` must include **purple-with-bubble** hard negatives.

## Workflow

```bash
# 1. Train (from the project root, venv active)
python training/train_yolo26.py --data path/to/data.yaml
#    compare the small variant for accuracy:
python training/train_yolo26.py --data path/to/data.yaml --model yolo26s.pt --name vialvision_yolo26s

# 2. Review results in runs/detect/<name>/ (confusion matrix, PR curves, best.pt).
#    Watch the confusion between:
#      yellow_positive <-> yellow_negative  (bubble errors — costly)
#      yellow_positive <-> purple_negative  (color errors)

# 3. Export the winner to NCNN for the Pi 5
python training/export_ncnn.py --weights runs/detect/vialvision_yolo26/weights/best.pt
```

## Augmentation policy (baked into `train_yolo26.py`)

- `hsv_h=0.0` — **no hue shift** (protects yellow vs purple). Do not change.
- `flipud=0.0` — no vertical flip (a bubble sits at the top of the tube).
- Modest `hsv_s/hsv_v`, small rotation, horizontal flip OK.
- Do **not** add blur/noise/cutout — they erase bubble detail.

Match this in Roboflow: Auto-Orient + Resize 640 (Fit), **no** grayscale/hue; light
brightness/exposure/rotation only.

## Data caveat

The current set (`yellow_positive` 422, `purple_negative` 231, `yellow_negative` **58**)
is an **old-jig bootstrap** — good for a pipeline shakedown and early signal, not the
final model. `yellow_negative` (58) is thin, so its metrics will be noisy. The real
acceptance test uses the **new-jig eval set** (docs/NEXT_STEPS.md Phase 0.2 / Phase 5).

## ⚠️ Integration reminder

The trained model emits `yellow_positive`, but the app still hardcodes the old
`"Yellow_Bubble"` in 4 places. Update those to `"yellow_positive"` (ideally via a single
`POSITIVE_LABEL` constant) at integration — otherwise MPN is silently always `P000`. See
[../docs/NEXT_STEPS.md](../docs/NEXT_STEPS.md) Phase 4.4.
