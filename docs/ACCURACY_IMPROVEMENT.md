# Accuracy Improvement Plan

_Purpose: a prioritized, tradeoff-aware plan for improving VialVision's prediction
accuracy, plus an evaluation of upgrading the detection model to **YOLO26**._

> **Context:** the client reports that prediction accuracy is not good enough. This
> doc is the reference for what to change, in what order, and why. It complements
> [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md), [CAMERA.md](CAMERA.md),
> [MODEL_AND_DATA.md](MODEL_AND_DATA.md), and [HARDWARE.md](HARDWARE.md) (which board
> to run on, with benchmarks).

---

## TL;DR

1. **Accuracy is currently unmeasurable** — there is no labeled evaluation set, so
   every threshold is tuned by eye. **Build one first** (Tier 0). Nothing else can be
   validated without it.
2. **The biggest wins are not "a better model."** This is a *fixed rig* (same rack,
   camera, distance). Controlled lighting, locked camera (focus/exposure/white
   balance), and exploiting the fixed geometry beat any architecture change.
3. **Upgrading to YOLO26 is worthwhile but modest and retraining-dependent.** Its
   headline gains are on COCO, not our 9-tube task. The genuinely large, *free* speed
   win is **exporting the model to NCNN** (~4× faster on a Raspberry Pi) — which then
   buys back the latency budget to *spend on accuracy* (full resolution, multi-frame).

---

## First, the framing: two kinds of "accuracy"

| Failure mode | Symptom | Root cause area |
|---|---|---|
| **Wrong tube count** (≠ 9) | Result shows `N/A` / no MPN | Detection / localization |
| **Wrong positive/negative** | MPN value is wrong | Classification (color + bubble) |

The fix differs by mode. **Collect a few real misread images and classify which mode
dominates** before investing — it changes the priority order below.

---

## Tier 0 — Do first (cheap; everything depends on it)

### 0.1 Build a labeled evaluation set
~200–500 images **from the actual rig**, each with the known-correct tube pattern
(and ideally per-tube positive/negative labels). This makes every later change
measurable (count accuracy, per-tube accuracy, end-to-end MPN-pattern accuracy).
- **Cost:** a few hours. **Tradeoff:** none — pure upside, and a prerequisite for
  retraining (Tier 2) and for benchmarking YOLO26.

### 0.2 Control the lighting
The whole classification keys on **color (yellow)** and **bubbles**. Add a light box /
LED ring / diffuser for even, shadow-free, consistent light; matte non-reflective
contrasting background. Bubbles are refractive — **back/side lighting** makes them pop.
- **Cost:** ~$20–50. **Tradeoff:** minor physical setup. Highest accuracy-per-dollar.

