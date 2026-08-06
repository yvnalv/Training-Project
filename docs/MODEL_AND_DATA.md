# Model & Data Assets

> _This document occupies the template slot originally named `INVENTORY_DESIGN`.
> Instead of stock inventory, VialVision's "inventory" is its model weights, training
> data, and on-device data assets._

## Model

| Item | Value |
|---|---|
| Architecture | Ultralytics YOLOv8 **Nano** (verified: base `yolov8n.pt`, ~3.0 M params, task=detect) |
| Active weights | `best.pt` (project root) |
| Loaded by | `app/inference.py`: `model = YOLO("best.pt")` (once, at import) |
| Classes | **4:** `Purple_Bubble`, `Purple_NoBubble`, `Yellow_Bubble`, `Yellow_NoBubble` (IDs 0–3) — **not** COCO |
| Positive rule | Only `Yellow_Bubble` (id 2) → positive; the other three → negative. See [LABELING_STRATEGY.md](LABELING_STRATEGY.md) |
| Trained with | ultralytics 8.3.x (env has 8.4.37, which already ships YOLO26 configs) |
| Inference settings | `conf` (clamped 0.05–0.95), `iou=0.6`, `agnostic_nms=True` |
| Export format | PyTorch `.pt` (no NCNN/ONNX export — see note below) |

