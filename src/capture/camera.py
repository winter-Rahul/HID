"""
Webcam Capture Service with Non-blocking Ring Buffer
"""
import cv2
import time
import threading
import numpy as np
from typing import List, Tuple, Optional


class CameraStream:
    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480, buffer_size: int = 10):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.buffer_size = buffer_size

        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if not self.cap.isOpened():
            print(f"[CameraStream] WARNING: Failed to open camera {camera_index}")

        self.running = True
        self.lock = threading.Lock()
        self.frame_buffer: List[Tuple[float, np.ndarray]] = []
        self.latest_frame: Optional[np.ndarray] = None

        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        """Continuously pulls frames from webcam into memory ring buffer."""
        while self.running:
            if not self.cap.isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Mirror frame horizontally so user sees natural selfie/kiosk perspective
            frame = cv2.flip(frame, 1)

            ts = time.monotonic()
            with self.lock:
                self.latest_frame = frame.copy()
                self.frame_buffer.append((ts, frame.copy()))
                if len(self.frame_buffer) > self.buffer_size:
                    self.frame_buffer.pop(0)

            time.sleep(0.01)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_burst(self, n_frames: int = 8) -> List[Tuple[float, np.ndarray]]:
        """Returns the most recent n_frames with monotonic timestamps."""
        with self.lock:
            return [(ts, f.copy()) for ts, f in self.frame_buffer[-n_frames:]]

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap.isOpened():
            self.cap.release()
