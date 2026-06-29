# Glossary

| Term | Definition |
|---|---|
| **MPN** | Most Probable Number — a statistical estimate of microbial concentration (per gram) derived from serial-dilution tube results. |
| **MPN/g** | The MPN value expressed per gram of sample. Reported as a (possibly non-numeric) string, e.g. `15`, `<3.0`, `>1100`. |
| **Rack** | The physical holder with 9 tubes arranged in 3 dilution groups of 3. |
| **Tube** | One dilution test tube. Read as positive (1) or negative (0). |
| **Positive tube** | A tube classified `Yellow_Bubble` — yellow with a gas bubble, indicating microbial growth → value `1`. |
| **Negative tube** | Any non-`Yellow_Bubble` tube → value `0`. |
| **Dilution group** | One of three sets of 3 tubes (0.1 g, 0.01 g, 0.001 g of sample). |
| **(x, y, z)** | Positive counts in groups 1, 2, 3 (each `0–3`). |
| **Pattern** | The string `P{x}{y}{z}` (e.g. `P210`) used as the MPN-table key. |
| **95 % CI** | The confidence interval (`ci_low`–`ci_high`) for an MPN value, from the reference table. |
| **Risk level** | Safe / Low / Moderate / High classification of an MPN/g value. |
| **Detection** | One YOLO output: `{ label, confidence, bbox }`. |
| **bbox** | Bounding box `[x1, y1, x2, y2]` in pixels (on the 50 %-downscaled image). |
| **NMS** | Non-Maximum Suppression — removing overlapping/duplicate detections, keeping the most confident. |
| **Greedy NMS dedup** | VialVision's extra suppression pass (`suppress_duplicate_tubes`) on top of YOLO's NMS, with an IoU and an x-distance criterion. |
| **IoU** | Intersection over Union — overlap ratio of two boxes. |
| **Hard cap (9)** | The rule that never more than 9 tubes are reported. |
| **YOLOv8 Nano** | The compact Ultralytics object-detection model used (`best.pt`). |
| **best.pt** | The trained model weights loaded at runtime. |
| **Client mode** | Live stream where the **browser** captures frames and sends them to the server. |
| **Server mode** | Live stream where the **server** captures from its own camera (Pi/USB). |
| **picamera2** | The native Raspberry Pi camera library (preferred backend). |
| **Capture / still** | A single frame grabbed from the server camera via `GET /capture`. |
| **Annotated image** | The result image with drawn boxes, `1`/`0` labels, and a tube count. |
| **Pruning** | Auto-deletion of the oldest records (and images) beyond `MAX_HISTORY` (500). |
| **Settings** | DB-stored UI preferences (camera mode, FPS, resolution, flip, confidence). |
| **XDG autostart / Wayfire** | The desktop-session mechanism used to auto-start VialVision on Pi boot. |
| **WAL** | SQLite Write-Ahead Logging mode (better concurrent reads). |
