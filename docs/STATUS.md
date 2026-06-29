# Project Status

_Last updated: 2026-06-29_

## Snapshot

VialVision is a **working, deployed prototype**. The full end-to-end flow —
image/stream → YOLO detection → MPN computation → result display → history — is
functional on both desktop and Raspberry Pi. Recent work focused on Raspberry Pi
deployment robustness (camera color/zoom, autostart, settings persistence).

Current branch: `fixing-upload-button`.

## Where we are

| Area | Status |
|---|---|
| Image upload → MPN result | ✅ Working |
| Live stream (client/webcam mode) | ✅ Working |
| Live stream (server/Pi camera mode) | ✅ Working |
| History (list, detail, delete, CSV export) | ✅ Working |
| MPN guideline reference view | ✅ Working |
| Settings persistence (DB-backed) | ✅ Working |
| Platform-aware camera defaults | ✅ Working |
| HTTPS / self-signed cert | ✅ Working |
| Raspberry Pi autostart (XDG + Wayfire) | ✅ Working |
| Pi camera color/zoom/focus | ✅ Fixed (2026-04-19) |
| Automated test suite | ❌ Not present (manual verification only) |
| User auth / accounts | ❌ Out of scope (single-device LAN tool) |

## Recently completed (newest first)

- **2026-04-19** — RPi autostart, DB-backed settings persistence, Pi camera color
  (BGR/RGB) fix, full-sensor zoom-out + sharpness + autofocus, network-IP display.
- **2026-04-16** — Added missing WebSocket deps; greedy-NMS dedup with hard cap of 9;
  fixed reversed positive label (`Yellow_Bubble` = 1); fixed Starlette 1.0
  `TemplateResponse` 500 on `/`.
- **2026-02-24** — SQLite persistence, history + detail modal, CSV export, MPN table.
- **2026-02-23** — Dark/lime UI, responsive layout for RPi 7" LCD.

See [../CHANGELOG.md](../CHANGELOG.md) for the complete history.

## What's next

See [ROADMAP.md](ROADMAP.md) for the full plan. Near-term candidates:

1. Add a minimal automated test suite (the two root `test_*.py` scripts call a
   removed `run_inference` signature and are stale — see [TESTING.md](TESTING.md)).
2. Tighten the over/under-detection handling UX (clear messaging when `total_tubes
   != 9`).
3. Model accuracy improvements / retraining (see [MODEL_AND_DATA.md](MODEL_AND_DATA.md)).

## Known issues / debt

- Root `test_api.py` / `test_local.py` are outdated (reference old API).
- No connection pooling — every DB call opens/closes a SQLite connection (fine at
  current scale; see [DATABASE.md](DATABASE.md)).
- Self-signed certificate requires a manual browser trust step per device.
- Multiple model checkpoints are committed to the repo (`best.pt`, `best (backup).pt`,
  `best_old.pt`, `vialvision_2.pt`, `yolov8n.pt`) — see [MODEL_AND_DATA.md](MODEL_AND_DATA.md).
