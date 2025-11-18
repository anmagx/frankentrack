"""
Camera tracking worker: captures frames, detects a bright marker, computes X,Y,Z,
publishes translation data to translationQueue and translationDisplayQueue,
and sends preview JPEG bytes to cameraPreviewQueue when requested.

Command protocol on cameraControlQueue:
  ('preview_on',)
  ('preview_off',)
  ('start_pos',)
  ('stop_pos',)
  ('set_cam', cam_index)
  ('calibrate',)

This worker runs as a separate process. It only sends primitive data (lists
and bytes) across multiprocessing queues; no Tk objects are created here.
"""

import time
import cv2
from queue import Empty

from config.config import (
    STALE_DETECTION_TIMEOUT,
    MIN_BLOB_AREA,
    PREVIEW_WIDTH,
    PREVIEW_HEIGHT,
    JPEG_QUALITY,
    LOWPASS_ALPHA,
    POSITION_CLAMP_MIN,
    POSITION_CLAMP_MAX,
    DEFAULT_CAMERA_WIDTH,
    DEFAULT_CAMERA_HEIGHT,
    DEFAULT_DETECTION_THRESHOLD,
    FPS_REPORT_INTERVAL,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put, safe_queue_get, clamp, safe_float_convert

# Simple smoothing helper
class LowPass:
    def __init__(self, alpha=LOWPASS_ALPHA, init=0.0):
        self.alpha = alpha
        self.val = float(init)
    def update(self, x):
        self.val = (1.0 - self.alpha) * self.val + self.alpha * float(x)
        return self.val


def _find_largest_blob(gray, thresh=DEFAULT_DETECTION_THRESHOLD, min_area=MIN_BLOB_AREA):
    """Find the largest bright blob in grayscale image.
    
    Args:
        gray: Grayscale image
        thresh: Brightness threshold (0-255)
        min_area: Minimum contour area in pixels
    
    Returns:
        Tuple of (cx, cy, area) or None if no blob found
    """
    # Validate threshold
    thresh = clamp(thresh, 0, 255)
    
    _, b = cv2.threshold(gray, int(thresh), 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    # pick largest contour
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < min_area:
        return None
    m = cv2.moments(c)
    if m.get('m00', 0) == 0:
        return None
    cx = int(m['m10'] / m['m00'])
    cy = int(m['m01'] / m['m00'])
    return (cx, cy, area)


def run_worker(translationQueue, translationDisplayQueue, cameraControlQueue, stop_event, cameraPreviewQueue=None, statusQueue=None, logQueue=None, cam_index=0, thresh_value=DEFAULT_DETECTION_THRESHOLD):
    """Entry point for Process spawn."""
    from util.log_utils import log_info, log_error
    
    log_info(logQueue, "Camera Worker", "Starting camera worker")
    
    try:
        tracking_thread(translationQueue, translationDisplayQueue, stop_event, statusQueue=statusQueue, logQueue=logQueue, cam_index=cam_index, thresh_value=thresh_value, preview_queue=cameraPreviewQueue, control_queue=cameraControlQueue)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_error(logQueue, "Camera Worker", f"Worker error: {e}")
        try:
            print(f"[Camera Worker] Error: {e}")
        except Exception:
            pass


def tracking_thread(translationQueue, translationDisplayQueue, stop_event, statusQueue=None, logQueue=None, cam_index=0, thresh_value=DEFAULT_DETECTION_THRESHOLD, preview_queue=None, control_queue=None):
    """Main capture + tracking loop. Listens to `control_queue` for commands.
    
    Args:
        translationQueue: Queue for publishing translation data to UDP worker
        translationDisplayQueue: Queue for publishing translation data to GUI
        stop_event: Event to signal worker shutdown
        statusQueue: Queue for status updates (FPS, etc.)
        logQueue: Queue for logging messages
        cam_index: Camera device index
        thresh_value: Brightness threshold for detection (0-255)
        preview_queue: Queue for preview frames
        control_queue: Queue for receiving control commands
    """
    from util.log_utils import log_info, log_error
    
    cap = None
    want_preview = False
    tracking = False
    target_cam = int(cam_index)

    # smoothed outputs (using LOWPASS_ALPHA from config)
    sx = LowPass(LOWPASS_ALPHA, 0.0)
    sy = LowPass(LOWPASS_ALPHA, 0.0)

    # calibration / frame size
    frame_w, frame_h = DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT
    desired_fps = None

    # (unused throttling variables removed to satisfy linter)

    try:
        # last published positions (persist while detections are intermittent)
        last_x = None
        last_y = None
        last_detection_time = None
        lost_state = False
        # FPS reporting for actual camera input (frames read from capture)
        frames_count = 0
        last_fps_ts = time.time()

        while stop_event is None or not stop_event.is_set():
            # process control commands (drain queue)
            if control_queue is not None:
                cmd = safe_queue_get(control_queue, timeout=0.0, default=None)
                while cmd is not None:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 1:
                        if cmd[0] == 'preview_on':
                            want_preview = True
                        elif cmd[0] == 'preview_off':
                            want_preview = False
                        elif cmd[0] == 'start_pos':
                            tracking = True
                        elif cmd[0] == 'stop_pos':
                            tracking = False
                        elif cmd[0] == 'set_thresh' and len(cmd) >= 2:
                            # Validate and clamp threshold to valid range
                            thresh_value = safe_float_convert(cmd[1], default=thresh_value, 
                                                             min_val=0.0, max_val=255.0)
                            thresh_value = int(thresh_value)
                        elif cmd[0] == 'set_cam_params' and len(cmd) >= 4:
                            # ('set_cam_params', fps, width, height)
                            desired_fps = safe_float_convert(cmd[1], default=None, 
                                                            min_val=1.0, max_val=240.0)
                            if desired_fps is not None:
                                desired_fps = int(desired_fps)
                            
                            frame_w = safe_float_convert(cmd[2], default=frame_w, 
                                                        min_val=160.0, max_val=4096.0)
                            frame_w = int(frame_w)
                            
                            frame_h = safe_float_convert(cmd[3], default=frame_h, 
                                                        min_val=120.0, max_val=4096.0)
                            frame_h = int(frame_h)
                            
                            # if capture already open, try to apply settings immediately
                            if cap is not None:
                                try:
                                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_w)
                                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_h)
                                    if desired_fps is not None:
                                        cap.set(cv2.CAP_PROP_FPS, desired_fps)
                                except Exception:
                                    pass
                        elif cmd[0] == 'set_cam' and len(cmd) >= 2:
                            try:
                                target_cam = int(cmd[1])
                                # reopen capture on next loop
                                if cap is not None:
                                    try:
                                        cap.release()
                                    except Exception:
                                        pass
                                    cap = None
                            except (ValueError, TypeError):
                                pass
                        elif cmd[0] == 'calibrate':
                            # future: handle calibrate
                            pass
                    
                    # Get next command
                    cmd = safe_queue_get(control_queue, timeout=0.0, default=None)

            # If neither preview nor tracking requested, release the capture device to reset state
            if not want_preview and not tracking and cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None

            # ensure capture open if preview or tracking required
            if (want_preview or tracking) and cap is None:
                try:
                    log_info(logQueue, "Camera Worker", f"Opening camera {target_cam} at {frame_w}x{frame_h}")
                    cap = cv2.VideoCapture(target_cam, cv2.CAP_DSHOW)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_h)
                    try:
                        if desired_fps is not None:
                            cap.set(cv2.CAP_PROP_FPS, desired_fps)
                    except Exception:
                        pass
                except Exception as e:
                    log_error(logQueue, "Camera Worker", f"Failed to open camera {target_cam}: {e}")
                    cap = None

            if cap is None:
                try:
                    time.sleep(0.05)
                except KeyboardInterrupt:
                    break
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                try:
                    time.sleep(0.02)
                except KeyboardInterrupt:
                    break
                continue
            # Count frame for FPS calculation
            try:
                frames_count += 1
            except Exception:
                frames_count = 0

            # Work on a copy
            proc = frame.copy()
            gray = cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY)

            blob = _find_largest_blob(gray, thresh=thresh_value, min_area=MIN_BLOB_AREA)

            now = time.time()
            if blob is not None and tracking:
                cx, cy, area = blob

                # Map X/Y to the same -30..+30 range used by SimpleTracker
                x_delta_pixels = float(cx) - (frame_w / 2.0)
                y_delta_pixels = (frame_h / 2.0) - float(cy)
                x_raw = (x_delta_pixels / float(frame_w)) * 60.0
                y_raw = (y_delta_pixels / float(frame_h)) * 60.0

                # We only care about X and Y. Disable Z estimation and publish 0.0.
                vx = sx.update(x_raw)
                vy = sy.update(y_raw)

                # Clamp outputs using constants from config
                x_val = float(clamp(vx, POSITION_CLAMP_MIN, POSITION_CLAMP_MAX))
                y_val = float(clamp(vy, POSITION_CLAMP_MIN, POSITION_CLAMP_MAX))
                z_val = 0.0

                tdata = [x_val, y_val, z_val]
                # remember last-known values
                last_x = x_val
                last_y = y_val
                last_detection_time = now
                if lost_state:
                    # detector restored
                    lost_state = False
                    safe_queue_put(translationDisplayQueue, ('_CAM_STATUS_', 'restored'), 
                                 timeout=QUEUE_PUT_TIMEOUT)
                    try:
                        print('[Camera Worker] Marker restored')
                    except Exception:
                        pass
                
                # publish for UDP and GUI display
                safe_queue_put(translationQueue, tdata, timeout=QUEUE_PUT_TIMEOUT)
                safe_queue_put(translationDisplayQueue, tdata, timeout=QUEUE_PUT_TIMEOUT)

                # draw overlay on proc
                cv2.circle(proc, (int(cx), int(cy)), 6, (0,255,0), 2)
                cv2.putText(proc, f"X:{x_val:.2f} Y:{y_val:.2f}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
            elif tracking:
                # No blob found but tracking is active: either re-publish last-known XY
                # while within STALE_DETECTION_TIMEOUT, or mark tracking as stale.
                if last_x is not None and last_y is not None:
                    if last_detection_time is not None and (now - last_detection_time) <= STALE_DETECTION_TIMEOUT:
                        tdata = [float(last_x), float(last_y), 0.0]
                        safe_queue_put(translationQueue, tdata, timeout=QUEUE_PUT_TIMEOUT)
                        safe_queue_put(translationDisplayQueue, tdata, timeout=QUEUE_PUT_TIMEOUT)
                    else:
                        # stale: stop republishing and notify once
                        if not lost_state:
                            lost_state = True
                            safe_queue_put(translationDisplayQueue, ('_CAM_STATUS_', 'lost'), 
                                         timeout=QUEUE_PUT_TIMEOUT)
                            try:
                                print('[Camera Worker] Marker lost (stale)')
                            except Exception:
                                pass

            # preview handling: downscale and send JPEG bytes
            if want_preview and preview_queue is not None:
                try:
                    # downscale using constants from config
                    disp = cv2.resize(proc, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
                    ret2, buf = cv2.imencode('.jpg', disp, 
                                            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                    if ret2:
                        jpg_bytes = buf.tobytes()
                        # Drop frame if queue full (intentionally small queue)
                        safe_queue_put(preview_queue, (jpg_bytes, time.time()), 
                                     timeout=QUEUE_PUT_TIMEOUT)
                except Exception:
                    pass

            # Periodically report the camera input FPS (based on frames read)
            try:
                now_fps = time.time()
                if (now_fps - last_fps_ts) >= FPS_REPORT_INTERVAL:
                    elapsed = now_fps - last_fps_ts
                    fps = float(frames_count) / elapsed if elapsed > 0 else 0.0
                    frames_count = 0
                    last_fps_ts = now_fps
                    # send camera FPS to statusQueue
                    safe_queue_put(statusQueue, ('cam_fps', fps), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

            # throttle loop a bit
            time.sleep(0.01)

    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
        log_info(logQueue, "Camera Worker", "Stopped")
        try:
            print("[Camera Worker] Stopped.")
        except Exception:
            pass
