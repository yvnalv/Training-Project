# Next Steps — Accuracy Improvement Plan

_Created: 2026-06-29 · Phase 0 starts: **2026-06-30**_

This is the sequenced action plan to address the client's **prediction-accuracy**
complaint. It operationalizes [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) and
[HARDWARE.md](HARDWARE.md) into ordered, gated steps.

> **Governing principle:** do not change anything you cannot measure first. Each phase
> ends in a **gate** — re-measure, and stop early if accuracy is already acceptable.
> Order is **cheapest / highest-leverage first**; the "upgrade the model / buy a
> Jetson" instinct is deliberately **last**.

## Status

| Phase | Goal | State |
|---|---|---|
| 0 | Establish a measurable baseline | ⏳ Starts 2026-06-30 |
| 1 | Fix the input (lighting + camera lock) | ⬜ Not started |
| 2 | Cheap software wins (NCNN, full-res, voting) | ⬜ Not started |
| 3 | Structural accuracy (fixture/ROI or retrain) | ⬜ Not started |
| 4 | Model upgrade (YOLO26) + hardware | ⬜ Not started |

Owners: _TBD_. Effort estimates are rough.

---

## Phase 0 — Establish a baseline  ·  starts 2026-06-30  ·  ~1–2 days

Nothing else is decidable without this.

- [ ] **0.1 Collect a labeled eval set** — ~200–500 photos *from the actual rig*, each
  tagged with the correct tube pattern (and ideally per-tube positive/negative).
  **Include the client's problem images.**
- [ ] **0.2 Diagnose the failure mode** — sort misreads into **wrong count (≠ 9)** vs
  **wrong positive/negative**. This split decides whether Phase 3 leans fixture/ROI or
  retraining.
- [ ] **0.3 Build the offline evaluation script** — runs the current `best.pt` over the
  eval set and prints **count accuracy**, **per-tube accuracy**, **MPN-pattern
  accuracy**. This is the baseline number to beat.

**Gate:** a baseline number exists, and the dominant failure mode is known.

---

## Phase 1 — Fix the input (cheap, biggest accuracy lever)  ·  ~1–3 days + parts

- [ ] **1.1 Controlled lighting** — LED ring / light box / diffuser; back/side-light the
  bubbles. (~$30)
- [ ] **1.2 Lock the camera** — manual focus at ~19 cm, fixed exposure, fixed white
  balance (kill AWB drift). Code-only change in [../app/camera.py](../app/camera.py);
  see [CAMERA.md](CAMERA.md).
- [ ] **1.3 Re-run the eval script** — measure the lift from lighting + locked camera.

**Gate:** if accuracy is now acceptable, **ship and stop here.**

---

## Phase 2 — Cheap software wins (no new hardware)  ·  ~2–4 days

- [ ] **2.1 Export the model to NCNN**, verify accuracy parity on the eval set,
  benchmark latency (~4× faster on Pi). Ship if parity holds. See
  [HARDWARE.md](HARDWARE.md) §3.
- [ ] **2.2 Decouple capture from preview** — run the `/predict` / `/capture` path at
  **full resolution** (drop the 50% downscale) + **multi-frame voting** (e.g. 5 frames,
  majority-vote per tube). Re-measure. See
  [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).
- [ ] **2.3 Fold in low-risk reliability fixes** while in the code (do **not** affect
  accuracy, but remove real correctness/concurrency risks):
  - move inference off the async event loop (`asyncio.to_thread`);
  - resolve `best.pt` by absolute path;
  - use a single shared `Camera` instance.
  See [ERROR_HANDLING.md](ERROR_HANDLING.md) / the analysis in [STATUS.md](STATUS.md).

**Gate:** re-measure. Likely acceptable for most setups by here.

---

## Phase 3 — Structural accuracy (only if still short)  ·  ~1–2 weeks

Choose based on the Phase 0.2 diagnosis:

- [ ] **3.A Wrong-count dominant** → add a **fixture/jig** to fix the rack position and
  switch to **fixed 9-ROI** classification. Eliminates the count failure mode and the
  dedup over-merge risk. See [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) §1.1.
- [ ] **3.B Wrong-reading dominant** → **retrain on the rig dataset** using the
  *current* architecture first (isolates the data effect from the model effect).
  Re-measure. See [MODEL_AND_DATA.md](MODEL_AND_DATA.md).

**Gate:** re-measure against baseline.

---

## Phase 4 — Model upgrade + hardware (last, not first)  ·  ~1–2 weeks

- [ ] **4.1 Retrain YOLO26n** on the rig data; compare head-to-head vs the current model
  on the eval set (accuracy + Pi latency).
- [ ] **4.2 Deploy the winner via NCNN**; re-tune confidence + dedup thresholds
  (YOLO26 is **NMS-free** — the YOLO-level `iou` / `agnostic_nms` args become moot).
- [ ] **4.3 Hardware only if needed** — Raspberry Pi 5 (8 GB) + good camera + lighting
  before any Jetson. See [HARDWARE.md](HARDWARE.md).

---

## The shape of it

```
Phase 0  measure ──► Phase 1  fix input ──► (good enough? ship)
                                  │ no
                                  ▼
Phase 2  NCNN + full-res + voting ──► (good enough? ship)
                                  │ no
                                  ▼
Phase 3  fixture/ROI  or  retrain ──► Phase 4  YOLO26 + hardware
```

## How every step is validated

Run the change against the Phase-0 eval set and report:
- **Count accuracy** — % of images with exactly 9 tubes detected.
- **Per-tube accuracy** — % of tubes classified correctly.
- **MPN-pattern accuracy** — % where final `P{x}{y}{z}` matches ground truth (the
  number the client actually cares about).
- **Pi latency** — median on-device inference time, per export format.

See [TESTING.md](TESTING.md) for where the harness should live.
