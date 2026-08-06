# Project Status

_Last updated: 2026-08-03_

## Snapshot

VialVision is a **working, deployed prototype**. The full end-to-end flow —
image/stream → YOLO detection → MPN computation → result display → history — is
functional on both desktop and Raspberry Pi. Current focus is a **model upgrade**
(YOLOv8n → YOLO26 object detection) to improve prediction accuracy; an interim YOLO26n
has been trained and exported to NCNN (not yet integrated into the app).

Current branch: `Refactor-Yolo26`.

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

- **2026-08-04** — ✅ **Rack detection working.** Retrained YOLO26n on the rack-inclusive
  dataset (`VialVision2.0 v2`, racks in train/valid/test): val mAP50 **0.966**. All 5 real
  rack photos now detect **9 tubes → MPN** through the full app pipeline (the interim
  single-tube model managed only 1–2). Exported NCNN, swapped into the app (`models/`).
  Remaining refinement: classification on the `yellow_positive ↔ yellow_negative`
  boundary (recall ~0.73) — a data problem, see [NEXT_STEPS.md](NEXT_STEPS.md) Phase 5.
- **2026-08-04** — Wired the trained model into the app (`models/` dir + NCNN/`.pt`
  resolution, `Yellow_Bubble → yellow_positive` rename) and **tested on real 9-tube
  racks**. Interim YOLO26n **fails to localize racks** (1–2 clustered boxes/rack).
  **Root cause: the `VialVision2.0 v1` dataset is single-tube-only** — the old `best.pt`
  (trained on rack images) detects **9/9** on the same photos. So detection is the right
  approach; the fix is a **rack-inclusive training set**. Annotating ~70–79 rack photos
  now. See [NEXT_STEPS.md](NEXT_STEPS.md).
- **2026-08-03** — Trained interim **YOLO26n** object detector on the Roboflow dataset
  (3 classes: `yellow_positive`/`yellow_negative`/`purple_negative`) on an RTX 4060.
  Val mAP50 **0.992**, test mAP50 **0.948**; `yolo26n` chosen over `yolo26s` (tied
  accuracy, 4× smaller). Exported to **NCNN**, parity verified. `yellow_negative` is the
  weakest class → data-limited (see durable-improvement levers in
  [NEXT_STEPS.md](NEXT_STEPS.md) Phase 5). **Not yet integrated into the app.**
- **2026-06-29** — Finalized the YOLO26 object-detection plan, 3-class label schema,
  Roboflow preprocessing/augmentation policy; added `training/` scripts.
- **2026-04-19** — RPi autostart, DB-backed settings persistence, Pi camera color
  (BGR/RGB) fix, full-sensor zoom-out + sharpness + autofocus, network-IP display.
- **2026-04-16** — Added missing WebSocket deps; greedy-NMS dedup with hard cap of 9;
  fixed reversed positive label (`Yellow_Bubble` = 1); fixed Starlette 1.0
  `TemplateResponse` 500 on `/`.
- **2026-02-24** — SQLite persistence, history + detail modal, CSV export, MPN table.
- **2026-02-23** — Dark/lime UI, responsive layout for RPi 7" LCD.

See [../CHANGELOG.md](../CHANGELOG.md) for the complete history.

## What's next

**Active focus: prediction accuracy** (client-reported). Upgrading YOLOv8n → **YOLO26
object detection**, deployed via **NCNN on a Raspberry Pi 5**. Full plan in
**[NEXT_STEPS.md](NEXT_STEPS.md)**.

Immediate next steps:

1. **Improve classification accuracy** — `yellow_negative` is the weak class (recall
   ~0.73) and drives the occasional wrong pattern (e.g. an unusual `P232`). The fix is
   more `yellow_negative` + clear positive/negative rack examples, plus good jig
   lighting for the bubble-vs-no-bubble call. See the durable-improvement levers in
   [NEXT_STEPS.md](NEXT_STEPS.md) Phase 5.
2. **On-device (Pi) validation** — deploy the NCNN model to the Pi 5, `pip install ncnn`,
   confirm 9-tube detection + latency in the real setup.
3. **Rack-only eval metric** — measure on the 8 rack test images specifically (overall
   test mAP is inflated by the single-tube images).

Supporting docs: label/preprocessing/augmentation policy in
[LABELING_STRATEGY.md](LABELING_STRATEGY.md); background in
[ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md); hardware in [HARDWARE.md](HARDWARE.md).

Other near-term candidates (see [ROADMAP.md](ROADMAP.md)):

1. Add a minimal automated test suite (the two root `test_*.py` scripts call a
   removed `run_inference` signature and are stale — see [TESTING.md](TESTING.md)).
2. Tighten the over/under-detection handling UX (clear messaging when `total_tubes
   != 9`).
3. Low-risk reliability fixes folded into Phase 2.3 of [NEXT_STEPS.md](NEXT_STEPS.md).

## Known issues / debt

- Root `test_api.py` / `test_local.py` are outdated (reference old API).
- No connection pooling — every DB call opens/closes a SQLite connection (fine at
  current scale; see [DATABASE.md](DATABASE.md)).
- Self-signed certificate requires a manual browser trust step per device.
- Multiple model checkpoints are committed to the repo (`best.pt`, `best (backup).pt`,
  `best_old.pt`, `vialvision_2.pt`, `yolov8n.pt`) — see [MODEL_AND_DATA.md](MODEL_AND_DATA.md).
