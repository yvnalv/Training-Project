"""
export_ncnn.py
--------------
Export a trained YOLO26 detection model to **NCNN** for the Raspberry Pi 5.

NCNN is ARM-optimized and ~4x faster than raw PyTorch on a Pi 5 (~68 ms vs ~302 ms at
640; see docs/HARDWARE.md). Always verify accuracy parity vs the PyTorch model on the
held-out test set before shipping (docs/NEXT_STEPS.md Phase 3.1).

Usage:
    python training/export_ncnn.py --weights runs/detect/vialvision_yolo26/weights/best.pt
    python training/export_ncnn.py --weights best.pt --imgsz 640

Output:
    Creates a "<weights_stem>_ncnn_model/" directory next to the weights. Load it in the
    app with YOLO("<...>_ncnn_model") (a directory path, not a single file).
"""

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    p = argparse.ArgumentParser(description="Export YOLO26 to NCNN for the Pi 5.")
    p.add_argument("--weights", required=True, help="Path to trained .pt weights.")
    p.add_argument("--imgsz", type=int, default=640, help="Export image size (match training).")
    p.add_argument("--half", action="store_true",
                   help="Export FP16 (smaller/faster; verify accuracy parity).")
    return p.parse_args()


def main():
    args = parse_args()
    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"weights not found: {weights}")

    model = YOLO(str(weights))
    out = model.export(format="ncnn", imgsz=args.imgsz, half=args.half)

    print(f"\nExported NCNN model: {out}")
    print("Load it in the app via YOLO(\"<dir>_ncnn_model\").")
    print("Verify accuracy parity vs the .pt model on the test set before shipping.")


if __name__ == "__main__":
    main()