> **Planned upgrade (decided 2026-06-29):** retrain as **YOLO26 object detection**
> (`yolo26n`, compare `yolo26s`) on the existing Roboflow dataset, keeping the detection
> architecture, and deploy via **NCNN** on a Raspberry Pi 5. NCNN alone is ~4× faster
> than the current raw `.pt` on a Pi (~68 ms vs ~302 ms at 640).
>
> The new model uses a **3-class** schema with **renamed** classes:
> `yellow_positive` (=1), `yellow_negative` (=0), `purple_negative` (=0) — replacing the
> old 4 (`Yellow_Bubble`/…). ⚠️ The positive label changes from `Yellow_Bubble` →
> `yellow_positive`, so the 4 hardcoded label strings in `inference.py` and `script.js`
> must be updated at integration (see [NEXT_STEPS.md](NEXT_STEPS.md) Phase 4.4 and
> [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §3).
>
> Full build plan in [NEXT_STEPS.md](NEXT_STEPS.md); label/preprocessing/augmentation
> policy in [LABELING_STRATEGY.md](LABELING_STRATEGY.md); board comparison in
> [HARDWARE.md](HARDWARE.md); YOLO26 evaluation in
> [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md).

The model is loaded relative to the **working directory** as `"best.pt"`, so the
server must be started from the project root (as all run commands and scripts do).

## Trained models

Trained on an RTX 4060 (env `testcuda`: ultralytics 8.4.115, torch 2.5.1+cu121) via
[../training/train_yolo26.py](../training/train_yolo26.py).

### Active — YOLO26n on `VialVision2.0 v2` (rack-inclusive, 2026-08-04)

The current app model. Adds ~70–79 annotated **9-tube rack** photos to the single-tube
data (racks in train/valid/test). **Val mAP50 0.966**; **detects 9 tubes on all 5 real
rack photos** → MPN end-to-end. Per-class val: `purple_negative` 0.995, `yellow_positive`
0.98, **`yellow_negative` 0.906 (recall 0.73 — weak, the refinement target)**.

Artifacts (gitignored; copy manually):
- **App model:** `models/best_ncnn_model/` (NCNN) + `models/vialvision_yolo26.pt`
- Training run: `runs/detect/vialvision_yolo26_rack/`

> Why this fixed it: the earlier `v1` model (below) was trained on **single-tube photos
> only**, so it couldn't localize tubes in a full rack (1–2 clustered boxes). Adding rack
> images fixed localization — detection was always the right approach.

### Earlier — YOLO26n on `VialVision2.0 v1` (single-tube only, 2026-08-03)

First YOLO26 retraining (single-tube data). Strong on single tubes but **fails on real
racks** (superseded by v2 above).

| Model | Val mAP50 | Val mAP50-95 | Test mAP50 | Size | Chosen |
|---|---|---|---|---|---|
| **yolo26n** | 0.992 | 0.971 | **0.948** | 5.3 MB | ✅ |
| yolo26s | 0.994 | 0.974 | 0.911 | 20 MB | — (no accuracy gain, 4× larger) |

Per-class (yolo26n, test split): `purple_negative` 0.995, `yellow_positive` 0.963,
**`yellow_negative` 0.885** — the weakest class and the false-positive risk. NCNN parity:
test mAP50 0.930 (acceptable). Bigger model gave no gain → **accuracy is data-limited, not
capacity-limited.**

**Artifact locations** (⚠️ `runs/` is **gitignored** — these are NOT in the repo; copy
manually to move between machines):

| Artifact | Path |
|---|---|
| **NCNN model (for the Pi)** | `runs/detect/vialvision_yolo26/weights/best_ncnn_model/` — load via `YOLO(".../best_ncnn_model")` |
| PyTorch weights (winner) | `runs/detect/vialvision_yolo26/weights/best.pt` |
| Comparison run (yolo26s) | `runs/detect/vialvision_yolo26s/weights/best.pt` |
| Metrics/plots (confusion matrix, curves) | `runs/detect/vialvision_yolo26/` |
| Local training data config (gitignored) | `training/data.vialvision.yaml` |

Caveat: trained on **single-tube** photos (~1 box/image); real 9-tube rack performance is
still pending validation. See [NEXT_STEPS.md](NEXT_STEPS.md) Phase 5 for the
durable-improvement plan.

## Detection classes

The trained model emits tube classes. The only one that maps to a **positive** tube
is `Yellow_Bubble`; every other label is treated as negative. See
[MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md), Rule 1.

## Checkpoints in the repo

Several `.pt` files are currently committed to the repository:

| File | Notes |
|---|---|
| `best.pt` | **Active** weights used at runtime |
| `best (backup).pt` | Backup snapshot |
| `best_old.pt` | Previous version |
| `vialvision_2.pt` | Alternate/experimental checkpoint |
| `yolov8n.pt` | Base COCO YOLOv8n (pretrained starting point) |

> **Debt:** committing multiple multi-MB checkpoints bloats the repo. The roadmap
> calls for proper model versioning and keeping only `best.pt` tracked (or moving
> weights to release artifacts / Git LFS). See [ROADMAP.md](ROADMAP.md) and
> [STATUS.md](STATUS.md).

## Training & comparison

- `compare_models.ipynb` (project root) — notebook used to compare model checkpoints.
- `data/` at the repo root is the **runtime** data directory (DB + result images),
  not the training dataset.
- Training data and the training pipeline are not committed; retraining is an
  out-of-band activity. When retraining, preserve the class names so
  `Yellow_Bubble` continues to denote a positive tube.

## MPN reference data

`app/mpn/mpn_table.csv` — 40-row CSV mapping each pattern (`P000`–`P333`) to its MPN/g
value and 95 % CI. Validated at startup by `load_mpn_table()`. This is reference data,
not model output; it changes only if the MPN standard changes. See
[MPN_DESIGN.md](MPN_DESIGN.md).

## On-device data assets (runtime)

| Path | Contents | Lifecycle |
|---|---|---|
| `data/vialvision.db` | SQLite DB (predictions + settings) | Persistent; pruned to 500 records |
| `data/results/*.jpg` | Annotated images for saved predictions | Created per save; deleted on prune/delete |

See [DATABASE.md](DATABASE.md) for the persistence model.

## Fonts

`app/fonts/DejaVuSans-Bold.ttf` — bundled font used to draw labels and the tube count
on annotated images. Resolved by absolute path so it works regardless of the launch
directory.
