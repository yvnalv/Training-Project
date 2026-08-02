# Next Steps — End-to-End Plan

_Created: 2026-06-29 · Last updated: 2026-06-29 · Phase 0 (design team) starts: **2026-06-30**_

Complete, end-to-end plan to upgrade VialVision's model from **YOLOv8n → YOLO26**,
**keeping the object-detection architecture**, and deploying via **NCNN on a Raspberry
Pi 5**. Covers dataset (Roboflow) → preprocessing/augmentation → training → export →
app integration → new-jig data + retrain → rollout → continuous improvement.

Companion docs: [LABELING_STRATEGY.md](LABELING_STRATEGY.md) (label schema +
preprocessing/augmentation policy), [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md),
[HARDWARE.md](HARDWARE.md), [MODEL_AND_DATA.md](MODEL_AND_DATA.md),
[INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

---

## Decisions locked (discussion 2026-06-29)

| # | Decision |
|---|---|
| Architecture | **Object detection (Path A)** — keep the current detection pipeline. The prior fixed-ROI classification idea (Path B) is shelved as a documented fallback. |
| Model | **YOLO26 detection** — `yolo26n` (start), compare `yolo26s`; export **NCNN** for the Pi 5 |
| Dataset | Existing **Roboflow detection** dataset (mixed 1-tube + 9-tube photos, **every tube boxed**); **downloaded in YOLO26 format** |
| Labels | **3 classes:** `yellow_positive` (=1), `yellow_negative` (=0), `purple_negative` (=0). Positive = `yellow_positive` only. Purple-with-bubble → `purple_negative` (hard negative). |
| Fixture | **Fixed jig** (Pi + camera + rack) — used for capture consistency & locked lighting (helps detection accuracy too), not for ROI cropping |
| Hardware | **Raspberry Pi 5 (8 GB)** + NCNN; optional Hailo AI HAT+ for headroom |
| Priority | **Accuracy first**, speed still important |

Verified facts: current `best.pt` is **YOLOv8n**, 4 classes, ~3.0 M params; env has
**ultralytics 8.4.37** (ships YOLO26). See [MODEL_AND_DATA.md](MODEL_AND_DATA.md).

---

## Current dataset snapshot (old-jig bootstrap)

Annotated on Roboflow (object detection). Counts of the single-tube category photos:

| Class | Count | Notes |
|---|---|---|
| `yellow_positive` (positive) | **422** | ✅ Well represented |
| `purple_negative` (negative) | 231 | Ensure enough purple-**with-bubble** hard negatives inside this |
| `yellow_negative` (negative) | **58** | 🔴 Too few — the critical `yellow_positive ↔ yellow_negative` boundary |

This is a **bootstrap** set from the **old jig** — good enough to shake out the whole
pipeline and get an early signal, **not** the final training set. The new jig may differ
in framing/lighting, so plan a fresh collection (Phase 5). See §"Parallel tracks".

---

## Target architecture (unchanged pipeline, new model)

```
Camera frame (via jig)
      │
 YOLO26 detect (NMS-free / end-to-end)   ← was YOLOv8n
      │
 suppress_duplicate_tubes()  ← VALIDATE: may be redundant with NMS-free; keep hard-cap-9 + L→R sort
      │
 detections_to_tubes()  → yellow_positive=1, else 0   (label string updated — see Phase 4)
      │
 tubes_to_xyz() → pattern "P{x}{y}{z}" → lookup_mpn() → MPN + CI + risk   (unchanged)
```

**Blast radius is small:** only the model (and a couple of inference args) change.
`detections_to_tubes`, `tubes_to_xyz`, `_compute_mpn`, the DB, the REST/WebSocket
contract, and the entire frontend stay as-is.

---

## Guiding principles

1. **Measure first, gate every phase.** No rollout before the model beats the baseline
   on a **new-jig** eval set.
2. **Protect the signal.** Yellow-vs-purple **color** and **bubble** detail are the
   whole game — no hue augmentation, no bubble-erasing transforms (see
   [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §"Preprocessing & augmentation").
3. **Positive label is now `yellow_positive`** (renamed from `Yellow_Bubble`) — the code
   that keys the positive off that string must be updated (Phase 4.4).
4. **The eval/test set must be new-jig** (production domain); never mix old-jig images
   into it.
5. **Version datasets and models.**

## Success metrics (definition of done)

- **mAP** (overall + per class) from `model.val()`.
- **Per-tube binary accuracy** (positive/negative — drives the pattern).
- **MPN-pattern accuracy** — % of racks whose final `P{x}{y}{z}` matches ground truth
  (**the number the client experiences**).
- **On-device latency** on the Pi 5 (per export format).
- Confusion focus: **`yellow_positive ↔ yellow_negative`** (costly false pos/neg) and
  **`yellow_positive ↔ purple_negative`** (color error).

---

## Parallel tracks

Two tracks run at once and converge at Phase 5:

- **Track A — design team (Phase 0, starts 2026-06-30):** finalize the jig, lock
  camera/lighting, build the **new-jig eval set**, baseline the current model.
- **Track B — modeling (now):** the Roboflow data is already annotated, so train an
  **interim YOLO26** on the bootstrap set to validate the export→train→integrate
  pipeline and get an early signal (Phases 1–4). Read interim numbers as **optimistic**
  (old-jig, `Yellow_NoBubble` only 58) — the real verdict comes from the new-jig eval
  set at Phase 5.

---

## Phase 0 — Foundations (Track A, design team)  ·  starts 2026-06-30  ·  ~2–4 days

- [ ] **0.1 Finalize the jig & lock the optics.** Mount Pi + camera + rack. **Lock the
  camera** (manual focus at the jig distance, fixed exposure, fixed white balance — kill
  AWB drift; see [CAMERA.md](CAMERA.md)). Set **controlled lighting** (even, diffuse;
  back/side-light so bubbles pop).
- [ ] **0.2 Build the new-jig eval set.** Capture held-out rack images **through the new
  jig**, with ground-truth per-tube conditions and the correct pattern. This is the only
  honest measure of production accuracy — **never train on it**.
- [ ] **0.3 Baseline the current model.** Run `best.pt` over the eval set; record mAP /
  per-tube / MPN-pattern accuracy + latency as the number to beat.

**Gate:** jig reproducible; new-jig eval set + baseline metrics exist.

---

## Phase 1 — Dataset prep in Roboflow (Track B)  ·  mostly done  ·  ~0.5–1 day

- [x] **1.1 Project settings confirmed.** Object detection; **3 classes** —
  `yellow_positive`, `yellow_negative`, `purple_negative`. Dataset **downloaded in
  YOLO26 format**. (Verify `purple_negative` includes purple-with-bubble hard negatives.)
- [ ] **1.2 Preprocessing** (applies to all images + inference): **Auto-Orient ON**,
  **Resize 640×640 (Fit/letterbox)**, **no Grayscale**, no contrast/tile. See
  [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §"Preprocessing & augmentation".
- [ ] **1.3 Augmentation** (training only) — **minimal and color-safe**: modest
  Brightness ±10%, Exposure ±10%, Rotation ±5°; multiplier ≤ 3×. **No Hue, no
  Saturation, no vertical flip, no Blur/Noise, no Cutout/Mosaic.**
- [ ] **1.4 Export** — choose the **YOLO26** format (native for the target model). If
  unavailable, **YOLOv11**/YOLOv8 work identically (the detection txt format is the
  same). Gives `data.yaml` + images/labels.

**Gate:** dataset version exported; preprocessing/augmentation policy applied.

> Data caveat: this is the old-jig bootstrap set; `Yellow_NoBubble` (58) is thin, so its
> interim metrics will be unreliable. Fixed in Phase 5.

---

## Phase 2 — Train YOLO26 detection (Track B)  ·  ~2–5 days

- [ ] **2.1 Train** with color/bubble-safe settings:
  ```python
  from ultralytics import YOLO
  model = YOLO("yolo26n.pt")                 # detection pretrained
  model.train(
      data="path/to/data.yaml", epochs=100, imgsz=640, patience=20,
      hsv_h=0.0,      # no hue shift — protect yellow vs purple
      hsv_s=0.3, hsv_v=0.4,
      flipud=0.0,     # no vertical flip (bubble is at top)
      fliplr=0.5, degrees=5.0,
  )
  ```
- [ ] **2.2 Compare `yolo26s`** (accuracy first; NCNN keeps `s` affordable on the Pi 5).
- [ ] **2.3 Evaluate** (`model.val()`): mAP, per-class, confusion — focus on the two
  confusable pairs above.
- [ ] **2.4 Iterate** — fix errors with **data first** (esp. `Yellow_NoBubble` and
  purple-bubble hard negatives), then hyperparameters.

**Gate:** interim model trains cleanly and the pipeline is validated end-to-end.

---

## Phase 3 — Export & Pi benchmark (Track B)  ·  ~1–2 days

- [ ] **3.1 Export NCNN:** `model.export(format="ncnn")`; verify accuracy **parity** vs
  PyTorch on the test set.
- [ ] **3.2 Benchmark on the Pi 5** (end-to-end capture → detect → MPN). Target the
  ~68 ms/frame NCNN ballpark ([HARDWARE.md](HARDWARE.md)).
- [ ] **3.3 Variant/hardware decision:** `n` vs `s` from the accuracy/latency curve;
  optional **Hailo AI HAT+** for headroom (e.g. `s`/`m` at video rates).

**Gate:** on-device latency + accuracy acceptable.

---

## Phase 4 — App integration (Track B, minimal)  ·  ~1–3 days

- [ ] **4.1 Swap the model** in [inference.py](../app/inference.py): point to the new
  weights / NCNN model dir; resolve the path absolutely (not CWD-relative).
- [ ] **4.2 NMS-free reconciliation.** YOLO26 is end-to-end, so `iou=0.6,
  agnostic_nms=True` become no-ops (remove them). **Validate `suppress_duplicate_tubes()`
  on real racks** — if YOLO26 emits ≤ 9 clean boxes, simplify it (keep only the
  hard-cap-9 + left→right sort as guards); otherwise keep it, re-tuned.
- [ ] **4.3 Reconsider the 50% downscale** ([inference.py:149-152](../app/inference.py#L149-L152))
  — for accuracy, try full/75% res on the capture path and measure.
- [ ] **4.4 Update the positive-label string (REQUIRED).** The new model emits
  **`yellow_positive`**, but the code hardcodes the old `"Yellow_Bubble"` in **4 places**
  ([inference.py:107](../app/inference.py#L107), [inference.py:203](../app/inference.py#L203),
  [script.js:573](../static/js/script.js#L573), [script.js:984](../static/js/script.js#L984)).
  Change them to `"yellow_positive"` — ideally via a single `POSITIVE_LABEL` constant.
  **If missed, every tube reads 0 → MPN always `P000` (silent catastrophic bug).**
  Everything else downstream (`tubes_to_xyz`, `_compute_mpn`, DB, `/predict`, `/capture`,
  `/ws`, frontend) stays unchanged.
- [ ] **4.5 Fold in low-risk reliability fixes** while here: inference off the async
  event loop (`asyncio.to_thread`), single shared `Camera`, robust model path. See
  [ERROR_HANDLING.md](ERROR_HANDLING.md) / [STATUS.md](STATUS.md).

**Gate:** app over the eval set reproduces the standalone model's metrics (no regression).

---

## Phase 5 — New-jig data + retrain (convergence of tracks)  ·  ~1–2 weeks

- [ ] **5.1 Collect through the new jig**, targeting the gaps: **`Yellow_NoBubble` up to
  ~200+**, balanced `Purple` (with enough purple-bubble hard negatives), all **9
  positions**, varied patterns. Keep the strong `Yellow_Bubble` set.
- [ ] **5.2 Merge old + new** with a `domain` field (`old_jig` / `new_jig`) in the
  manifest so the mix is managed and metrics can be sliced.
- [ ] **5.3 Retrain** (fine-tune from the interim model or retrain fresh); **evaluate on
  the new-jig eval set** — this is the real acceptance number.
- [ ] **5.4 Re-export NCNN**, re-benchmark, redeploy the winner.

**Gate:** model beats baseline on **new-jig MPN-pattern accuracy** by the agreed margin.

---

## Phase 6 — On-device validation & rollout  ·  ~2–4 days

- [ ] **6.1 Deploy to the Pi** in the jig; run the full new-jig eval set on-device;
  confirm metrics + latency.
- [ ] **6.2 Field trial with the client;** log every misread for Phase 7.
- [ ] **6.3 Update docs & changelog:** [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md),
  [ARCHITECTURE.md](ARCHITECTURE.md), [API_SPEC.md](API_SPEC.md),
  [MODEL_AND_DATA.md](MODEL_AND_DATA.md), [MODULES.md](MODULES.md),
  [../CHANGELOG.md](../CHANGELOG.md).

**Gate:** client-acceptance accuracy met in the field trial.

---

## Phase 7 — Continuous improvement  ·  ongoing

- [ ] **7.1 Active learning.** Log low-confidence detections + client-flagged misreads,
  label them, fold into the next dataset version, retrain, re-measure.
- [ ] **7.2 Maintenance.** Version every model + dataset; retire the extra `.pt`
  checkpoints in the repo root (keep only the active model) — see
  [MODEL_AND_DATA.md](MODEL_AND_DATA.md).

---

## Dependency flow

```
Track A:  0 Foundations (jig + new-jig eval set + baseline) ────────────────┐
                                                                            ▼
Track B:  1 Roboflow prep ─► 2 Train YOLO26 ─► 3 Export/NCNN ─► 4 Integrate ─► 5 New-jig retrain ─► 6 Rollout ─► 7 Improve
                                (interim signal)                              (real acceptance)
```

Each arrow is a gate — do not proceed until the previous gate passes.

## Risk register

| Risk | Mitigation |
|---|---|
| `yellow_negative` too few (58) → weak on the key boundary | Collect ~200+ on the new jig (5.1); interpret interim numbers cautiously |
| `purple_negative` merge hides missing purple-bubble hard negatives | Track purple-with-bubble count even within the merged class (1.1, 5.1) |
| **Class rename `Yellow_Bubble`→`yellow_positive` not applied in code** | Update the 4 hardcoded strings via a `POSITIVE_LABEL` constant (4.4); else MPN silently always `P000` |
| **Hue/color augmentation corrupts yellow vs purple** | `hsv_h=0.0`; no Roboflow Hue/Saturation (1.3, 2.1) |
| Bubble erased by blur/noise/cutout | Ban those augmentations (1.3) |
| Old-jig data ≠ new-jig domain | Bootstrap only; retrain on new-jig data (Phase 5); eval set is new-jig |
| NCNN export degrades accuracy | Parity check vs PyTorch (3.1) |
| NMS-free changes dedup behavior | Validate `suppress_duplicate_tubes` on real racks (4.2) |
| Model loaded by CWD-relative path | Resolve `best.pt`/NCNN dir absolutely (4.1) |

## Notes

- This plan **keeps object detection** and swaps YOLOv8n → YOLO26. The fixed-ROI
  classification alternative (Path B) remains documented in
  [LABELING_STRATEGY.md](LABELING_STRATEGY.md) as a fallback if detection accuracy ever
  plateaus.
- Nothing here is implemented yet — it is the agreed plan. Track A begins 2026-06-30;
  Track B (interim training on the existing Roboflow data) can start immediately.
