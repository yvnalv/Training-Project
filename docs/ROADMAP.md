# Roadmap

This roadmap is forward-looking and intentionally lightweight. For what is already
done, see [STATUS.md](STATUS.md) and [../CHANGELOG.md](../CHANGELOG.md).

## Phase 0 — Done (shipped)

- Core inference pipeline (detect → dedup → annotate → MPN).
- Image upload, live stream (client + server modes), single-frame capture.
- SQLite persistence, history, detail modal, CSV export, auto-pruning.
- MPN guideline reference view.
- DB-backed settings with platform-aware camera defaults.
- HTTPS, Raspberry Pi camera fixes, and XDG/Wayfire autostart.

## Phase 1 — Reliability & correctness (near term)

- **Automated tests.** Replace the stale root `test_*.py` scripts with a small
  pytest suite covering: NMS dedup + hard cap, `detections_to_tubes`, `tubes_to_xyz`,
  `lookup_mpn`, and `_compute_mpn` (including the `total_tubes != 9` path). See
  [TESTING.md](TESTING.md).
- **Detection-count UX.** When `total_tubes != 9`, surface clear guidance (re-frame,
  adjust lighting/confidence) instead of a bare `N/A`.
- **Confidence-threshold tuning** guidance baked into the UI.

## Phase 2 — Model quality & accuracy

**Committed plan (2026-06-29): retrain as YOLO26 object detection + NCNN on Pi 5.** The
sequenced build plan is in [NEXT_STEPS.md](NEXT_STEPS.md); background/rationale in
[ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md); label/preprocessing/augmentation
policy in [LABELING_STRATEGY.md](LABELING_STRATEGY.md).

- Build a labeled **new-jig** evaluation set (prerequisite for everything measurable).
- Control lighting and lock camera focus/exposure/white balance.
- Retrain **YOLO26** detection (`yolo26n`, compare `yolo26s`) on the Roboflow dataset.
- Export to **NCNN** (~4× faster on Pi, near-zero risk); validate NMS-free vs the custom
  dedup.
- Curate and version the training dataset (see [MODEL_AND_DATA.md](MODEL_AND_DATA.md));
  fix the `Yellow_NoBubble` shortage.
- Track model versions and metrics; stop committing multiple `.pt` checkpoints.
- *(Fallback if accuracy plateaus: fixed-ROI per-tube classification.)*

## Phase 3 — Operability

- Optional Docker/compose packaging for non-Pi deployment.
- Health/metrics surface beyond `/health` (e.g. last inference latency).
- Configurable history cap and storage location.
- Hardware refresh as needed — see [HARDWARE.md](HARDWARE.md) (Raspberry Pi 5 + NCNN
  recommended; optional Hailo AI HAT+ for video-rate headroom).

## Phase 4 — Nice-to-haves

- Multi-rack / batch processing.
- Trusted certificate flow (e.g. mkcert) to remove the manual browser warning.
- Per-result notes / operator annotations in history.

## Explicitly not planned

- User accounts, authentication, or multi-tenancy.
- Cloud sync or external service integrations.
- Anything accounting/ERP-related.
