# Next Steps — End-to-End Plan

_Created: 2026-06-29 · Phase 0 starts: **2026-06-30**_

Complete, end-to-end plan to rebuild VialVision's reading pipeline for higher accuracy
(and speed) on the fixed jig: **fixed-ROI per-tube classification** with a **retrained
YOLO26 classifier**. Covers dataset collection → labeling → annotation → modeling →
export → app integration → on-device rollout → continuous improvement.

Companion docs: [LABELING_STRATEGY.md](LABELING_STRATEGY.md),
[ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md), [HARDWARE.md](HARDWARE.md),
[MODEL_AND_DATA.md](MODEL_AND_DATA.md), [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

---

## Decisions locked (discussion 2026-06-29)

| # | Decision |
|---|---|
| Fixture | **Fixed jig** holds Pi + camera + rack in a fixed geometry → tube positions are known pixel coordinates ✅ |
| Architecture | **Path B — fixed-ROI + per-tube classification** (no detection, no NMS, no dedup, no "count ≠ 9") |
| Model | **YOLO26 classifier** (`yolo26n-cls`, compare `yolo26s-cls`), retrained on our data; export **NCNN** |
| Labels | **4 classes** (`Purple_Bubble`, `Purple_NoBubble`, `Yellow_Bubble`, `Yellow_NoBubble`), binary collapse in code; positive = `Yellow_Bubble` only |
| Data | Combine **previous** (detection boxes → crops) + **new** (single-tube photos), captured **through the production jig** |
| Hardware | **Raspberry Pi 5 (8 GB)** + NCNN; optional Hailo AI HAT+ for headroom |
| Priority | **Accuracy first**, speed still important |
| Sequencing | This supersedes the earlier tiered accuracy plan; it *is* the Phase-4 model work, now with a committed architecture |

---

## Target architecture (what we're building)

```
Camera frame (full res, via jig)
      │
 [optional] alignment check (fiducial / rack-edge) — correct small shifts
      │
 crop 9 FIXED ROIs  (positions from one-time jig calibration; grouped 1-3 | 4-6 | 7-9)
      │
 classify each crop → 4-class softmax → argmax
      │
 emit 9 "detection" dicts { label, confidence, bbox=ROI }   ← SAME contract as today
      │
 detections_to_tubes()  → Yellow_Bubble=1, else 0   (unchanged)
      │
 tubes_to_xyz() → pattern "P{x}{y}{z}" → lookup_mpn() → MPN + CI + risk   (unchanged)
```

**Key design choice:** the new inference path returns the **same detection-dict shape**
the app already consumes, so **MPN lookup, the database, the REST/WebSocket contract,
and the entire frontend stay unchanged.** Only the "how we get the 9 labels" is
replaced. `total_tubes` is always 9, so MPN always computes.

**What is removed/retired:** `suppress_duplicate_tubes()` (greedy NMS + dedup), the
hard-cap-9, the 50% downscale, and the `iou`/`agnostic_nms` YOLO args — none are needed
once positions are fixed and we classify crops directly.

---

## Guiding principles

1. **Measure first, gate every phase.** No integration before the model beats the
   baseline on the held-out eval set.
2. **Train through the production jig.** Training crops must come from the same jig,
   camera, lighting, and distance as production — exact domain match is the biggest
   accuracy lever.
3. **Preserve the output contract** (detection dicts) to minimize blast radius.
4. **Preserve the 4 class names and IDs** (0–3) so we can fine-tune and stay compatible.
5. **Version datasets and models**; keep a manifest and a held-out test set that is
   never trained on.

## Success metrics (definition of done)

Because positions are fixed, "count accuracy" is trivially 9 — the meaningful metrics are:
- **Per-condition accuracy** (4-class) + confusion matrix (watch `Yellow_Bubble ↔
  Yellow_NoBubble` and `Yellow_Bubble ↔ Purple_Bubble`).
- **Per-tube binary accuracy** (positive/negative — what drives the pattern).
- **MPN-pattern accuracy** — % of racks whose final `P{x}{y}{z}` matches ground truth
  (**the number the client experiences**).
- **On-device latency** on the Pi 5 (per export format).

---

## Phase 0 — Foundations  ·  starts 2026-06-30  ·  ~2–4 days

- [ ] **0.1 Finalize the jig & fix the optics.** Mount Pi + camera + rack in the jig.
  **Lock the camera** (manual focus at the jig distance, fixed exposure, fixed white
  balance — kill AWB drift; see [CAMERA.md](CAMERA.md)). Set **controlled lighting**
  (even, diffuse; back/side-light so bubbles pop). This rig is *both* the training-data
  source and the production capture — they must be identical.
- [ ] **0.2 ROI calibration.** Capture a reference frame through the jig. Define the
  **9 tube ROIs** as `(x, y, w, h)` in image pixels, **ordered left→right and grouped**
  (tubes 1–3, 4–6, 7–9) to match `tubes_to_xyz`. Use **generous margins** to absorb
  rack-insertion tolerance. Store as a config (e.g. `roi_config.json`). *Optional
  robustness:* add fiducial markers to the jig/rack for automatic small-shift
  correction.
- [ ] **0.3 Eval harness + baseline.** Build a held-out **evaluation set** (rack images
  through the jig, with ground-truth per-tube conditions and the correct pattern).
  Write a scoring script reporting the four metrics above. **Baseline the current
  `best.pt`** so every later change is measured against a real number.

**Gate:** jig geometry is reproducible, the 9 ROIs are defined and verified on several
inserts, and baseline metrics exist.

---

## Phase 1 — Dataset collection  ·  ~3–7 days (spread)

- [ ] **1.1 Capture through the jig only.** All training images use the production jig,
  camera, lighting, and distance. Two complementary sources:
  - **Single-tube photos** per category (your plan) → native classification data.
  - **Full-rack photos** in varied patterns → crop the 9 ROIs into per-tube images.
- [ ] **1.2 Coverage & balance.**
  - All **4 conditions**, well represented.
  - Every one of the **9 positions** (avoid position bias — a tube in slot 1 vs slot 9
    can differ in lighting/perspective even in a jig).
  - **Over-collect `Yellow_Bubble` (positive)** — it is the rare-but-critical class
    (real racks are often positive-sparse). See [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §8.
  - Include realistic variation the rig will see: minor lighting changes, tube
    insertion tolerance, bubble sizes, color intensities.
- [ ] **1.3 Volume & manifest.** Target a healthy count per class (aim for a few hundred
  crops per class minimum; more for the positive). Record every image in a **manifest
  CSV** (source, capture date, condition, position, rack pattern).

**Gate:** per-class counts are adequate and reasonably balanced (positive class not
starved); manifest complete.

---

## Phase 2 — Labeling & annotation  ·  ~2–5 days

Follow [LABELING_STRATEGY.md](LABELING_STRATEGY.md) in full.

- [ ] **2.1 Labeling guide.** Finalize example images for each of the 4 classes and the
  **edge-case rules**: minimum-bubble definition (with examples), color tie-break for
  transitional hues, exclude occluded/blurred, meniscus/reflection ≠ bubble.
- [ ] **2.2 Annotate (classification / ImageFolder).** Sort every crop into one of the 4
  class folders (`Yellow_Bubble/`, `Yellow_NoBubble/`, `Purple_Bubble/`,
  `Purple_NoBubble/`). **Preserve the exact class names.**
- [ ] **2.3 Convert previous detection data.** Crop each labeled box from the old rack
  images into the matching class folder (reuse of existing labels — no re-labeling).
- [ ] **2.4 QC review.** A second reviewer spot-checks against the guide; fix
  inconsistencies. Watch mislabels between the confusable pairs.

**Gate:** labeled set passes QC; class names/IDs correct.

---

## Phase 3 — Dataset assembly  ·  ~1–2 days

- [ ] **3.1 Merge & de-duplicate.** Combine old-crops + new-crops; remove near-duplicate
  frames so one tube doesn't dominate.
- [ ] **3.2 Balance.** Equalize class counts via oversampling/augmentation of minority
  classes, or plan class weights at train time.
- [ ] **3.3 Split by sample (no leakage).** All crops from one rack photo / tube session
  stay in the same split. ~70/15/15 train/val/test. **The test split = the Phase-0
  eval set — never trained on.** See [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §9.
- [ ] **3.4 Freeze `dataset vX`** (ImageFolder tree + manifest) for reproducibility.

**Gate:** reproducible, balanced, leak-free dataset version exists.

---

## Phase 4 — Modeling: train, evaluate, iterate  ·  ~3–7 days

- [ ] **4.1 Train the classifier.** `YOLO("yolo26n-cls.pt").train(data=<dataset_dir>,
  epochs=…, imgsz=<crop size, e.g. 128>, …)`. Use mild, realistic augmentation
  (color jitter within real range, small rotation/translation for insertion tolerance,
  brightness); **class weights / oversampling** for the positive class. Keep the
  toolchain consistent with the installed ultralytics (8.4.37, ships YOLO26).
- [ ] **4.2 Compare variants.** Evaluate `yolo26n-cls` vs `yolo26s-cls` (accuracy first;
  both are cheap on 9 small crops). Optionally a tiny CNN baseline for reference.
- [ ] **4.3 Evaluate on the held-out test set.** Report **per-condition confusion**,
  **per-tube binary accuracy**, **MPN-pattern accuracy**, and Pi latency (measured in
  Phase 5). Do targeted error analysis on the confusable pairs.
- [ ] **4.4 Iterate.** Address errors with *data* first (more/better examples of the
  failing condition/position), then hyperparameters. Re-measure each time.
- [ ] **4.5 Select the winner** vs the Phase-0 baseline.

**Gate:** chosen model beats baseline on **MPN-pattern accuracy** by the agreed margin,
with acceptable per-tube accuracy.

---

## Phase 5 — Export & optimize for the Pi  ·  ~1–2 days

- [ ] **5.1 Export to NCNN**; verify accuracy **parity** vs PyTorch on the test set
  (quantization/format must not degrade results).
- [ ] **5.2 Benchmark on the Pi 5.** Measure end-to-end latency (capture → 9-crop
  classify → MPN). **Batch the 9 crops into one inference call.** Confirm it meets the
  latency target.
- [ ] **5.3 Variant/hardware decision.** Pick `n` vs `s` from the accuracy/latency
  curve. If more headroom is wanted (e.g. `s`/`m` at video rates for the live preview),
  evaluate the **Hailo AI HAT+** ([HARDWARE.md](HARDWARE.md)).

**Gate:** on-device latency + accuracy both acceptable.

---

## Phase 6 — App integration  ·  ~3–6 days

- [ ] **6.1 New inference path.** Replace `run_inference_with_count()` internals (or add
  `classify_rack()`) that: loads the full-res frame, crops the 9 ROIs from
  `roi_config.json`, classifies each (batched), and returns the **same list of
  detection dicts** `{ label, confidence, bbox }` (bbox = the ROI). `total_count`
  always 9.
- [ ] **6.2 Retire detection-era code.** Remove/retire `suppress_duplicate_tubes()`, the
  hard-cap-9, the 50% downscale, and `iou`/`agnostic_nms`. Update the annotation drawing
  to render the 9 ROIs + `1`/`0` labels + count.
- [ ] **6.3 Keep downstream untouched.** `detections_to_tubes`, `tubes_to_xyz`,
  `_compute_mpn`, DB, `/predict`, `/capture`, `/ws` (client + server), and the frontend
  all stay as-is because the output contract is preserved. Verify class-label strings
  still match `Yellow_Bubble`.
- [ ] **6.4 Config & model loading.** Load the NCNN model (dir path) and
  `roi_config.json`; resolve paths absolutely (not CWD-relative).
- [ ] **6.5 Fold in low-risk reliability fixes** while in this code: run inference off
  the async event loop (`asyncio.to_thread`), single shared `Camera` instance, robust
  model path. See [ERROR_HANDLING.md](ERROR_HANDLING.md) / [STATUS.md](STATUS.md).

**Gate:** running the app over the eval set (through `/predict`) reproduces the Phase-4
metrics — no regression from the standalone model.

---

## Phase 7 — On-device validation & rollout  ·  ~2–4 days

- [ ] **7.1 Deploy to the Pi** in the jig; run the **full eval set end-to-end on-device**
  and confirm metrics + latency match the bench numbers.
- [ ] **7.2 ROI sanity across inserts.** Re-insert the rack several times; confirm the
  fixed ROIs still frame each tube (adjust margins / enable fiducial alignment if not).
- [ ] **7.3 Field trial with the client.** Collect real readings and **log every
  misread** for Phase 8.
- [ ] **7.4 Update docs & changelog.** [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md)
  (new ROI-classify flow), [ARCHITECTURE.md](ARCHITECTURE.md),
  [API_SPEC.md](API_SPEC.md) (labels/notes), [MODEL_AND_DATA.md](MODEL_AND_DATA.md),
  [MODULES.md](MODULES.md), and [../CHANGELOG.md](../CHANGELOG.md).

**Gate:** client-acceptance accuracy met in the field trial.

---

## Phase 8 — Continuous improvement  ·  ongoing

- [ ] **8.1 Active learning.** Log low-confidence crops (and any client-flagged
  misreads), label them, fold into the next `dataset vX+1`, retrain, re-measure.
- [ ] **8.2 Maintenance.** Re-run ROI calibration if the jig geometry changes; **version
  every model + dataset**; keep only the active model tracked in the repo (retire the
  extra `.pt` checkpoints — see [MODEL_AND_DATA.md](MODEL_AND_DATA.md)).

---

## Dependency flow

```
0 Foundations ─► 1 Collect ─► 2 Label ─► 3 Assemble ─► 4 Train/Eval
      (jig+ROI+eval)                                        │ beats baseline?
                                                            ▼
                                     5 Export/NCNN ─► 6 Integrate ─► 7 On-device rollout ─► 8 Improve
```

Each arrow is a gate — do not proceed until the previous phase's gate passes.

## Risk register

| Risk | Mitigation |
|---|---|
| Rack insertion tolerance shifts tubes out of the ROIs | Generous ROI margins; fiducial/edge alignment; re-check across inserts (7.2) |
| Positive class (`Yellow_Bubble`) too rare in data | Deliberate over-collection; class weights/oversampling (1.2, 3.2) |
| Lighting drift changes "yellow" | Locked camera + controlled lighting; lighting augmentation (0.1, 4.1) |
| NCNN export degrades accuracy | Parity check vs PyTorch before shipping (5.1) |
| Training data not captured via the jig → domain mismatch | Mandate jig capture for all training data (1.1) |
| Label inconsistency between annotators | Labeling guide + QC review + confusion-matrix watch (2.1, 2.4) |
| Data leakage between splits | Split by sample, not by crop (3.3) |

## Notes

- This plan **retires the detection pipeline** in favor of fixed-ROI classification. If
  the jig ever cannot guarantee position, the detection fallback (Path A with
  `yolo26s`) remains documented in [LABELING_STRATEGY.md](LABELING_STRATEGY.md) §3.
- Nothing here is implemented yet — it is the agreed plan. Phase 0 begins 2026-06-30.
