# Model & Data Assets

> _This document occupies the template slot originally named `INVENTORY_DESIGN`.
> Instead of stock inventory, VialVision's "inventory" is its model weights, training
> data, and on-device data assets._

## Model

| Item | Value |
|---|---|
| Architecture | Ultralytics YOLOv8 **Nano** |
| Active weights | `best.pt` (project root) |
| Loaded by | `app/inference.py`: `model = YOLO("best.pt")` (once, at import) |
| Classes | Tube-detection classes (notably `Yellow_Bubble` = positive) — **not** COCO |
| Inference settings | `conf` (clamped 0.05–0.95), `iou=0.6`, `agnostic_nms=True` |

The model is loaded relative to the **working directory** as `"best.pt"`, so the
server must be started from the project root (as all run commands and scripts do).

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