### 0.3 Lock the camera (stop "auto" everything)
For a fixed rig, continuous autofocus + auto-exposure + auto-white-balance are
*enemies of consistency* — AWB drift literally changes what "yellow" looks like
frame to frame. The Pi path currently uses continuous AF
([CAMERA.md](CAMERA.md), [camera.py:104-116](../app/camera.py#L104-L116)).
Calibrate once for the rig, then fix: manual focus (`AfMode` manual + `LensPosition`),
`AeEnable=False` (fixed exposure/gain), `AwbEnable=False` (fixed gains).
- **Cost:** code only. **Tradeoff:** must recalibrate if the rig/lighting changes —
  which is exactly the repeatability you want.

---

## Tier 1 — High-leverage code changes

### 1.1 Exploit the fixed geometry (fixed ROIs instead of free detection)
Because the rack sits in a known position, the 9 tube locations are essentially fixed
in the frame. Classifying **9 fixed regions** instead of "detect N tubes anywhere,
then dedup" eliminates:
- the wrong-count failure mode (you always have 9), and
- the dedup heuristics that can **merge two real tubes** or **drop a real
  low-confidence tube** ([inference.py:42-93](../app/inference.py#L42-L93)).

Needs a **mechanical fixture/jig** so the rack lands in the same spot (cheap,
3D-printed). Optionally a light alignment step (detect rack corners) for small shifts.
- **Tradeoff:** less flexible to repositioning; needs the fixture. Most robust
  architecture for a fixed appliance.

### 1.2 Decouple the live preview from the measurement
The live stream is for **aiming** (needs speed); the captured reading is for
**measuring** (needs accuracy; latency barely matters — a person waits for one
result). Today both use the same 50% downscale + nano model. Make `/predict` and
`/capture` the **high-accuracy path** (full resolution, bigger/heavier model,
multi-frame), keep the stream light.
- **Tradeoff:** a slower capture (1–3 s) for a correct reading — almost always worth it.

### 1.3 Stop (or reduce) the 50% downscale on the measurement path
Inference currently halves the image before YOLO
([inference.py:149-152](../app/inference.py#L149-L152)) — discarding exactly the fine
detail that distinguishes bubble vs no-bubble. Run full/75% res on the capture path;
measure the accuracy/latency curve on the Tier-0 eval set.
- **Tradeoff:** slower inference (mitigated by NCNN export, §3.3).

### 1.4 Multi-frame voting
On capture, grab N frames (e.g. 5), infer each, and **majority-vote per tube**. Kills
per-frame flicker and borderline-bubble misreads.
- **Cost:** small. **Tradeoff:** +0.5–1 s per capture. High robustness, low effort.

---

## Tier 2 — Model & data (raises the ceiling)

### 2.1 Retrain on rig-specific data
A model trained on images from *this exact camera/lighting/distance* dramatically
outperforms a generic one. Use the Tier-0 dataset; ensure enough **positive/bubble**
examples (class balance); augment for *real* variation only.
- **Tradeoff:** needs labeled data + a training cycle. Highest ceiling-raiser.

### 2.2 Consider a bigger model or a two-stage approach (on the capture path)
Nano → **small/medium** for `/predict` only; or split **locate → per-tube classify**
(a small classifier on a clean, aligned crop is more accurate and easier to train than
one-shot detection).
- **Tradeoff:** more latency/compute on capture (acceptable; not on the stream).

### 2.3 Active-learning loop
Every prediction is already persisted. Flag low-confidence and count-≠-9 cases, label
them, fold back into training — the system improves on the hard cases it actually sees.
- **Tradeoff:** ongoing process, but compounding.

---

## Tier 3 — Classical CV cross-check (cheap insurance)
Under controlled lighting, **HSV color thresholding** ("is this tube yellow?") is very
robust, and **blob/Hough-circle** bubble detection is straightforward on a clean crop.
Use as a sanity cross-check against the model (disagreement → flag for review), or a
fallback.
- **Tradeoff:** another path to maintain; sensitive to lighting (which Tier 0 fixes).

---

## 4. Model upgrade evaluation: YOLO26

**Current model:** a custom-trained YOLOv8n (`best.pt`) — see
[MODEL_AND_DATA.md](MODEL_AND_DATA.md). Loaded as PyTorch via `YOLO("best.pt")`
([inference.py:18](../app/inference.py#L18)).

### 4.1 What YOLO26 is
Ultralytics' 2026 release, **edge-first** by design (n/s/m/l/x variants). Key changes
vs YOLO11/YOLOv8:
- **End-to-end, NMS-free** — predictions come out directly with **no Non-Maximum
  Suppression post-processing**, lowering latency and latency *variability*.
- **DFL (Distribution Focal Loss) removed** — drops softmax-heavy ops that low-power
  accelerators handle poorly; helps quantization. Cited as up to **43% faster CPU
  inference** without accuracy loss.
- New optimizer (MuSGD) and small-object loss tweaks (ProgLoss + STAL).

### 4.2 Benchmark numbers (COCO — official Ultralytics)
| Metric | YOLO26n | YOLO11n | YOLO26s | YOLO11s |
|---|---|---|---|---|
| mAP@50-95 | **40.9** | 39.5 | **48.6** | 47.0 |
| CPU ONNX (ms) | **38.9** | 56.1 | **87.2** | 90.0 |
| Params (M) | 2.4 | 2.6 | 9.5 | 9.4 |
| FLOPs (B) | 5.4 | 6.5 | 20.7 | 21.5 |

Nano: ~**+1.4 mAP** and ~**31% faster** CPU than YOLO11n, at fewer params/FLOPs.

### 4.3 Raspberry Pi 5, YOLO26n @ 640, by export format
| Format | Inference time | Note |
|---|---|---|
| **NCNN** | **67.7 ms** | Fastest; ARM-optimized — recommended |
| OpenVINO | 70.7 ms | |
| ONNX | 130.3 ms | |
| **PyTorch (`.pt`)** | **302.2 ms** | **What VialVision uses today** |

> **The single biggest speed finding has nothing to do with the model version:**
> exporting to **NCNN** is ~**4.5× faster** than running the raw `.pt` on a Pi. That
> alone frees enough latency budget to run full resolution and multi-frame voting
> (§1.3–1.4) — i.e. **trade reclaimed speed for accuracy**.

For a full board-by-board comparison (Pi 4/5, Pi 5 + Hailo AI HAT+, Coral, Jetson
Orin Nano) and the hardware-spend recommendation, see [HARDWARE.md](HARDWARE.md).

### 4.4 Honest verdict for *this* project
- ✅ **Worth adopting**, primarily for **speed/edge efficiency** and the simpler
  NMS-free pipeline.
- ⚠️ **Not a fix for the client's accuracy complaint on its own.** The +1.4 mAP is a
  **COCO** delta on a generic 80-class task; it does **not** transfer 1:1 to our
  2-class bubble/no-bubble problem. Real accuracy here is set by **our training data,
  lighting, and capture** — Tiers 0–2 — not by the architecture's COCO score.
- 🔁 **Benefit requires retraining.** You cannot drop YOLO26 in over `best.pt`; you
  must **retrain a YOLO26n checkpoint on our dataset** (which is why Tier 0.1 comes
  first). Without rig data, switching architectures changes nothing for us.
- ⚠️ **NMS-free interacts with our custom dedup.** YOLO26 outputs final boxes with no
  NMS, so the YOLO-level `iou=0.6, agnostic_nms=True` args
  ([inference.py:155](../app/inference.py#L155)) become moot. Our
  `suppress_duplicate_tubes()` + hard-cap-9 still has value (domain x-distance merge,
  the 9-tube guarantee), but should be **re-tuned/validated** against YOLO26 output —
  an NMS-free model may already emit ≤ 9 clean boxes, making aggressive dedup
  unnecessary (and our over-merge risk avoidable).

### 4.5 Recommended migration path

> **Decision (2026-06-29):** the team is proceeding with **YOLO26 object detection**
> (keeping the detection architecture, not the fixed-ROI classification alternative),
> retrained on the existing Roboflow dataset and deployed via NCNN on a Pi 5. This
> document remains the background/rationale; the committed, sequenced build plan is in
> [NEXT_STEPS.md](NEXT_STEPS.md), with the label/preprocessing/augmentation policy in
> [LABELING_STRATEGY.md](LABELING_STRATEGY.md).

1. Finish **Tier 0.1** (labeled eval set) — required to benchmark anything.
2. **Quick win, do now regardless of version:** export the *current* `best.pt` to
   **NCNN** and benchmark accuracy + latency on the eval set. If accuracy holds, ship
   it — ~4× speed for near-zero risk.
3. **Retrain YOLO26n** on the rig dataset; compare against the current model on the
   eval set (count accuracy, per-tube accuracy, MPN-pattern accuracy, Pi latency).
4. If YOLO26n wins (likely on speed, maybe on accuracy), **deploy via NCNN export** and
   **re-tune** confidence + the dedup thresholds for the new model.
5. Optionally evaluate **YOLO26s** on the capture-only path for extra accuracy headroom
   (NCNN keeps it affordable on the Pi).

---

## 5. Priority summary (what to actually do)

| Order | Action | Effort | Accuracy impact | Speed impact | Risk |
|---|---|---|---|---|---|
| 1 | Labeled eval set (0.1) | Low | Enables all | — | None |
| 2 | Controlled lighting (0.2) | Low ($) | **High** | — | Low |
| 3 | Lock focus/exposure/WB (0.3) | Low | **High** | — | Low |
| 4 | NCNN export of current model (4.5 §2) | Low | None | **~4×** | Low |
| 5 | Full-res + multi-frame on capture (1.3–1.4) | Med | High | −(offset by NCNN) | Low |
| 6 | Fixed-ROI fixture (1.1) | Med-High | **High** | + | Med |
| 7 | Retrain on rig data (2.1) | High | **High** | — | Med |
| 8 | Adopt YOLO26 (retrained) + re-tune dedup (4) | High | Med | High | Med |
| 9 | Classical-CV cross-check (Tier 3) | Med | Med (safety) | — | Low |

**The instinct to "upgrade the AI model" is item 8, not item 1.** If the input is
inconsistent, a new architecture just learns to cope with variance you could have
removed for $30. Clean, consistent, measurable input first; then the model.

---

## How to validate any change

Run it against the Tier-0 eval set and report:
- **Count accuracy** — % of images where exactly 9 tubes are detected.
- **Per-tube accuracy** — % of tubes classified correctly.
- **MPN-pattern accuracy** — % where the final `P{x}{y}{z}` matches ground truth (the
  number that actually matters to the client).
- **Pi latency** — median inference time on-device, per export format.

See [TESTING.md](TESTING.md) for where an automated harness would live.

---

## Sources

- [Ultralytics — YOLO26 product page](https://www.ultralytics.com/yolo/yolo26)
- [YOLO26 vs YOLO11 comparison (benchmarks, architecture)](https://docs.ultralytics.com/compare/yolo26-vs-yolo11)
- [YOLO26 on Raspberry Pi: setup & benchmarks (export-format timings)](https://docs.ultralytics.com/guides/raspberry-pi)
- [Object detection with Ultralytics YOLO26 on Raspberry Pi (Raspberry Pi official)](https://www.raspberrypi.com/news/object-detection-with-ultralytics-yolo26-on-raspberry-pi/)
- [YOLO26 on Raspberry Pi 5: real-world performance (Medium)](https://medium.com/@aiedge.ai/yolo26-on-raspberry-pi-5-real-world-performance-quick-wins-why-its-worth-it-in-2026-75e267b8d59b)

_Benchmark figures above are Ultralytics' official COCO / Raspberry Pi 5 numbers and
are indicative; validate on our own eval set and hardware before deciding._

---

## Real-world domain shift (deployed model fails on uncontrolled photos) — 2026-08-08

**Symptom:** after deployment, the model failed on a casual phone photo (dim room, blue
keyboard-RGB colour cast, unfamiliar white stand) — it found only 1–3 *clustered* boxes,
not 9, and mislabelled colours.

**Root cause: domain shift — not a saturation-only issue.** The model was trained on a
narrow, specific rig (bright, even light; foam background). Changing lighting + white
balance + background + camera all at once makes **both localisation and classification**
break. The model generalises only to conditions close to its training data.

**Two deployment targets, two answers:**
- **Controlled appliance (Pi + fixed jig) — primary, reliable:** control the environment
  with a **light box / diffuser** (kills colour casts), a fixed background + distance, and
  **retrain on data captured through that exact rig** so *training conditions == deployment
  conditions*. (**Track 3** — environment/dataset owned by the user.)
- **Wild phones (web/VPS) — much harder:** needs a **large, diverse dataset** (many
  lightings, backgrounds, phones — including messy ones) to generalise. A big data effort;
  set expectations that it works best in decent light until that exists.

**Tension to navigate:** we deliberately avoided hue/saturation augmentation to keep
yellow-vs-purple crisp — which is exactly what makes the model brittle to colour casts. For
the wild case, carefully reintroduce some white-balance/colour robustness (or normalise WB
in preprocessing) **without** destroying the colour discrimination.

> Note: **NCNN vs PyTorch is unrelated** to this — the backend only affects *speed*, not
> detection quality. See [STREAM_PERFORMANCE.md](STREAM_PERFORMANCE.md).

---

## Lens distortion + edge tubes blending into the white rig — 2026-08-11

**Symptom:** on a phone capture of a full 9-tube rack, the model detected only **7 tubes**
— the **leftmost and rightmost** tubes were missed. In person there is a clear gap between
each tube and the rig wall; on camera the two end tubes appeared merged with the white rig.

**Root cause — three effects that all peak at the frame edges:**
1. **Barrel / "fisheye" lens distortion.** Phone cameras (especially the wide / ultra-wide
   lens, held close) bend the image radially — **near-zero distortion in the centre, worst
   at the left/right edges.** The two end tubes are exactly where the warp is strongest.
2. **Off-axis / angled view.** The camera is not perpendicular, so the end tubes are
   **foreshortened** and partly occluded by the rig walls.
3. **Low contrast (clear tube on white rig).** A pale, semi-transparent tube against a
   **white** rig has almost no edge signal — and once (1) and (2) flatten and compress it,
   the detector has nothing left to latch onto. The training images had a darker background,
   so this white-on-clear case is a worst case for contrast.

They **stack at the edges**, which is why the *centre* seven tubes are found and the *two
ends* are lost.

**Fixes, by leverage (and by which deployment target — see the two use cases below):**

| Fix | What it does | Best for |
|---|---|---|
| **Perpendicular + centred + backed-off camera** (fixed jig) | Puts all 9 tubes in the low-distortion centre zone; removes foreshortening | Pi appliance |
| **Dark, matte, contrasting backdrop** behind the tubes | End tubes stop blending into white — cheap, high impact | Pi appliance |
| **Even lighting** (light box / diffuser) | End tubes aren't washed out or shadowed | Pi appliance |
| **Lens undistortion** (OpenCV calibration → `undistort`) | Straightens barrel distortion before inference; per-camera calibration | Phones / wide lenses |
| **Retrain on rig data incl. edge tubes** | Model learns this exact geometry + contrast | Both |
| **Fixed-ROI classification** (know the 9 positions → crop → classify) | Makes "can't *detect* an edge tube" structurally impossible | Pi appliance |

**Structural fix — fixed-ROI.** This is the third time real-world variance (dim room,
colour cast, now edge-blend) has broken *detection*. When the rack sits in a repeatable
jig, we already know where all 9 tubes are, so we **crop the 9 known positions and classify
each** instead of asking the detector to *find* them. An edge tube that blends into white is
impossible to *detect* but trivial to *classify*. See
[FIXED_ROI_DESIGN.md](FIXED_ROI_DESIGN.md).

---

## The two deployment use cases (they are genuinely different products)

VialVision ships to **two targets with different physics** — the accuracy strategy must
branch on which one you are building for. Do not expect one model/config to serve both
equally.

### 1. Controlled appliance — Raspberry Pi 5 + fixed jig (primary, reliable)

- **Environment is controlled by us:** fixed camera mount (perpendicular, centred, backed
  off), fixed rack position, controlled lighting (light box / diffuser), dark contrasting
  backdrop, locked focus / exposure / white balance.
- **Because the rack is in a repeatable position, we can use [fixed-ROI](FIXED_ROI_DESIGN.md)**
  — crop the 9 known tube positions and classify each. This removes the whole "missing edge
  tube" class of failures and is the recommended path for a dependable product.
- **Retrain on data captured *through this exact rig*** so training conditions ==
  deployment conditions.
- **Target:** high, repeatable accuracy. This is the one to guarantee.

### 2. Wild phones — web app on the VPS (best-effort)

- **Environment is uncontrolled:** any phone, any lens (incl. ultra-wide barrel
  distortion), any lighting, any background, handheld angle. The 7/9 edge-blend failure
  above is this case.
- **No fixed jig → no fixed-ROI.** Detection must genuinely *find* the tubes, so this path
  depends on a **large, diverse dataset** (many phones / lightings / backgrounds, including
  messy ones) plus optional **per-phone lens undistortion** and **white-balance
  normalisation** in preprocessing.
- **Target:** best-effort. Set client expectations: reliable in decent light and a roughly
  straight-on framing; degrades with extreme wide-angle, glare, or clutter.

> **Design consequence:** the app already exposes an **inference mode** (Live vs Aim &
> Capture) and a **model backend** badge. The jig path will additionally gain a **fixed-ROI
> mode** (calibrate once, then classify fixed crops); the phone path stays on full-frame
> detection. See [FIXED_ROI_DESIGN.md](FIXED_ROI_DESIGN.md) and
> [STREAM_PERFORMANCE.md](STREAM_PERFORMANCE.md).
