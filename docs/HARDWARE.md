# Hardware Recommendation

_Purpose: which hardware to run VialVision on for the best **accuracy + speed**,
with benchmarks. Companion to [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) and
[DEPLOYMENT.md](DEPLOYMENT.md)._

> Benchmark figures here are indicative (vendor / community numbers for YOLOv8n/s at
> 640). Validate on your own eval set and hardware before buying — see
> [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) §"How to validate".

---

## TL;DR

- **Recommended:** **Raspberry Pi 5 (8 GB)** with the model exported to **NCNN**.
  Cheap, keeps the entire existing software stack, and is ~5× faster than this
  on-demand workload needs.
- **A faster chip will not fix the accuracy complaint.** This reads *one rack on
  demand*, not a real-time video feed — compute is not the bottleneck. **Spend the
  budget on camera + lighting + a fixture instead.**
- **Don't buy a Jetson for this** (and never the 2019 "Jetson Nano" — it's
  end-of-life). Jetson only makes sense if the product pivots to real-time,
  multi-camera video analytics, and it forces a camera-stack rewrite.

---

## 1. The workload reality check

VialVision runs inference **once per reading**, when a person clicks "analyze" (plus a
few extra frames if multi-frame voting is added). It is **not** a continuous,
high-FPS, multi-stream pipeline. A result in **1–3 seconds is perfectly acceptable**.

Consequences:
- "100+ FPS" on a Jetson is horsepower you will **never use** here.
- Inference *speed* is already solvable in software (NCNN export, §3) with **no
  hardware change**.
- Inference *accuracy* is gated by **camera, lighting, and training data**
  ([ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md)), **not** by TOPS.

Read the rest of this doc with that framing: we are choosing the cheapest compute that
comfortably covers an on-demand single-inference workload, then redirecting money to
the things that actually move accuracy.

---

## 2. Benchmarks (YOLOv8n/s @ 640, indicative)

| Platform | Inference (YOLOv8n) | ~FPS | Power | Approx. cost | Notes |
|---|---|---|---|---|---|
| **Pi 4 (current, CPU, `.pt`)** | ~500–700 ms | ~2 | ~5 W | (in hand) | Slowest path; raw PyTorch |
| **Pi 5 (CPU, `.pt`)** | ~302 ms | ~3 | ~7 W | ~$80 | Unoptimized format |
| **Pi 5 (CPU, NCNN)** | **~68 ms** | **~15** | ~7 W | ~$80 | **~4.5× free speedup, no extra HW** |
| **Pi 5 + AI HAT+ (Hailo-8L, 13 TOPS)** | ~8–12 ms (YOLOv8s ~80 FPS) | 80–120 | ~10 W | +~$70 | Needs Hailo compile; great for video |
| **Coral Edge TPU (4 TOPS)** | ~15–30 ms* | ~30–50* | ~6 W | +~$60 | **Avoid** — stale SW, Python/compat issues |
| **Jetson Orin Nano (TensorRT, INT8)** | **~23 ms** | ~43–100+ | 7–9 W | ~$200–250 | Fastest, but different camera/SW stack |

\* Coral numbers are unreliable in practice; one documented Pi 5 + Coral demo managed
only 1–2 FPS due to compatibility problems. Coral hasn't been meaningfully updated and
breaks with current Python/Ultralytics — not recommended.

**Reading the table for *this* project:** everything from "Pi 5 + NCNN" down is
*overkill* for an on-demand single read. The relevant comparison is **Pi 4 `.pt`
(~2 FPS) → Pi 5 NCNN (~15 FPS)** — and that jump is mostly the *NCNN export*, not the
board.

---

## 3. The free speed win (independent of hardware)

