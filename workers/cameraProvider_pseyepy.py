"""PS3Eye (pseyepy) camera provider wrapper for the camera worker.

Provides a consistent interface with the OpenCV provider:
  - read() -> (frame, timestamp)  (frame returned as BGR numpy array)
  - set_params(width, height, fps)
  - close()

This module isolates pseyepy specifics so the worker can switch backends easily.
"""
import time
from util.log_utils import log_info, log_error


class PSEyeProvider:
    def __init__(self, index, width, height, fps, logQueue=None):
        self.index = int(index)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps) if fps is not None else None
        self.logQueue = logQueue
        self.camera = None
        self._open()

    def _open(self):
        try:
            import pseyepy
            Camera = pseyepy.Camera
            # Choose resolution constant roughly based on requested width
            try:
                res_const = Camera.RES_SMALL if self.width <= 320 else Camera.RES_LARGE
            except Exception:
                res_const = 0

            if self.fps is not None:
                self.camera = Camera(ids=self.index, resolution=res_const, fps=self.fps, colour=True)
            else:
                self.camera = Camera(ids=self.index, resolution=res_const, colour=True)
            try:
                log_info(self.logQueue, 'PSEyeProvider', f'Opened PS3Eye camera {self.index} ({self.width}x{self.height}) fps={self.fps}')
            except Exception:
                pass
            # Always print to stdout too so worker console shows open result
            # (debug print removed)
            return True
        except Exception as e:
            self.camera = None
            try:
                log_error(self.logQueue, 'PSEyeProvider', f'Failed to open PS3Eye camera {self.index}: {e}')
            except Exception:
                pass
            # Always print failure to stdout as well
            # (debug print removed)
            return False

    def read(self):
        if self.camera is None:
            # Don't log here - this would spam if called in a loop waiting for camera
            return (None, None)
        try:
            # pseyepy returns (imgs, ts)
            data = self.camera.read(timestamp=True, squeeze=True)
            if data is None:
                # Don't log per-frame errors - they can spam at high FPS
                return (None, None)
            frame_obj, ts = data
            if frame_obj is None:
                # Don't log per-frame errors - they can spam at high FPS
                return (None, None)
            # Try to convert RGB -> BGR for downstream OpenCV processing
            try:
                import cv2
                frame_bgr = cv2.cvtColor(frame_obj, cv2.COLOR_RGB2BGR)
            except Exception:
                frame_bgr = frame_obj.copy()
            # NOTE: Do NOT log every frame here - it destroys performance at high FPS!
            return (frame_bgr, ts)
        except Exception:
            # Don't log per-frame exceptions - they can spam at high FPS
            return (None, None)

    def set_params(self, width, height, fps):
        # Recreate camera with new params
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps) if fps is not None else None
        try:
            self.close()
        except Exception:
            pass
        self._open()

    def set_setting(self, name, value):
        """Set a camera parameter (e.g., 'exposure', 'gain') on the underlying pseyepy Camera.

        Returns True on success, False otherwise.
        """
        if self.camera is None:
            return False
        try:
            # Camera exposes attributes like 'exposure' and 'gain' that map to on-board controls
            if hasattr(self.camera, name):
                try:
                    setattr(self.camera, name, int(value))
                    return True
                except Exception:
                    return False
            else:
                return False
        except Exception:
            return False

    def close(self):
        if self.camera is not None:
            try:
                self.camera.end()
            except Exception:
                pass
            self.camera = None
