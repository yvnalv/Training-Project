"""Evaluate the rack model on val + test splits and save plots (confusion matrix,
curves). Run from a file (not stdin) with workers=0 to avoid the Windows
multiprocessing spawn error."""
from ultralytics import YOLO

if __name__ == "__main__":
    m = YOLO(r"runs/detect/vialvision_yolo26_rack/weights/best.pt")
    for split in ["val", "test"]:
        print(f"===== {split.upper()} SPLIT =====")
        m.val(data="training/data.vialvision.yaml", split=split, imgsz=640,
              plots=True, name=f"rack_report_{split}", exist_ok=True,
              workers=0, verbose=True)
    print("ALL DONE")
