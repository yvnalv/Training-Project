# Stream Performance — Optimization Options (Future Work)

Live **video stream** inference is slow on the small VPS. This document records
*why*, and three optimization options. Single-photo `/predict` is unaffected — this
is specifically about the real-time WebSocket stream.

> **Status:** Option A (NCNN) and Option B (throttling) are **implemented**
> (branch `stream-perf-ncnn-throttling`, 2026-08-07 — see `../CHANGELOG.md`).
> Option C (client-side inference) remains **future work**.

## The bottleneck (why it's slow)

The production VPS is a **DigitalOcean $6/mo Basic droplet: 1 shared vCPU, 1 GB
RAM, no GPU**, shared with nginx, postgres, and other apps. Every streamed frame
runs full YOLO inference **on the VPS CPU** — in *both* stream modes:

| Mode | Camera source | Where inference runs |
|---|---|---|
| **Server mode** | The server's own camera (Pi cam / OpenCV) — [`../app/api.py`](../app/api.py) `websocket_endpoint`, server-mode branch | **VPS CPU** |
| **Client mode** | The browser/phone camera; frames sent as bytes over the WebSocket | **VPS CPU** |

> **Important:** "client mode" means only that the *camera* is on the client. The
> **model still runs on the server** in client mode — it does **not** offload
> inference. See [`../app/api.py`](../app/api.py) (`if "bytes" in data:` branch).

Current flow (both modes):

```
frame → JPEG encode → run_inference_with_count (YOLO on VPS CPU) → annotate → send image+results over WS
```

There is **no frame-skipping**, so on a slow CPU a backlog builds and displayed
latency grows unbounded. Confirm the bottleneck on the VPS while streaming:

```bash
free -h                  # Swap "used" > 0  → RAM-bound (bigger droplet helps)
docker stats --no-stream # vialvision-app CPU ~100% → CPU-bound (droplet size won't help much)
```

A $12 droplet doubles RAM but keeps **1 vCPU**, so it fixes swapping but not the
CPU ceiling. For faster streaming you need fewer frames (B), faster inference (A),
more vCPU, or client-side inference (C).

---

## Option A — Export the model to NCNN (server-side) — ✅ implemented

NCNN is a CPU-optimized inference runtime; it is typically **2–4× faster** than raw
PyTorch on CPU for the same model. The pipeline already **auto-detects** an NCNN
model — see [`../app/inference.py`](../app/inference.py) `_resolve_model_path()`:
it uses `models/best_ncnn_model/` when the `ncnn` runtime is importable, otherwise
falls back to `models/vialvision_yolo26.pt`.

**Done:** `models/best_ncnn_model/` is committed (now baked into the image), `ncnn` is
in `requirements.txt`, and [`../app/inference.py`](../app/inference.py) loads with
explicit `task="detect"`. Verified locally: NCNN auto-selected, inference ~118 ms/frame.

**How it was done (reproduce when the model is retrained):**
1. Export once (locally):
   ```bash
   yolo export model=models/vialvision_yolo26.pt format=ncnn
   ```
   This produces `models/vialvision_yolo26_ncnn_model/`.
2. **Rename** it to match the code's expected path:
   ```
   models/vialvision_yolo26_ncnn_model/  →  models/best_ncnn_model/
   ```
3. Add the runtime to [`../requirements.txt`](../requirements.txt): `ncnn`.
4. Commit the exported folder (like `vialvision_yolo26.pt` is already committed).

**Code changes:** none to the inference pipeline — detection is automatic.

**CI/CD & VPS:** no manual VPS installation. The exported model is **baked into the
Docker image** (exactly like the `.pt` today) and `ncnn` is pip-installed into that
image. It ships through the existing GHCR build → SSH `pull && up -d` pipeline. The
VPS needs nothing new. (Export is done once locally and committed; an in-CI export
step is possible but adds build time — committing the artifact is simpler.)

