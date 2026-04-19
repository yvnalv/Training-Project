import logging
import time
import importlib
import sys
from threading import Thread, Lock

import cv2
import numpy as np

try:
    Picamera2 = importlib.import_module("picamera2").Picamera2
except Exception:
    Picamera2 = None

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self._latest_frame = None
        self._frame_lock = Lock()      # FIX: protects latest_frame across threads
        self._thread = None
        self._backend = None
        self._picam = None
        self._picam_frame_is_rgb = False
        self._pi_hflip = True
        self._pi_vflip = True

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

    def start(self, source=0, width=640, height=480):
        if self.is_running:
            return

        if source in (0, "0", "pi", "picam") and Picamera2 is not None:
            try:
                self._picam = Picamera2()
                # Always request RGB888 — it is universally supported by all
                # Pi camera modules and libcamera versions.  BGR888 is
                # hardware-dependent and on some configurations delivers data
                # in RGB byte order despite the name, causing blue↔red swaps.
                self._picam_frame_is_rgb = True
                config = self._picam.create_video_configuration(
                    main={"size": (width, height), "format": "RGB888"}
                )

                self._picam.configure(config)
                self._picam.start()

                self._backend = "picamera2"
                self.is_running = True
                self._thread = Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                logger.info(
                    "Camera started with Picamera2 (%dx%d, format=RGB888).",
                    width,
                    height,
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