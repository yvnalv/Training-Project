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

See [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) for the full prioritized plan
(measurement, lighting/camera, fixed-ROI, retraining) and the **YOLO26** upgrade
evaluation.

- Build a labeled evaluation set (prerequisite for everything measurable).
- Control lighting and lock camera focus/exposure/white balance.
- Export the model to **NCNN** (~4× faster on Pi, near-zero risk).
- Curate and version the training dataset (see [MODEL_AND_DATA.md](MODEL_AND_DATA.md)).
- Retrain / fine-tune for fewer false positives at rack edges and labels.
- Evaluate retraining on **YOLO26n** (edge-first, NMS-free) vs the current model.
- Track model versions and metrics; stop committing multiple `.pt` checkpoints.

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
