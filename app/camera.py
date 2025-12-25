import cv2
import time
from threading import Thread

class Camera:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.latest_frame = None
        
    def start(self, source=0, width=640, height=480):
        if self.is_running:
            return

        self.cap = cv2.VideoCapture(source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        if not self.cap.isOpened():
            raise RuntimeError("Could not open camera")

        self.is_running = True
        
        # Start background thread to keep buffer empty (important for low latency)
        # However, for simplicity/safety with asyncio, we can just read on demand 
        # OR use a thread to constantly read the latest frame.
        # Threading is better for latency.
        self.thread = Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        while self.is_running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame
            else:
                # If reading fails, maybe brief pause
                time.sleep(0.1)

    def get_frame(self):
        return self.latest_frame

    def stop(self):
        self.is_running = False
        if self.camera_available():
            # Wait a bit for thread to finish
            time.sleep(0.2)
            self.cap.release()
            self.cap = None

    def camera_available(self):
        return self.cap is not None and self.cap.isOpened()
