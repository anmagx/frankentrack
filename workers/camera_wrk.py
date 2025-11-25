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
    ('set_backend', backend_key)  # 'openCV' or 'pseyepy'

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
    QUEUE_PUT_TIMEOUT,
    CAMERA_LOOP_DELAY,
    CAMERA_OPEN_TIMEOUT,
    CAPTURE_RETRY_DELAY
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
    
    # Announce startup both to log queue and stdout so main process can see worker started
    log_info(logQueue, "Camera Worker", "Starting camera worker")
    try:
        print("[Camera Worker] Starting camera worker...")
    except Exception:
        pass
    
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
    
    provider = None
    want_preview = False
    tracking = False
    target_cam = int(cam_index)
    backend = 'openCV'  # default backend; can be set to 'pseyepy'

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
        # track whether capture was open on previous loop to detect transitions
        cap_was_open = False

        while stop_event is None or not stop_event.is_set():
            # process control commands (drain queue)
            if control_queue is not None:
                cmd = safe_queue_get(control_queue, timeout=0.0, default=None)
                while cmd is not None:
                    try:
                        log_info(logQueue, "Camera Worker", f"Control command received: {cmd}")
                    except Exception:
                        pass
                    # (debug prints removed) command is logged via log_info above
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
                            
                            # if provider already open, try to apply settings immediately
                            if provider is not None:
                                try:
                                    try:
                                        provider.set_params(frame_w, frame_h, desired_fps)
                                    except Exception:
                                        # If provider cannot apply params in-place, recreate it next loop
                                        try:
                                            provider.close()
                                        except Exception:
                                            pass
                                        provider = None
                                except Exception:
                                    pass
                        elif cmd[0] == 'set_cam' and len(cmd) >= 2:
                            try:
                                target_cam = int(cmd[1])
                                # reopen capture on next loop
                                if provider is not None:
                                    try:
                                        provider.close()
                                    except Exception:
                                        pass
                                    provider = None
                            except (ValueError, TypeError):
                                pass
                        elif cmd[0] == 'set_backend' and len(cmd) >= 2:
                            # ('set_backend', 'pseyepy'|'openCV' or display names)
                            try:
                                val = str(cmd[1])
                                new_backend = 'pseyepy' if 'pseyepy' in val.lower() else 'openCV'
                                if new_backend != backend:
                                    backend = new_backend
                                    # close existing capture so it will be reopened with new backend
                                    if provider is not None:
                                        try:
                                            provider.close()
                                        except Exception:
                                            pass
                                        provider = None
                                    try:
                                        log_info(logQueue, "Camera Worker", f"Backend switched to {backend}")
                                    except Exception:
                                        pass
                                    # (debug print removed)
                            except Exception:
                                pass
                        elif cmd[0] == 'calibrate':
                            # future: handle calibrate
                            pass
                        elif cmd[0] == 'set_cam_setting' and len(cmd) >= 3:
                            # ('set_cam_setting', name, value)
                            try:
                                name = str(cmd[1])
                                val = cmd[2]
                                # If provider already open, try to apply immediately
                                if provider is not None and hasattr(provider, 'set_setting'):
                                    try:
                                        provider.set_setting(name, val)
                                    except Exception:
                                        pass
                                else:
                                    # If no provider yet, ignore or remember for later (not implemented)
                                    pass
                            except Exception:
                                pass
                    
                    # Get next command
                    cmd = safe_queue_get(control_queue, timeout=0.0, default=None)

            # If neither preview nor tracking requested, release the capture device to reset state
            if not want_preview and not tracking and provider is not None:
                try:
                    provider.close()
                except Exception:
                    pass
                provider = None
                # notify UI that camera is idle (0 fps)
                try:
                    safe_queue_put(statusQueue, ('cam_fps', 0.0), timeout=QUEUE_PUT_TIMEOUT)
                except Exception:
                    pass

            # ensure capture open if preview or tracking required
            if (want_preview or tracking) and provider is None:
                try:
                    log_info(logQueue, "Camera Worker", f"Opening camera {target_cam} at {frame_w}x{frame_h} using backend={backend}")
                    # Lazy import providers to avoid importing pseyepy/opencv at module import time
                    try:
                        if backend == 'openCV':
                            from workers.cameraProvider_openCV import OpenCVCameraProvider
                            provider = OpenCVCameraProvider(target_cam, frame_w, frame_h, desired_fps, logQueue=logQueue)
                        else:
                            from workers.cameraProvider_pseyepy import PSEyeProvider
                            provider = PSEyeProvider(target_cam, frame_w, frame_h, desired_fps, logQueue=logQueue)
                        # If provider failed to open, provider implementations return None-internal state
                        if provider is None:
                            provider = None
                        else:
                            try:
                                pname = getattr(provider, '__class__', type(provider)).__name__
                                log_info(logQueue, 'Camera Worker', f'Provider created: {pname} (backend={backend})')
                            except Exception:
                                pass
                            # (debug print removed)
                    except Exception as e:
                        log_error(logQueue, "Camera Worker", f"Failed to create provider for backend {backend}: {e}")
                        provider = None
                except Exception as e:
                    log_error(logQueue, "Camera Worker", f"Failed to open camera {target_cam}: {e}")
                    provider = None

            if provider is None:
                try:
                    time.sleep(CAPTURE_RETRY_DELAY)
                except KeyboardInterrupt:
                    break
                continue
            # Read unified frame from provider: (frame, ts)
            try:
                frame, _ts = provider.read()
            except Exception:
                frame, _ts = (None, None)
            if frame is None:
                try:
                    time.sleep(CAPTURE_RETRY_DELAY)
                except KeyboardInterrupt:
                    break
                continue
            # For preview-only mode avoid unnecessary copies and heavy
            # grayscale / contour work. Only prepare a copy and compute
            # grayscale when position tracking is enabled.
            if tracking:
                proc = frame.copy()
                gray = cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY)
            else:
                # Use frame directly for preview pipeline (no overlay required)
                proc = frame
                gray = None
            # mark that cap is open
            cap_was_open = True
            # Count frame for FPS calculation
            try:
                frames_count += 1
            except Exception:
                frames_count = 0

            # proc and gray are prepared by backend-specific read logic above

            # Only run blob detection when tracking is requested
            blob = None
            if tracking:
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
                        # Avoid logging every preview frame (too verbose / costly)
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

            # Frame pacing: if desired_fps was requested, try to pace loop to that rate.
            # Otherwise, fall back to a small sleep to avoid busy-looping.
            try:
                loop_elapsed = time.time() - now
                if desired_fps is not None and desired_fps > 0:
                    target_interval = 1.0 / float(desired_fps)
                    delay = target_interval - loop_elapsed
                    if delay > 0:
                        time.sleep(delay)
                else:
                    # small sleep to yield CPU when no explicit fps target
                    time.sleep(CAMERA_LOOP_DELAY)
            except Exception:
                try:
                    time.sleep(CAMERA_LOOP_DELAY)
                except Exception:
                    pass

    finally:
        try:
            if provider is not None:
                try:
                    provider.close()
                except Exception:
                    pass
        except Exception:
            pass
        log_info(logQueue, "Camera Worker", "Stopped")
        try:
            print("[Camera Worker] Stopped.")
        except Exception:
            pass