The model currently runs as a raw PyTorch `.pt`
([inference.py:18](../app/inference.py#L18)), the **slowest** format on ARM. Exporting
to **NCNN** gives ~4.5× speedup on a Pi at near-zero risk:

- Pi 5: ~302 ms (`.pt`) → ~68 ms (NCNN).
- Do this **before** considering any hardware change; it may make the current Pi 4
  fast enough on its own.

See [MODEL_AND_DATA.md](MODEL_AND_DATA.md) and
[ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) §4.

---

## 4. Two clarifications that change the decision

**"Jetson Nano" — which one?** The original **Jetson Nano (2019, Maxwell)** is
**end-of-life**: stuck on ancient JetPack/CUDA, painful-to-impossible with modern
Ultralytics / YOLO26. Do **not** buy it. The current equivalent is the **Jetson Orin
Nano** (~$200–250), which is genuinely fast.

**Jetson means rewriting the camera layer.** Jetson uses CSI cameras via
Argus/GStreamer, **not `picamera2`**. Moving to Jetson would require re-doing the
entire [camera.py](../app/camera.py) backend, the autostart/kiosk scripts, and the
Pi-specific color/focus fixes ([CAMERA.md](CAMERA.md)). That is a real,
project-specific migration cost — not just swapping a board.

---

## 5. Recommendation (tiered)

### → Recommended: Raspberry Pi 5 (8 GB) + NCNN export
- ~15 FPS — **5× more than an on-demand single-rack read needs**.
- Keeps the **entire** existing stack: picamera2, color/focus fixes, kiosk autostart,
  HTTPS. **Zero rewrite.**
- ~$80. Resolves the *speed* side completely.

### → Headroom (only if you later want continuous live detection or a heavier model)
- Add the **Raspberry Pi AI HAT+ (Hailo-8L, 13 TOPS)**, ~$70. Runs YOLO26s/m at video
  rates. Overkill for on-demand reads, but the *right* upgrade path — it stays in the
  Pi ecosystem (no camera rewrite).

### → Don't
- **Jetson** for this workload — only justified by a pivot to real-time, multi-camera
  analytics. Never the **2019 Jetson Nano** (EOL).
- **Coral Edge TPU** — stale software, compatibility pain.

---

## 6. Where the budget should actually go

Compute is solved cheaply, so redirect spend to the **accuracy levers**
([ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) Tier 0–1):

| Spend | ~Cost | Why it beats a faster SoC |
|---|---|---|
| **Controlled lighting** (LED ring / light box / diffuser; back-light for bubbles) | $20–50 | Biggest real-world accuracy gain — color & bubble detection live or die on lighting |
| **Better camera** (Camera Module 3 autofocus, or HQ Camera + lens) | $25–70 | Sharper, higher-detail tubes; lockable focus at the ~19 cm distance |
| **Mechanical jig** to fix rack position | ~$10 (3D print) | Enables fixed-ROI detection — eliminates the wrong-count failure mode |

---

## 7. Bottom line

**Pi 5 (8 GB) + Camera Module 3 + a lighting box + a fixture ≈ $150 total** will
outperform a **$250 Jetson Orin Nano running the current camera and lighting** on
*your* accuracy metric — because the errors come from inconsistent input, not a slow
chip. Buy compute for the workload you have (on-demand, single inference), and spend
the rest on input quality.

---

## Sources

- [YOLO26 on Raspberry Pi: setup & benchmarks (export-format timings)](https://docs.ultralytics.com/guides/raspberry-pi)
- [Raspberry Pi 5 vs Jetson Orin Nano: Edge AI 2026](https://www.kunalganglani.com/blog/raspberry-pi-5-vs-jetson-orin-nano-edge-ai)
- [Benchmark RPi5 running YOLOv8s with Hailo-8L (Raspberry Pi forums)](https://forums.raspberrypi.com/viewtopic.php?t=373867)
- [NPU vs TPU: Raspberry Pi 5 with Hailo vs Coral](https://rasimmax.com/blog/npu-vs-tpu-raspberry-pi-5-hailo-coral-2025-guide)
- [Performance analysis of YOLO models on edge (arXiv)](https://arxiv.org/pdf/2502.15737)
- [Jetson Nano vs Raspberry Pi 5 + Hailo (Ultralytics community discussion)](https://github.com/orgs/ultralytics/discussions/17741)