**Effect:** ~2–4× faster per-frame inference on the VPS CPU. Model still runs on
the VPS.

---

## Option B — Frame throttling — ✅ implemented

**What it does:** Previously every frame ran full inference with no skipping. When the
CPU can't keep up, frames queue and the displayed result drifts seconds behind
reality — the stream feels laggy. Throttling caps the processing rate (process only
the **latest** frame / drop stale frames / cap to N FPS) so latency stays
**bounded**. It does not make each inference faster — it keeps the stream
responsive (lower but honest FPS) instead of an ever-growing backlog.

**How it was done:**
- **Server** — [`../app/api.py`](../app/api.py) `websocket_endpoint`: a per-session
  monotonic `last_infer` timestamp caps inference to `VIALVISION_STREAM_MAX_FPS`
  (default 10). Both branches drop frames arriving within the min interval —
  server-mode grabs the latest camera frame; client-mode drops the incoming bytes.
- **Client** — [`../static/js/script.js`](../static/js/script.js): an in-flight guard
  (`_frameInFlight`) sends the next frame only after the previous result arrives, so
  the browser can't flood a slow server. Self-heals after `STALL_MS` (4 s) if a
  result is ever dropped.

**UI-tunable (no redeploy):** the existing **Max FPS** slider now governs *both*
modes. Changing it sends a `set_fps` control message that sets the server-side
per-session cap (`session_min_interval`) as well as the client capture rate — so on
hardware whose throughput is unknown (e.g. **Raspberry Pi 5** server-camera mode) you
can just drag the slider until the stream is smooth. `VIALVISION_STREAM_MAX_FPS`
(env, default 10) is only the **startup default** used until the client sends a value;
`<=0` (env or slider path) disables the cap.

**Effect:** lower, bounded latency; smoother perceived stream. Pairs with A.

---

## Option C — Client-side (in-browser) inference (large change, future)

Move inference off the VPS entirely: run the model **in the browser**. This is an
architectural shift from thin-client to fat-client and is **not** implemented today.

**Plan:**
1. **Export to a web format** — ONNX (`yolo export ... format=onnx`) run via
   `onnxruntime-web` (WASM / WebGPU), or TensorFlow.js. Serve the weights as a
   static asset (a few MB, downloaded once, cacheable).
2. **Port post-processing to JavaScript** — `suppress_duplicate_tubes`,
   `detections_to_tubes`, `tubes_to_xyz` (see
   [`../app/inference.py`](../app/inference.py)) plus YOLO output-tensor decoding,
   currently Python.
3. **Render in-browser** — draw boxes on a canvas overlay instead of the server
   annotating a JPEG.
4. **Keep MPN lookup + history on the server** — the browser POSTs the final
   9-tube pattern to a lightweight endpoint to compute MPN and persist history
   ([`../app/mpn/mpn_lookup.py`](../app/mpn/mpn_lookup.py),
   [`../app/db/queries.py`](../app/db/queries.py)). MPN lookup is tiny and not a
   bottleneck, so the CSV need not be ported.

**Trade-offs:**
- **Pro:** VPS does zero stream inference → scales per-device, lowest latency,
  cheapest hosting.
- **Con:** two implementations of post-processing to maintain; performance depends
  on the client device (varies widely on phones); model download size; more
  frontend complexity.

**Effort:** substantial — new model export, a JS inference layer, canvas rendering,
and porting the decode/dedup logic.

---

## Recommended sequence

1. **A + B first** — small, keep the current architecture, and together give the
   biggest real-world win on the $6 droplet (faster inference + bounded latency).
2. **Re-measure** (`free -h`, `docker stats`). If still CPU-bound and smoother
   streaming is required, either move to a **2 vCPU** droplet or pursue **C**.
3. **C** is the proper answer for scale, but it's a genuine rewrite — schedule it
   only if per-device/real-time streaming becomes a hard requirement.
