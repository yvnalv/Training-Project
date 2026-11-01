# Camera

> _This document occupies the template slot originally named `MULTI_TENANCY`.
> VialVision is a single-device tool with no tenancy concept; the genuinely
> device-specific subsystem worth documenting here is the camera abstraction._

The `Camera` class (`app/camera.py`) provides one capture interface over two
backends, used by both `GET /capture` (single still) and the `/ws` server-mode stream.

## Backends

| Priority | Backend | When |
|---|---|---|
| 1 | **picamera2** | Raspberry Pi camera module (native, low latency, autofocus/ISP controls) |
| 2 | **OpenCV** | USB webcams / any platform (fallback) |

`picamera2` is imported lazily (`importlib`); if it isn't available, `Picamera2` is
`None` and `start()` goes straight to the OpenCV path (logging a warning on Linux).
The presence of `picamera2` also drives the platform-aware default camera mode
(`_platform_info()` in the API).

> **Important (Raspberry Pi virtualenv):** `python3-picamera2` is an apt system
> package. Always create the Raspberry Pi virtual environment with
> `python3 -m venv --system-site-packages <venv>` so `picamera2` and `libcamera` are
> accessible inside the venv.

## Lifecycle

```
start(source=0, width=640, height=480, focus_mode="continuous", lens_position=5.2)
   ├─ if source in (0,"0","pi","picam") and picamera2 available → try Pi backend
   │     ├─ select full-FoV sensor mode (e.g. 2304×1296 binned on IMX708)
   │     ├─ apply ScalerCrop + Sharpness
   │     ├─ configure focus (Continuous AF w/ Full range + Fast speed, or Manual LensPosition)
   │     ├─ run initial autofocus_cycle() lock before starting capture thread
   │     └─ on failure, fall back to OpenCV
   └─ else / fallback → OpenCV (tries multiple sources + platform backends)
        │
   background thread runs _capture_loop()  ──►  _latest_frame (lock-protected)
        │
get_frame()  ── thread-safe read of the latest BGR frame
        │
stop()  ── signal thread, join (2 s), release backend, clear frame
```

- Capture runs on a **daemon background thread**; `get_frame()` returns the most
  recent frame. A `Lock` (`_frame_lock`) guards reads/writes so a consumer never sees
  a half-written array, while `_picam_lock` serializes `capture_image()` and
  `autofocus_cycle()`.
- `stop()` **joins** the thread (2 s timeout) before releasing the device, avoiding a
  race where the loop is still reading while the capture is released.

## Frame format: everything is BGR internally

The in-memory frame buffer is always **BGR** (OpenCV convention):

- **picamera2 path:** request `RGB888`, capture with `capture_image("main")` (returns
  a PIL Image in guaranteed RGB; `.convert("RGB")` guards rare RGBA), then convert
  **RGB→BGR** with `cv2.cvtColor`.
- **OpenCV path:** `cap.read()` already returns BGR.

> **Why RGB888 (not BGR888)?** On some Pi hardware/libcamera versions `BGR888`
> delivers bytes in RGB order despite its name, causing blue/red swaps. `RGB888` +
> `capture_image()` is reliable across all camera modules. JPEG encoding of stills is
> done with **PIL** (not `cv2.imencode`) to avoid ARM libjpeg channel-order quirks.
> See [../CHANGELOG.md](../CHANGELOG.md) entry _2026-04-19 — Pi camera color fix_.

## Pi-specific controls (applied in `start()`)

| Control | Value | Purpose |
|---|---|---|
| `sensor.output_size` | Full-FoV binned mode (e.g. `2304×1296` on IMX708) | Prevents `libcamera` from picking a center-cropped sensor mode (`1536×864`) that restricts field-of-view and PDAF phase pixels |
| `ScalerCrop` | full `PixelArraySize` | Widest field of view (zoom out) — fixes "too zoomed in" at close range |
| `Sharpness` | `2.5` (default 1.0) | Crisp close-distance detail without over-sharpening halos |
| `AfMode` | `2` (Continuous) or `0` (Manual) | Camera Module 3 (IMX708) autofocus or locked manual focus (`LensPosition` in dioptres); logged and skipped on fixed-focus modules (CM1/CM2/HQ) |
| `AfRange` | `2` (`Full`) | Searches both close macro (~5–10 cm) and normal range |
| `AfSpeed` | `1` (`Fast`) | Faster focus lock when placing the rack in front of the camera |

Users can switch between **Continuous Autofocus (Macro + Full Range)** and **Manual
Focus (Fixed Distance / Jig)** in **Settings → Camera & Focus** (or click **Refocus**
in the Stream header). Manual focus sets `LensPosition` in dioptres ($\frac{1}{\text{meters}}$,
default `5.2` dpt $\approx 19\text{ cm}$), which prevents autofocus from hunting through
clear glass tubes onto the background.

## Flips

`_pi_hflip` and `_pi_vflip` (both default `True`) control `cv2.flip` in the Pi
capture loop (`-1` = both, `1` = horizontal, `0` = vertical). Flip preferences also
exist as a frontend setting (`flipHorizontal`). See
[../CHANGELOG.md](../CHANGELOG.md) entries on flip and RGB fixes.

## OpenCV source/backend probing

`_open_opencv_capture()` tries multiple candidates so a webcam is found without
manual configuration:
- **Sources:** the requested source, and if it's `0`, also `0,1,2,3`.
- **Backends:** Windows → `CAP_MSMF, CAP_DSHOW, CAP_ANY`; Linux → `CAP_V4L2,
  CAP_ANY`; else `CAP_ANY`.

For each combination it opens, sets resolution, and verifies with a test `read()`
before accepting. If nothing opens, `start()` raises a `RuntimeError` with a
platform-specific hint (e.g. "another app may be using the webcam" on Windows, or
"install python3-picamera2" on Linux). See [ERROR_HANDLING.md](ERROR_HANDLING.md).

## Stabilization & resolution on still capture

`GET /capture` opens the camera at **at least `1280×720`** (or `1920×1080` if selected
in Settings), waits for exposure and white balance to settle, triggers an explicit
`autofocus_cycle()` lock (when in autofocus mode), and encodes the frame at full
resolution. `POST /predict` defaults to `full=True` (`scale_factor=1.0`) so single
captures and uploads are never downscaled to `320×240`.
