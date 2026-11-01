import logging
import time
import importlib
import sys
from threading import Thread, Lock

import cv2
import numpy as np

try:
    Picamera2 = importlib.import_module("picamera2").Picamera2
    _PICAM_IMPORT_ERROR = None
except Exception as _e:
    Picamera2 = None
    _PICAM_IMPORT_ERROR = _e

logger = logging.getLogger(__name__)

# libcamera numeric control constants (avoid hard dependency on libcamera.controls enum)
_AF_MODE_MANUAL = 0
_AF_MODE_AUTO = 1
_AF_MODE_CONTINUOUS = 2

_AF_RANGE_NORMAL = 0
_AF_RANGE_MACRO = 1
_AF_RANGE_FULL = 2

_AF_SPEED_NORMAL = 0
_AF_SPEED_FAST = 1

_AF_TRIGGER_START = 0


class Camera:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self._latest_frame = None
        self._frame_lock = Lock()      # FIX: protects latest_frame across threads
        self._picam_lock = Lock()      # serialises capture_image() and autofocus_cycle()
        self._thread = None
        self._backend = None
        self._picam = None
        self._picam_frame_is_rgb = False
        self._pi_hflip = True
        self._pi_vflip = True
        self._focus_mode = "continuous"
        self._lens_position = 5.2      # dioptres (~19 cm default rack distance; 1 / 0.19m)
        self._supports_af = False
        self._camera_model = None

    def _open_opencv_capture(self, source, width, height):
        numeric_source = source
        if isinstance(source, str) and source.isdigit():
            numeric_source = int(source)

        source_candidates = [numeric_source]
        if isinstance(numeric_source, int) and numeric_source == 0:
            source_candidates = [0, 1, 2, 3]

        if sys.platform.startswith("win"):
            backend_candidates = [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
        elif sys.platform.startswith("linux"):
            backend_candidates = [cv2.CAP_V4L2, cv2.CAP_ANY]
        else:
            backend_candidates = [cv2.CAP_ANY]

        for src in source_candidates:
            for backend in backend_candidates:
                if backend == cv2.CAP_ANY:
                    cap = cv2.VideoCapture(src)
                else:
                    cap = cv2.VideoCapture(src, backend)

                if not cap.isOpened():
                    cap.release()
                    continue

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

                ok, _ = cap.read()
                if ok:
                    logger.info("OpenCV camera opened (source=%s, backend=%s)", src, backend)
                    return cap, src, backend

                cap.release()

        return None, None, None

    def _select_full_fov_sensor_size(self, req_width: int, req_height: int):
        """
        Pick a sensor output size that reads the full sensor field-of-view (e.g. the
        2304x1296 2x2 binned mode on IMX708 Camera Module 3, or 1640x1232 on IMX219)
        instead of a center-cropped low-res mode (like 1536x864 on IMX708) where
        ScalerCrop and PDAF phase pixels are restricted.
        """
        if self._picam is None:
            return None
        try:
            full_res = self._picam.camera_properties.get("PixelArraySize")
            modes = getattr(self._picam, "sensor_modes", None) or []
            if not full_res or len(full_res) != 2 or not modes:
                return None

            full_w, full_h = full_res
            full_fov_modes = []
            for m in modes:
                size = m.get("size")
                crop = m.get("crop_limits")
                fps = float(m.get("fps", 30.0))
                if not size or len(size) != 2:
                    continue
                # Check if this mode covers >=95% of the physical pixel array
                if crop and len(crop) == 4:
                    if crop[2] < full_w * 0.95 or crop[3] < full_h * 0.95:
                        continue
                full_fov_modes.append((size[0], size[1], fps))

            if not full_fov_modes:
                return None

            # Prefer the smallest full-FoV mode (usually 2x2 binned, e.g. 2304x1296 @ 56fps
            # on IMX708) that is at least as large as the requested output and >=25 fps.
            fast_modes = [
                (w, h) for (w, h, fps) in full_fov_modes
                if fps >= 25.0 and w >= req_width and h >= req_height
            ]
            if fast_modes:
                fast_modes.sort(key=lambda s: s[0] * s[1])
                return fast_modes[0]

            # Fallback: smallest full-FoV mode overall (2x2 binned)
            full_fov_modes.sort(key=lambda s: s[0] * s[1])
            return (full_fov_modes[0][0], full_fov_modes[0][1])
        except Exception as e:
            logger.debug("Could not inspect sensor_modes for full FoV: %s", e)
            return None

    def set_focus(self, focus_mode: str = "continuous", lens_position: float | None = None) -> dict:
        """
        Configure autofocus or manual lens position on Picamera2 (Camera Module 3 / IMX708).

        Args:
            focus_mode:    "continuous" (default), "auto" (one-shot), or "manual".
            lens_position: Focus distance in dioptres (1 / meters) when focus_mode == "manual".
                           0.0 = infinity, ~5.2 = 19 cm, ~8.0 = 12.5 cm.

        Returns:
            dict with applied focus state for logging / API responses.
        """
        mode = str(focus_mode or "continuous").strip().lower()
        if mode not in ("continuous", "auto", "manual"):
            mode = "continuous"
        self._focus_mode = mode

        if lens_position is not None:
            try:
                self._lens_position = max(0.0, min(15.0, float(lens_position)))
            except (TypeError, ValueError):
                pass

        if self._backend != "picamera2" or self._picam is None:
            return {"supported": False, "mode": self._focus_mode, "reason": "not_picamera2"}

        controls_map = getattr(self._picam, "camera_controls", {}) or {}
        if "AfMode" not in controls_map:
            self._supports_af = False
            logger.warning(
                "Camera sensor '%s' does not expose AfMode (fixed-focus module such as "
                "CM1/CM2/HQ). Physical lens rotation is required for close-range focus.",
                self._camera_model or "unknown",
            )
            return {
                "supported": False,
                "mode": "fixed",
                "camera_model": self._camera_model,
            }

        self._supports_af = True

        try:
            if self._focus_mode == "manual":
                ctrl = {"AfMode": _AF_MODE_MANUAL}
                if "LensPosition" in controls_map:
                    ctrl["LensPosition"] = float(self._lens_position)
                self._picam.set_controls(ctrl)
                logger.info(
                    "Manual focus enabled (LensPosition=%.2f dioptres, ~%.0f cm).",
                    self._lens_position,
                    (100.0 / self._lens_position) if self._lens_position > 0 else 999.0,
                )
            else:
                # Continuous AF with Full range (macro + normal) and Fast speed so the
                # Camera Module 3 focuses reliably at close rack distances (~10-25 cm).
                ctrl = {"AfMode": _AF_MODE_CONTINUOUS}
                if "AfRange" in controls_map:
                    ctrl["AfRange"] = _AF_RANGE_FULL
                if "AfSpeed" in controls_map:
                    ctrl["AfSpeed"] = _AF_SPEED_FAST
                try:
                    self._picam.set_controls(ctrl)
                except Exception:
                    # Fallback if driver rejects AfRange/AfSpeed combination
                    self._picam.set_controls({"AfMode": _AF_MODE_CONTINUOUS})
                logger.info(
                    "Continuous autofocus enabled (AfRange=Full, AfSpeed=Fast) on '%s'.",
                    self._camera_model or "Picamera2",
                )
            return {
                "supported": True,
                "mode": self._focus_mode,
                "lens_position": self._lens_position,
                "camera_model": self._camera_model,
            }
        except Exception as e:
            logger.warning("Failed to set focus controls (%s): %s", self._focus_mode, e)
            return {"supported": True, "mode": self._focus_mode, "error": str(e)}

    def trigger_autofocus(self) -> dict:
        """
        Run an explicit autofocus cycle on Picamera2 and wait for the lens to lock.
        If the camera is in manual focus mode, re-applies the manual LensPosition.
        After locking in continuous mode, restores Continuous AF so live tracking continues.
        """
        if self._backend != "picamera2" or self._picam is None:
            return {"focused": False, "supported": False, "reason": "not_picamera2"}

        controls_map = getattr(self._picam, "camera_controls", {}) or {}
        if "AfMode" not in controls_map:
            return {
                "focused": False,
                "supported": False,
                "camera_model": self._camera_model,
                "reason": "fixed_focus_sensor",
            }

        if self._focus_mode == "manual":
            res = self.set_focus("manual", self._lens_position)
            return {"focused": True, **res}

        focused = False
        lens_pos = None
        af_state = None

        with self._picam_lock:
            try:
                # Ensure Full range (macro-capable) before running the AF sweep
                pre_ctrl = {}
                if "AfRange" in controls_map:
                    pre_ctrl["AfRange"] = _AF_RANGE_FULL
                if "AfSpeed" in controls_map:
                    pre_ctrl["AfSpeed"] = _AF_SPEED_FAST
                if pre_ctrl:
                    try:
                        self._picam.set_controls(pre_ctrl)
                    except Exception:
                        pass

                if hasattr(self._picam, "autofocus_cycle"):
                    focused = bool(self._picam.autofocus_cycle())
                else:
                    self._picam.set_controls({
                        "AfMode": _AF_MODE_AUTO,
                        "AfTrigger": _AF_TRIGGER_START,
                    })
                    time.sleep(0.8)
                    focused = True

                try:
                    meta = self._picam.capture_metadata() or {}
                    lens_pos = meta.get("LensPosition")
                    af_state = meta.get("AfState")
                except Exception:
                    pass

                logger.info(
                    "Autofocus cycle completed: focused=%s, LensPosition=%s, AfState=%s",
                    focused,
                    f"{lens_pos:.2f}" if isinstance(lens_pos, (int, float)) else lens_pos,
                    af_state,
                )
            except Exception as e:
                logger.warning("Autofocus cycle failed: %s", e)
            finally:
                # Restore continuous autofocus if that is the active mode
                if self._focus_mode == "continuous":
                    try:
                        restore_ctrl = {"AfMode": _AF_MODE_CONTINUOUS}
                        if "AfRange" in controls_map:
                            restore_ctrl["AfRange"] = _AF_RANGE_FULL
                        if "AfSpeed" in controls_map:
                            restore_ctrl["AfSpeed"] = _AF_SPEED_FAST
                        self._picam.set_controls(restore_ctrl)
                    except Exception:
                        try:
                            self._picam.set_controls({"AfMode": _AF_MODE_CONTINUOUS})
                        except Exception:
                            pass

        return {
            "focused": focused,
            "supported": True,
            "mode": self._focus_mode,
            "lens_position": lens_pos,
            "af_state": af_state,
            "camera_model": self._camera_model,
        }

    def start(
        self,
        source=0,
        width=640,
        height=480,
        focus_mode: str = "continuous",
        lens_position: float | None = None,
    ):
        if self.is_running:
            return

        if source in (0, "0", "pi", "picam") and Picamera2 is None and sys.platform.startswith("linux"):
            logger.warning(
                "picamera2 is not importable (%s); falling back to OpenCV V4L2 which "
                "cannot control Raspberry Pi autofocus/ISP. Recreate the venv with: "
                "python3 -m venv --system-site-packages <venv>",
                _PICAM_IMPORT_ERROR,
            )

        if source in (0, "0", "pi", "picam") and Picamera2 is not None:
            try:
                self._picam = Picamera2()
                self._camera_model = self._picam.camera_properties.get("Model", "unknown")
                logger.info("Opening Picamera2 (sensor model: %s)", self._camera_model)

                # Always request RGB888 — it is universally supported by all
                # Pi camera modules and libcamera versions.  BGR888 is
                # hardware-dependent and on some configurations delivers data
                # in RGB byte order despite the name, causing blue↔red swaps.
                self._picam_frame_is_rgb = True

                # FIX: Pick a full-FoV sensor mode (e.g. 2304x1296 2x2 binned on IMX708
                # Camera Module 3) when requesting a smaller output like 640x480 or
                # 1280x720. Otherwise libcamera selects the 1536x864 center-cropped mode
                # where both field-of-view and PDAF autofocus phase pixels are restricted.
                sensor_size = self._select_full_fov_sensor_size(width, height)
                config = None
                if sensor_size:
                    try:
                        config = self._picam.create_video_configuration(
                            main={"size": (width, height), "format": "RGB888"},
                            sensor={"output_size": sensor_size},
                        )
                        logger.info(
                            "Picamera2 configured with full-FoV sensor mode %dx%d -> main %dx%d.",
                            sensor_size[0],
                            sensor_size[1],
                            width,
                            height,
                        )
                    except Exception as _cfg_err:
                        logger.debug("sensor output_size config fallback: %s", _cfg_err)
                        config = None

                if config is None:
                    config = self._picam.create_video_configuration(
                        main={"size": (width, height), "format": "RGB888"}
                    )

                self._picam.configure(config)
                self._picam.start()

                # ── Field-of-view: use the full sensor pixel array so the
                #    camera is not digitally zoomed in.  This is the widest
                #    possible crop and effectively "zooms out" the image.
                try:
                    full_res = self._picam.camera_properties.get("PixelArraySize")
                    if full_res and len(full_res) == 2:
                        self._picam.set_controls({
                            "ScalerCrop": (0, 0, full_res[0], full_res[1])
                        })
                        logger.info("ScalerCrop set to full sensor %dx%d.", *full_res)
                except Exception as _e:
                    logger.debug("ScalerCrop not applied: %s", _e)

                # ── Sharpness: raise above the 1.0 default to compensate for
                #    the close capture distance and any sensor softness.
                try:
                    self._picam.set_controls({"Sharpness": 2.5})
                except Exception as _e:
                    logger.debug("Sharpness not applied: %s", _e)

                self._backend = "picamera2"

                # ── Autofocus / Manual focus (Camera Module 3 / IMX708):
                #    Apply focus mode and run an initial autofocus_cycle() before
                #    starting the capture thread so the lens locks onto the close-range
                #    rack immediately instead of staying blurry at infinity.
                self.set_focus(focus_mode=focus_mode, lens_position=lens_position)
                if self._supports_af and self._focus_mode != "manual":
                    self.trigger_autofocus()

                self.is_running = True
                self._thread = Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                logger.info(
                    "Camera started with Picamera2 (%dx%d, sensor=%s, focus=%s).",
                    width,
                    height,
                    self._camera_model,
                    self._focus_mode if self._supports_af else "fixed",
                )
                return
            except Exception as e:
                logger.warning("Picamera2 start failed, falling back to OpenCV: %s", e)
                try:
                    if self._picam is not None:
                        self._picam.close()
                except Exception:
                    pass
                self._picam = None
                self._picam_frame_is_rgb = False
                self._backend = None

        self.cap, opened_source, opened_backend = self._open_opencv_capture(
            source, width, height
        )

        if self.cap is None or not self.cap.isOpened():
            hint = ""
            if sys.platform.startswith("win"):
                hint = (
                    " On Windows, make sure no other app is using the webcam, "
                    "privacy camera access is enabled, and try source 0/1."
                )
            elif sys.platform.startswith("linux") and source in (0, "0", "pi", "picam"):
                hint = " On Raspberry Pi camera module, install/use python3-picamera2."
            raise RuntimeError(
                f"Could not open camera source: {source}.{hint}"
            )

        self._backend = "opencv"
        self.is_running = True
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Camera started with OpenCV (requested=%s, opened=%s, backend=%s, %dx%d).",
            source,
            opened_source,
            opened_backend,
            width,
            height,
        )

    def _capture_loop(self):
        while self.is_running:
            if self._backend == "picamera2":
                try:
                    # capture_image() returns a PIL Image in standard RGB —
                    # it is format-agnostic and works correctly on every Pi
                    # camera module regardless of libcamera format quirks.
                    with self._picam_lock:
                        if self._picam is None or not self.is_running:
                            break
                        pil_frame = self._picam.capture_image("main")
                    # Ensure RGB mode (handles rare RGBA output)
                    if pil_frame.mode != "RGB":
                        pil_frame = pil_frame.convert("RGB")
                    # Convert RGB → BGR for OpenCV convention
                    frame = cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)

                    if self._pi_hflip and self._pi_vflip:
                        frame = cv2.flip(frame, -1)
                    elif self._pi_hflip:
                        frame = cv2.flip(frame, 1)
                    elif self._pi_vflip:
                        frame = cv2.flip(frame, 0)

                    with self._frame_lock:
                        self._latest_frame = frame
                    time.sleep(0.01)
                except Exception:
                    time.sleep(0.05)
                continue

            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.05)
                continue

            ret, frame = self.cap.read()
            if ret:
                # FIX: acquire lock before writing so get_frame() never reads
                # a half-written numpy array on a non-CPython runtime.
                with self._frame_lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.05)

    def get_frame(self):
        # FIX: acquire lock before reading
        with self._frame_lock:
            return self._latest_frame

    def stop(self):
        if not self.is_running:
            return

        # Signal the capture loop to exit
        self.is_running = False

        # FIX: join the thread instead of sleeping for an arbitrary 200 ms.
        # Previously, stop() released self.cap after only time.sleep(0.2),
        # which could race with _capture_loop() still calling self.cap.read().
        # join() guarantees the thread has fully exited before we release.
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("Camera thread did not stop within timeout.")
            self._thread = None

        if self._backend == "picamera2" and self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
            try:
                self._picam.close()
            except Exception:
                pass
            self._picam = None
            self._picam_frame_is_rgb = False

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        # Clear the stored frame so stale data isn't returned after restart
        with self._frame_lock:
            self._latest_frame = None

        self._backend = None

        logger.info("Camera stopped.")

    def camera_available(self):
        if self._backend == "picamera2":
            return self._picam is not None and self.is_running
        return self.cap is not None and self.cap.isOpened()
