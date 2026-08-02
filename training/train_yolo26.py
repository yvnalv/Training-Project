"""
train_yolo26.py
---------------
Train a YOLO26 **object-detection** model on the VialVision tube dataset.

This encodes the color/bubble-safe augmentation policy from
docs/LABELING_STRATEGY.md §5 — most importantly `hsv_h=0.0` (no hue shift), because the
task depends on distinguishing yellow vs purple. Do not re-enable hue augmentation.

Usage:
    # from the project root, with the venv active
    python training/train_yolo26.py --data path/to/data.yaml
    python training/train_yolo26.py --data path/to/data.yaml --model yolo26s.pt --epochs 150

Notes:
- `--data` points at the data.yaml from the Roboflow YOLO26 export.
- Positive class in the dataset is `yellow_positive` (see docs/LABELING_STRATEGY.md).
- After training, export to NCNN for the Raspberry Pi 5 with training/export_ncnn.py.
"""

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    p = argparse.ArgumentParser(description="Train YOLO26 detection for VialVision.")
    p.add_argument("--data", required=True,
                   help="Path to the dataset data.yaml (Roboflow YOLO26 export).")
    p.add_argument("--model", default="yolo26n.pt",
                   help="Pretrained model to start from (yolo26n.pt or yolo26s.pt).")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640,
                   help="Training image size. 640 is the accuracy/speed sweet spot.")
    p.add_argument("--batch", type=int, default=16,
                   help="Batch size (-1 lets Ultralytics auto-pick for the GPU).")
    p.add_argument("--patience", type=int, default=20,
                   help="Early-stopping patience (epochs without improvement).")
    p.add_argument("--device", default=None,
                   help="cuda device e.g. '0', or 'cpu'. Default: auto.")
    p.add_argument("--name", default="vialvision_yolo26",
                   help="Run name (results saved under runs/detect/<name>).")
    return p.parse_args()


def main():
    args = parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"data.yaml not found: {data_path}")

    model = YOLO(args.model)

    # ---- Color/bubble-safe augmentation policy (docs/LABELING_STRATEGY.md §5) ----
    # hsv_h=0.0  -> NO hue shift (protect yellow vs purple). Do not change.
    # flipud=0.0 -> NO vertical flip (a bubble sits at the top of the tube).
    # Modest saturation/brightness/rotation only; horizontal flip is geometrically safe.
    train_kwargs = dict(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        name=args.name,
        hsv_h=0.0,
        hsv_s=0.3,
        hsv_v=0.4,
        flipud=0.0,
        fliplr=0.5,
        degrees=5.0,
        translate=0.05,
        scale=0.2,
        mosaic=1.0,     # Ultralytics mosaic; disable (0.0) if it hurts on this data
    )
    if args.device is not None:
        train_kwargs["device"] = args.device

    print(f"Training {args.model} on {data_path} (imgsz={args.imgsz}, epochs={args.epochs})")
    print("Augmentation: hsv_h=0.0 (hue OFF), flipud=0.0 (no vertical flip).")
    results = model.train(**train_kwargs)

    # ---- Validate and print per-class metrics ----
    print("\nValidating best weights on the val split...")
    metrics = model.val()
    print("mAP50-95:", getattr(metrics.box, "map", "n/a"))
    print("mAP50   :", getattr(metrics.box, "map50", "n/a"))

    best = Path(results.save_dir) / "weights" / "best.pt"
    print(f"\nDone. Best weights: {best}")
    print("Next: export to NCNN for the Pi 5:")
    print(f"    python training/export_ncnn.py --weights \"{best}\" --imgsz {args.imgsz}")
    print("Reminder: at app integration, update the positive label string "
          "'Yellow_Bubble' -> 'yellow_positive' (docs/NEXT_STEPS.md Phase 4.4).")


if __name__ == "__main__":
    main()
