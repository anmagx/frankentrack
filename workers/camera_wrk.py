"""
Camera tracking worker process.

This worker captures frames from a PS3 Eye camera via `pseyepy`, detects a
bright marker, computes X/Y/Z (Z currently 0.0), and publishes translation
data to `translationQueue` and `translationDisplayQueue`. Preview JPEG bytes
are published to `cameraPreviewQueue` when requested.

Control commands are received on `cameraControlQueue` (see legacy `inspect/` file
for supported commands). The implementation deliberately performs lazy imports
of provider code so that `pseyepy` is only imported inside the worker process.
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
    CAPTURE_RETRY_DELAY,
    QUEUE_SIZE_DISPLAY,
)
from util.error_utils import safe_queue_put, safe_queue_get, clamp, safe_float_convert


class LowPass:
    def __init__(self, alpha=LOWPASS_ALPHA, init=0.0):
        self.alpha = alpha
        self.val = float(init)

    def update(self, x):
        self.val = (1.0 - self.alpha) * self.val + self.alpha * float(x)
        return self.val


def _find_largest_blob(gray, thresh=DEFAULT_DETECTION_THRESHOLD, min_area=MIN_BLOB_AREA):
    thresh = clamp(thresh, 0, 255)
    _, b = cv2.threshold(gray, int(thresh), 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
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
    from util.log_utils import log_info, log_error
    import traceback
    import os
    import sys
    import json
    import tempfile
    import platform

    # Announce startup
    try:
        log_info(logQueue, "Camera Worker", "Starting camera worker")
    except Exception:
        pass
    try:
        print("[Camera Worker] Starting camera worker...")
    except Exception:
        pass

    # Create a small debug dump file for this worker (PID/env/args) and
    # redirect stdout/stderr there so native crashes can be correlated.
    try:
        pid = os.getpid()
        td = tempfile.gettempdir()
        dbg_base = os.path.join(td, f"frankentrack_camera_{pid}")
        env_path = dbg_base + ".env.json"
        out_path = dbg_base + ".out.log"
        err_path = dbg_base + ".err.log"
        try:
            info = {
                'pid': pid,
                'exe': sys.executable,
                'python': platform.python_version(),
                'cwd': os.getcwd(),
                'argv': sys.argv,
                'time': time.time(),
            }
            with open(env_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2)
        except Exception:
            pass
        try:
            # Redirect stdout/stderr to files to capture any native crashes output
            so = open(out_path, 'a', buffering=1, encoding='utf-8', errors='replace')
            se = open(err_path, 'a', buffering=1, encoding='utf-8', errors='replace')
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(so.fileno(), sys.stdout.fileno())
            os.dup2(se.fileno(), sys.stderr.fileno())
        except Exception:
            pass
    except Exception:
        pass

    # Run main tracking thread and capture any unexpected exceptions with full traceback
    try:
        tracking_thread(translationQueue, translationDisplayQueue, stop_event, statusQueue=statusQueue, logQueue=logQueue, cam_index=cam_index, thresh_value=thresh_value, preview_queue=cameraPreviewQueue, control_queue=cameraControlQueue)
    except KeyboardInterrupt:
        pass
    except SystemExit:
        # Allow clean exit
        raise
    except Exception:
        tb = traceback.format_exc()
        try:
            log_error(logQueue, "Camera Worker", f"Unhandled exception in Camera Worker:\n{tb}")
        except Exception:
            pass
        try:
            # Also print to stdout/stderr so parent process may capture it
            print(f"[Camera Worker] Unhandled exception:\n{tb}")
        except Exception:
            pass


def tracking_thread(translationQueue, translationDisplayQueue, stop_event, statusQueue=None, logQueue=None, cam_index=0, thresh_value=DEFAULT_DETECTION_THRESHOLD, preview_queue=None, control_queue=None):
    from util.log_utils import log_info, log_error

    provider = None
    want_preview = False
    tracking = False
    target_cam = int(cam_index)
    backend = 'pseyepy'

    sx = LowPass(LOWPASS_ALPHA, 0.0)
    sy = LowPass(LOWPASS_ALPHA, 0.0)

    frame_w, frame_h = DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT
    desired_fps = None
    # Movement scale used to map pixel deviation to physical range (default +/-30)
    movement_scale = 30.0
    # Preview throttling: allow preview to be sent at a lower FPS than camera capture
    PREVIEW_DISPLAY_FPS = 30.0
    _preview_interval = 1.0 / float(PREVIEW_DISPLAY_FPS) if PREVIEW_DISPLAY_FPS > 0 else 0.0
    _last_preview_ts = 0.0

    try:
        last_x = None
        last_y = None
        last_detection_time = None
        lost_state = False
        frames_count = 0
        last_fps_ts = time.time()
        # Origin handling: when tracking starts, treat first detected brightspot
        # as the origin (0,0,0) for subsequent translations so displays are relative.
        _origin_pending = False
        _origin_set = False
        _origin = (0.0, 0.0, 0.0)

        # Pub rate limiting for translationQueue to avoid flooding when downstream is slow
        _last_pub_ts = 0.0
        _last_pub_x = None
        _last_pub_y = None
        _pub_min_interval = 0.02  # seconds (50 Hz)

        while stop_event is None or not stop_event.is_set():
            if control_queue is not None:
                cmd = safe_queue_get(control_queue, timeout=0.0, default=None)
                while cmd is not None:
                    try:
                        log_info(logQueue, "Camera Worker", f"Control command received: {cmd}")
                    except Exception:
                        pass
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 1:
                        if cmd[0] == 'preview_on':
                            want_preview = True
                        elif cmd[0] == 'preview_off':
                            want_preview = False
                            # Don't close provider here - let the automatic cleanup handle it
                            # (only closes if both want_preview and tracking are False)
                        elif cmd[0] == 'start_pos':
                            tracking = True
                            # Inform downstream consumers that position tracking is enabled
                            try:
                                if translationQueue is not None:
                                    safe_queue_put(translationQueue, ('_POS_ENABLE_', True), timeout=QUEUE_PUT_TIMEOUT)
                            except Exception:
                                pass
                            # Request camera-local origin capture on next numeric translation
                            try:
                                _origin_pending = True
                                _origin_set = False
                            except Exception:
                                pass
                        elif cmd[0] == 'latch_origin':
                            # Explicit request to latch the next numeric translation as camera-local origin
                            try:
                                _origin_pending = True
                                _origin_set = False
                                try:
                                    log_info(logQueue, "Camera Worker", "Latch origin requested via control queue")
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        elif cmd[0] == 'stop_pos':
                            tracking = False
                            # Inform downstream consumers that position tracking is disabled
                            try:
                                if translationQueue is not None:
                                    safe_queue_put(translationQueue, ('_POS_ENABLE_', False), timeout=QUEUE_PUT_TIMEOUT)
                            except Exception:
                                pass
                            # Clear any camera-local origin baseline
                            try:
                                _origin_pending = False
                                _origin_set = False
                                _origin = (0.0, 0.0, 0.0)
                            except Exception:
                                pass
                        elif cmd[0] == 'set_thresh' and len(cmd) >= 2:
                            thresh_value = safe_float_convert(cmd[1], default=thresh_value, min_val=0.0, max_val=255.0)
                            thresh_value = int(thresh_value)
                        elif cmd[0] == 'set_cam_params' and len(cmd) >= 4:
                            desired_fps = safe_float_convert(cmd[1], default=None, min_val=1.0, max_val=240.0)
                            if desired_fps is not None:
                                desired_fps = int(desired_fps)
                            frame_w = safe_float_convert(cmd[2], default=frame_w, min_val=160.0, max_val=4096.0)
                            frame_w = int(frame_w)
                            frame_h = safe_float_convert(cmd[3], default=frame_h, min_val=120.0, max_val=4096.0)
                            frame_h = int(frame_h)
                            if provider is not None:
                                try:
                                    provider.set_params(frame_w, frame_h, desired_fps)
                                except Exception:
                                    try:
                                        provider.close()
                                    except Exception:
                                        pass
                                    provider = None
                        elif cmd[0] == 'set_cam' and len(cmd) >= 2:
                            try:
                                target_cam = int(cmd[1])
                                if provider is not None:
                                    try:
                                        provider.close()
                                    except Exception:
                                        pass
                                    provider = None
                            except (ValueError, TypeError):
                                pass
                        elif cmd[0] == 'set_exposure' and len(cmd) >= 2:
                            try:
                                ev = int(cmd[1])
                                if provider is not None and hasattr(provider, 'set_setting'):
                                    try:
                                        provider.set_setting('exposure', ev)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        elif cmd[0] == 'set_gain' and len(cmd) >= 2:
                            try:
                                gv = int(cmd[1])
                                if provider is not None and hasattr(provider, 'set_setting'):
                                    try:
                                        provider.set_setting('gain', gv)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        elif cmd[0] == 'close_cam':
                            # Explicit request to close/release the camera provider
                            try:
                                if provider is not None:
                                    try:
                                        provider.close()
                                    except Exception:
                                        pass
                                    provider = None
                                    try:
                                        log_info(logQueue, "Camera Worker", "Camera provider closed on request")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        elif cmd[0] == 'set_backend' and len(cmd) >= 2:
                            try:
                                val = str(cmd[1])
                                new_backend = 'pseyepy' if 'pseyepy' in val.lower() else 'pseyepy'
                                if new_backend != backend:
                                    backend = new_backend
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
                            except Exception:
                                pass
                        elif cmd[0] == 'calibrate':
                            pass
                        elif cmd[0] == 'set_scale' and len(cmd) >= 2:
                            try:
                                sv = safe_float_convert(cmd[1], default=movement_scale, min_val=-1000.0, max_val=1000.0)
                                movement_scale = float(sv)
                            except Exception:
                                pass
                        elif cmd[0] == 'set_cam_setting' and len(cmd) >= 3:
                            try:
                                name = str(cmd[1])
                                val = cmd[2]
                                if provider is not None and hasattr(provider, 'set_setting'):
                                    try:
                                        provider.set_setting(name, val)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    cmd = safe_queue_get(control_queue, timeout=0.0, default=None)

            if not want_preview and not tracking and provider is not None:
                try:
                    provider.close()
                except Exception:
                    pass
                provider = None
                try:
                    safe_queue_put(statusQueue, ('cam_fps', 0.0), timeout=QUEUE_PUT_TIMEOUT)
                except Exception:
                    pass

            if (want_preview or tracking) and provider is None:
                try:
                    log_info(logQueue, "Camera Worker", f"Opening camera {target_cam} at {frame_w}x{frame_h} using pseyepy")
                    try:
                        # Use new clean subprocess-based PSEyeProvider
                        from workers.pseyepy_prov import PSEyeProvider
                        provider = PSEyeProvider(target_cam, frame_w, frame_h, desired_fps, logQueue=logQueue)
                        if provider is None:
                            provider = None
                        else:
                            try:
                                pname = getattr(provider, '__class__', type(provider)).__name__
                                log_info(logQueue, 'Camera Worker', f'Provider created: {pname} (backend={backend})')
                            except Exception:
                                pass
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

            loop_start_time = time.time()

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

            if tracking:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = None

            proc = frame
            need_overlay_copy = False

            try:
                frames_count += 1
            except Exception:
                frames_count = 0

            blob = None
            if tracking:
                blob = _find_largest_blob(gray, thresh=thresh_value, min_area=MIN_BLOB_AREA)

            now = time.time()
            if blob is not None and tracking:
                cx, cy, area = blob
                x_delta_pixels = float(cx) - (frame_w / 2.0)
                y_delta_pixels = (frame_h / 2.0) - float(cy)

                # Map pixel deviation using configurable movement_scale
                x_raw = (x_delta_pixels / float(frame_w)) * movement_scale
                y_raw = (y_delta_pixels / float(frame_h)) * movement_scale

                vx = sx.update(x_raw)
                vy = sy.update(y_raw)

                raw_x = float(clamp(vx, POSITION_CLAMP_MIN, POSITION_CLAMP_MAX))
                raw_y = float(clamp(vy, POSITION_CLAMP_MIN, POSITION_CLAMP_MAX))
                raw_z = 0.0

                # If an origin capture was requested, latch this raw sample as origin
                if _origin_pending:
                    _origin = (raw_x, raw_y, raw_z)
                    _origin_set = True
                    _origin_pending = False
                    send_x, send_y, send_z = 0.0, 0.0, 0.0
                    try:
                        log_info(logQueue, "Camera Worker", f"Origin latched: {_origin} -> sending (0.0,0.0,0.0)")
                    except Exception:
                        pass
                    # Send explicit origin message so fusion can deterministically set its origin
                    try:
                        if translationQueue is not None:
                            try:
                                safe_queue_put(translationQueue, ('_CAM_ORIGIN_', float(_origin[0]), float(_origin[1]), float(_origin[2])), timeout=QUEUE_PUT_TIMEOUT)
                                try:
                                    log_info(logQueue, "Camera Worker", f"Sent explicit origin message: {_origin}")
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                elif _origin_set:
                    ox, oy, oz = _origin
                    send_x, send_y, send_z = raw_x - ox, raw_y - oy, raw_z - oz
                else:
                    send_x, send_y, send_z = raw_x, raw_y, raw_z

                tdata = [send_x, send_y, send_z]
                last_x = float(send_x)
                last_y = float(send_y)
                last_detection_time = now
                if lost_state:
                    lost_state = False
                    safe_queue_put(translationDisplayQueue, ('_CAM_STATUS_', 'restored'), timeout=QUEUE_PUT_TIMEOUT)
                    try:
                        print('[Camera Worker] Marker restored')
                    except Exception:
                        pass

                # Publish to fusion (translationQueue) — best-effort, non-blocking
                try:
                    now_pub = time.time()
                    publish = False
                    if _last_pub_x is None or _last_pub_y is None:
                        publish = True
                    elif abs(send_x - _last_pub_x) > 0.01 or abs(send_y - _last_pub_y) > 0.01:
                        publish = True
                    elif (now_pub - _last_pub_ts) >= _pub_min_interval:
                        publish = True

                    if publish:
                        try:
                            success = safe_queue_put(translationQueue, tdata, timeout=0.0)
                        except Exception:
                            success = False
                        if success:
                            _last_pub_ts = now_pub
                            _last_pub_x = float(send_x)
                            _last_pub_y = float(send_y)
                        else:
                            try:
                                log_info(logQueue, "Camera Worker", f"Failed to publish translation (queue full?): {tdata}")
                            except Exception:
                                pass
                except Exception:
                    pass

                # Publish a single combined display message for the GUI to avoid multiple
                # queue entries per frame which can overwhelm the display queue.
                display_item = ('_CAM_DATA_', float(send_x), float(send_y), float(send_z), int(cx), int(cy))
                try:
                    # Use non-blocking put; if display queue is full, drop the display item
                    safe_queue_put(translationDisplayQueue, display_item, timeout=0.0)
                except Exception:
                    pass

                if want_preview:
                    if not need_overlay_copy:
                        proc = frame.copy()
                        need_overlay_copy = True
                    cv2.circle(proc, (int(cx), int(cy)), 6, (0,255,0), 2)
                    try:
                        cv2.putText(proc, f"X:{send_x:.2f} Y:{send_y:.2f}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
                    except Exception:
                        # Fallback to raw values if send_* not available
                        try:
                            cv2.putText(proc, f"X:{raw_x:.2f} Y:{raw_y:.2f}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
                        except Exception:
                            pass
            elif tracking:
                if last_x is not None and last_y is not None:
                    if last_detection_time is not None and (now - last_detection_time) <= STALE_DETECTION_TIMEOUT:
                        tdata = [float(last_x), float(last_y), 0.0]
                        safe_queue_put(translationQueue, tdata, timeout=0)
                        safe_queue_put(translationDisplayQueue, tdata, timeout=0)
                    else:
                        if not lost_state:
                            lost_state = True
                            safe_queue_put(translationDisplayQueue, ('_CAM_STATUS_', 'lost'), timeout=QUEUE_PUT_TIMEOUT)
                            try:
                                print('[Camera Worker] Marker lost (stale)')
                            except Exception:
                                pass

            if want_preview and preview_queue is not None:
                try:
                    now = time.time()
                    if _preview_interval <= 0.0 or (now - _last_preview_ts) >= _preview_interval:
                        # It's time to produce a preview frame
                        disp = cv2.resize(proc, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
                        ret2, buf = cv2.imencode('.jpg', disp, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                        if ret2:
                            jpg_bytes = buf.tobytes()
                            # Avoid blocking if preview queue is nearly full: drop frames instead
                            try:
                                qsize = preview_queue.qsize()
                            except Exception:
                                qsize = None
                            try:
                                if qsize is None or qsize < max(1, int(QUEUE_SIZE_DISPLAY * 0.9)):
                                    safe_queue_put(preview_queue, (jpg_bytes, now), timeout=0.0)
                                    _last_preview_ts = now
                                else:
                                    try:
                                        log_info(logQueue, 'Camera Worker', 'Dropping preview frame (queue near full)')
                                    except Exception:
                                        pass
                            except Exception:
                                # Final fallback: non-blocking put
                                try:
                                    preview_queue.put_nowait((jpg_bytes, now))
                                    _last_preview_ts = now
                                except Exception:
                                    pass
                except Exception:
                    pass

            try:
                now_fps = time.time()
                if (now_fps - last_fps_ts) >= FPS_REPORT_INTERVAL:
                    elapsed = now_fps - last_fps_ts
                    fps = float(frames_count) / elapsed if elapsed > 0 else 0.0
                    frames_count = 0
                    last_fps_ts = now_fps
                    safe_queue_put(statusQueue, ('cam_fps', fps), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

            try:
                loop_elapsed = time.time() - loop_start_time
                if desired_fps is not None and desired_fps > 0:
                    target_interval = 1.0 / float(desired_fps)
                    delay = target_interval - loop_elapsed
                    if delay > 0:
                        time.sleep(delay)
                else:
                    if loop_elapsed < 0.001:
                        time.sleep(0.001)
            except Exception:
                try:
                    time.sleep(0.001)
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
