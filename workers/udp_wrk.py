import socket
import struct
import time
from queue import Empty

from config.config import (
    DEFAULT_UDP_IP,
    DEFAULT_UDP_PORT,
    STALE_DETECTION_TIMEOUT,
    FPS_REPORT_INTERVAL,
    QUEUE_PUT_TIMEOUT,
    QUEUE_GET_TIMEOUT
)
from util.error_utils import safe_queue_put, safe_queue_get


def run_worker(eulerQueue, translationQueue, stop_event, udp_ip=None, udp_port=None, controlQueue=None, statusQueue=None, logQueue=None):
    """Read Euler data from eulerQueue and send to OpenTrack over UDP.

    eulerQueue is expected to provide an iterable/sequence: [Yaw, Pitch, Roll, X, Y, Z]
    OpenTrack expects translation-first ordering (TX,TY,TZ, RX,RY,RZ) packed as 6 doubles
    using little-endian '<6d'.
    """
    from util.log_utils import log_info, log_error
    
    # Use config defaults if not provided
    if udp_ip is None:
        udp_ip = DEFAULT_UDP_IP
    if udp_port is None:
        udp_port = DEFAULT_UDP_PORT
    
    log_info(logQueue, "UDP Worker", f"Starting UDP sender to {udp_ip}:{udp_port}")
    print(f"[UDP Worker] Starting. Sending to {udp_ip}:{udp_port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Keep last-seen translation so brief queue gaps don't produce zeros.
        last_translation = (0.0, 0.0, 0.0)
        last_translation_time = 0.0
        # Use stale timeout from config
        local_stale = STALE_DETECTION_TIMEOUT
        # UDP enabled flag (can be toggled at runtime via controlQueue)
        udp_enabled = False
        # lightweight send-rate tracking
        send_count = 0
        last_rate_ts = time.time()
        rate_report_interval = FPS_REPORT_INTERVAL

        while not stop_event.is_set():
            # Process any control commands (drain queue)
            while True:
                cmd = safe_queue_get(controlQueue, timeout=0.0, default=None)
                if cmd is None:
                    break
                
                try:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 1:
                        if cmd[0] == 'set_udp' and len(cmd) >= 3:
                            try:
                                udp_ip = str(cmd[1])
                                udp_port = int(cmd[2])
                                log_info(logQueue, "UDP Worker", f"UDP target updated to {udp_ip}:{udp_port}")
                            except Exception:
                                pass
                        elif cmd[0] == 'udp_enable' and len(cmd) >= 2:
                            try:
                                udp_enabled = bool(cmd[1])
                                status = "enabled" if udp_enabled else "disabled"
                                log_info(logQueue, "UDP Worker", f"UDP sending {status}")
                            except Exception:
                                pass
                        # ignore other commands
                except Exception:
                    pass
            sendData = safe_queue_get(eulerQueue, timeout=QUEUE_GET_TIMEOUT, default=None)
            if sendData is None:
                # no data available, loop and check stop_event
                continue

            try:
                # sendData expected at least [Yaw, Pitch, Roll, ...]
                yaw, pitch, roll = float(sendData[0]), float(sendData[1]), float(sendData[2])

                # Try to get latest translation from translationQueue (non-blocking).
                # Drain any queued translations and keep the newest sample. If none
                # are currently available, reuse the last_translation until it
                # becomes stale (STALE_DETECTION_TIMEOUT). This avoids flip-flopping to zeros
                # during brief queue scheduling races.
                tx, ty, tz = last_translation
                try:
                    latest = None
                    while True:
                        t = safe_queue_get(translationQueue, timeout=0.0, default=None)
                        if t is None:
                            break
                        latest = t
                    
                    if latest is not None and len(latest) >= 3:
                        # update last-seen translation and timestamp
                        tx, ty, tz = float(latest[0]), float(latest[1]), float(latest[2])
                        last_translation = (tx, ty, tz)
                        last_translation_time = time.time()
                    else:
                        # if we have a last_translation but it's stale, fall back to zeros
                        if last_translation_time and (time.time() - last_translation_time) > local_stale:
                            tx = ty = tz = 0.0
                            last_translation = (0.0, 0.0, 0.0)
                except Exception:
                    # on any error keep previous last_translation values
                    pass

                # Reorder to translation-first (TX,TY,TZ, RX,RY,RZ)
                out = (tx, ty, tz, yaw, pitch, roll)
                # Debug: print values being sent (can be noisy)
                if udp_enabled:
                    try:
                        packed = struct.pack('<6d', *out)
                        sock.sendto(packed, (udp_ip, udp_port))
                        sent = True
                    except Exception:
                        sent = False
                else:
                    sent = False
                # increment send counter and report periodically
                try:
                    if sent:
                        send_count += 1
                    nowr = time.time()
                    elapsed = nowr - last_rate_ts
                    if elapsed >= rate_report_interval:
                        rate = float(send_count) / elapsed if elapsed > 0 else float(send_count)
                        send_count = 0
                        last_rate_ts = nowr
                        safe_queue_put(statusQueue, ('send_rate', rate), timeout=QUEUE_PUT_TIMEOUT)
                except Exception:
                    # ensure UDP sending is not impacted by reporting errors
                    pass
                # tiny throttle to avoid busy-looping if messages pile up
                time.sleep(0)
            except Exception as e:
                log_error(logQueue, "UDP Worker", f"Pack/send error: {e}")
                print(f"[UDP Worker] pack/send error: {e}")

    except KeyboardInterrupt:
        # allow clean shutdown on Ctrl+C
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
        log_info(logQueue, "UDP Worker", "Stopped")
        print("[UDP Worker] Stopped.")
