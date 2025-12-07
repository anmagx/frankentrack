"""OpenCV camera provider wrapper for the camera worker.

Provides a simple, consistent interface:
  - read() -> (frame, timestamp)  (frame is BGR numpy array)
  - set_params(width, height, fps)
  - close()

This module isolates OpenCV-specific capture logic so the worker can orchestrate
backends uniformly.
"""
import time
import cv2
from config.config import CAMERA_OPEN_TIMEOUT


class OpenCVCameraProvider:
    def __init__(self, index, width, height, fps, logQueue=None):
        self.index = int(index)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps) if fps is not None else None
        self.logQueue = logQueue
        self.cap = None
        self._open()

    def _open(self):
        try:
            self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            start = time.time()
            while not self.cap.isOpened() and (time.time() - start) < float(CAMERA_OPEN_TIMEOUT):
                time.sleep(0.05)
            if not self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
                return False
            try:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if self.fps is not None:
                    self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            except Exception:
                pass
            return True
        except Exception:
            try:
                if self.cap is not None:
                    self.cap.release()
            except Exception:
                pass
            self.cap = None
            return False

    def read(self):
        if self.cap is None:
            return (None, None)
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return (None, None)
            return (frame, time.time())
        except Exception:
            return (None, None)

    def set_params(self, width, height, fps):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps) if fps is not None else None
        if self.cap is not None:
            try:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            except Exception:
                pass
            try:
                if self.fps is not None:
                    self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            except Exception:
                pass

    def set_setting(self, name, value):
        """Set capture property (exposure, gain) where supported by OpenCV backend.

        Returns True on success, False otherwise.
        """
        if self.cap is None:
            return False
        try:
            if name == 'exposure':
                # Note: exposure values and behavior vary by backend/platform
                return bool(self.cap.set(cv2.CAP_PROP_EXPOSURE, float(value)))
            if name == 'gain':
                return bool(self.cap.set(cv2.CAP_PROP_GAIN, float(value)))
            # unsupported
            return False
        except Exception:
            return False

    def close(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
