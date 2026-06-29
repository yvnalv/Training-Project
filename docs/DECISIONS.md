# Decisions Log

A running log of significant decisions. For formal, individually-numbered records,
use the ADR format in [adr/](adr/) (start from [adr/0000-template.md](adr/0000-template.md)).
This file is the lightweight chronological summary.

| # | Decision | Rationale | Source |
|---|---|---|---|
| D-1 | Use YOLOv8 **Nano** | Smallest/fastest model; runs acceptably on Raspberry Pi 4 | [MODEL_AND_DATA.md](MODEL_AND_DATA.md) |
| D-2 | **FastAPI + vanilla JS**, no frontend framework | Minimal footprint and dependencies for an edge appliance | [ARCHITECTURE.md](ARCHITECTURE.md) |
| D-3 | **SQLite, no ORM** | Single-file, zero-config persistence; raw `sqlite3` is enough at this scale | [DATABASE.md](DATABASE.md) |
| D-4 | **Downscale 50 %** before inference | Latency optimization for the Pi; bbox/annotation live in downscaled space | [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md) |
| D-5 | **Extra greedy-NMS dedup + hard cap of 9** | YOLO NMS alone left clustered false positives and counts > 9 | CHANGELOG 2026-04-16 |
| D-6 | **`Yellow_Bubble` = positive (1)** | Domain definition; corrected after an inversion bug | CHANGELOG 2026-04-16 |
| D-7 | **No MPN when count ≠ 9** | Grouping is undefined otherwise; never guess a result | [BUSINESS_RULES.md](BUSINESS_RULES.md) BR-5 |
| D-8 | **Store frames as BGR; request RGB888; encode stills with PIL** | Avoids Pi/libcamera + ARM libjpeg channel-order swaps | CHANGELOG 2026-04-19 |
| D-9 | **Full-sensor `ScalerCrop` + sharpness + continuous AF** on Pi | Fix "too zoomed in" and blur at ~19 cm capture distance | CHANGELOG 2026-04-19 |
| D-10 | **DB-backed, server-side settings** with platform-aware default camera mode | Persist preferences across reloads; pick sane default per device | CHANGELOG 2026-04-19 |
| D-11 | **HTTPS with self-signed cert** | `getUserMedia` requires a secure origin for camera access | [SECURITY.md](SECURITY.md) |
| D-12 | **XDG autostart + Wayfire `[autostart]`** (not systemd) | Needs to run inside the desktop session to open Chromium; X11 tools don't work on Wayland | [DEPLOYMENT.md](DEPLOYMENT.md) |
| D-13 | **DB failures are non-fatal to `/predict`** | The user's result must never be lost to a persistence error | [ERROR_HANDLING.md](ERROR_HANDLING.md) |
| D-14 | **Auto-prune history to 500** | Bound disk/DB growth on a small device | [DATABASE.md](DATABASE.md) |
| D-15 | **MPN values kept as strings** | Reference values include `<3.0`, `>1100`, `–` | [MPN_DESIGN.md](MPN_DESIGN.md) |
| D-16 | **`opencv-python-headless`** | No GUI libs needed on a server; smaller install | [SECURITY.md](SECURITY.md) |

## How to add a decision

For a quick entry, append a row above. For anything with meaningful trade-offs or
that future readers will question, write a full ADR: copy
[adr/0000-template.md](adr/0000-template.md) to `adr/NNNN-short-title.md`, fill it in,
and reference it here.
