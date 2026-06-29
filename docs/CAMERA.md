# Camera

> _This document occupies the template slot originally named `MULTI_TENANCY`.
> VialVision is a single-device tool with no tenancy concept; the genuinely
> device-specific subsystem worth documenting here is the camera abstraction._

The `Camera` class (`app/camera.py`) provides one capture interface over two
backends, used by both `GET /capture` (single still) and the `/ws` server-mode stream.

## Backends

| Priority | Backend | When |
|---|---|---|
| 1 | **picamera2** | Raspberry Pi camera module (native, low latency) |
| 2 | **OpenCV** | USB webcams / any platform (fallback) |

`picamera2` is imported lazily (`importlib`); if it isn't available, `Picamera2` is
`None` and `start()` goes straight to the OpenCV path. The presence of `picamera2`
also drives the platform-aware default camera mode (`_platform_info()` in the API).

## Lifecycle

```
start(source=0, width=640, height=480)
   ├─ if source in (0,"0","pi","picam") and picamera2 available → try Pi backend
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
  recent frame. A `Lock` guards reads/writes so a consumer never sees a half-written
  array.
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

## Pi-specific controls (applied after `start()`)

| Control | Value | Purpose |
|---|---|---|
| `ScalerCrop` | full `PixelArraySize` | Widest field of view (zoom out) — fixes "too zoomed in" at close range |
| `Sharpness` | `4.0` (default 1.0) | Compensate for close-distance softness |
| `AfMode` | `2` (continuous AF) | Camera Module 3 autofocus; silently ignored on CM1/CM2 (fixed focus) |

Each is wrapped in try/except so an unsupported control on a given module never
breaks startup.

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

## Stabilization on capture

`GET /capture` polls up to ~3 s for the first frame, then waits **2 s** before
encoding so exposure, white balance, and autofocus can settle — important for the
Pi camera at close range.
