import logging
import time
from threading import Thread, Lock

import cv2

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self._latest_frame = None
        self._frame_lock = Lock()      # FIX: protects latest_frame across threads
        self._thread = None

    def start(self, source=0, width=640, height=480):
        if self.is_running:
            return

        self.cap = cv2.VideoCapture(source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera source: {source}")

        self.is_running = True
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Camera started (source=%s, %dx%d).", source, width, height)

    def _capture_loop(self):
        while self.is_running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # FIX: acquire lock before writing so get_frame() never reads
                # a half-written numpy array on a non-CPython runtime.
                with self._frame_lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.1)

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

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        # Clear the stored frame so stale data isn't returned after restart
        with self._frame_lock:
            self._latest_frame = None

        logger.info("Camera stopped.")

    def camera_available(self):
        return self.cap is not None and self.cap.isOpened()