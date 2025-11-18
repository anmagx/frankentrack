import serial
import time
import sys
from serial import SerialException
from queue import Empty

from config.config import (
    DEFAULT_SERIAL_BAUD,
    SERIAL_RETRY_DELAY,
    SERIAL_TIMEOUT,
    FPS_REPORT_INTERVAL,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put, safe_queue_get

def open_serial(port, baud, retry_delay, messageQueue, stop_event=None, serialControlQueue=None):
    """Try to open serial port repeatedly until successful.

    This version listens to `serialControlQueue` and `stop_event` so a GUI stop
    request can cancel the open attempt.
    Returns an open Serial instance or `None` if cancelled.
    """
    # Print a short waiting message
    msg = f"Waiting for device on {port}... (retrying in {retry_delay}s)"
    safe_queue_put(messageQueue, msg, timeout=QUEUE_PUT_TIMEOUT)

    while True:
        # allow external cancel via stop_event or serialControlQueue
        if stop_event is not None:
            try:
                if hasattr(stop_event, 'is_set') and stop_event.is_set():
                    return None
            except Exception:
                pass

        # check for immediate control commands
        cmd = safe_queue_get(serialControlQueue, timeout=0.0, default=None)
        if cmd is not None and isinstance(cmd, (list, tuple)):
            if cmd[0] == 'stop':
                return None
            if cmd[0] == 'start' and len(cmd) >= 3:
                # new start request with possibly different port/baud
                port = cmd[1]
                try:
                    baud = int(cmd[2])
                except Exception:
                    pass

        try:
            ser = serial.Serial(port, baud, timeout=SERIAL_TIMEOUT)
            safe_queue_put(messageQueue, f"Connected to {port} at {baud} baud.", 
                         timeout=QUEUE_PUT_TIMEOUT)
            return ser
        except SerialException:
            time.sleep(retry_delay)

def serial_thread(messageQueue=None, serialQueue=None, serialDisplayQueue=None, stop_event=None, serialControlQueue=None, statusQueue=None, logQueue=None):
    """Main serial thread controlled by commands from `serialControlQueue`.

    Commands expected on serialControlQueue:
      ('start', port, baud)  -> open and begin reading
      ('stop',)              -> close port and stop reading

    This thread will not block forever trying to open a port; open attempts
    can be cancelled via the control queue.
    """
    from util.log_utils import log_info, log_error
    
    log_info(logQueue, "Serial Worker", "Serial thread started")
    
    ser = None
    # Track messages per second (MPS)
    mps_count = 0
    last_mps_time = time.time()
    report_interval = FPS_REPORT_INTERVAL  # seconds

    while stop_event is None or not stop_event.is_set():
        # Process control commands first (drain queue)
        while True:
            cmd = safe_queue_get(serialControlQueue, timeout=0.0, default=None)
            if cmd is None:
                break
            
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 1:
                if cmd[0] == 'start' and len(cmd) >= 3:
                    port = cmd[1]
                    try:
                        baud = int(cmd[2])
                    except Exception:
                        baud = DEFAULT_SERIAL_BAUD
                    log_info(logQueue, "Serial Worker", f"Attempting connection to {port} at {baud} baud")
                    # attempt to open (blocking retry loop, but cancellable)
                    ser = open_serial(port, baud, SERIAL_RETRY_DELAY, messageQueue, stop_event, serialControlQueue)
                    if ser is not None:
                        log_info(logQueue, "Serial Worker", f"Connected to {port}")
                    # reset counters on start
                    mps_count = 0
                    last_mps_time = time.time()
                elif cmd[0] == 'stop':
                    if ser is not None:
                        log_info(logQueue, "Serial Worker", "Stopping serial connection")
                        try:
                            ser.close()
                        except Exception:
                            pass
                        ser = None
                        safe_queue_put(messageQueue, f"\nSerial on {port} stopped.", 
                                     timeout=QUEUE_PUT_TIMEOUT)

        if ser is None:
            # nothing to read right now
            try:
                time.sleep(0.05)
            except KeyboardInterrupt:
                break
            continue

        try:
            if ser.in_waiting:
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                if data:
                    # forward serial payload
                    safe_queue_put(serialQueue, data, timeout=QUEUE_PUT_TIMEOUT)
                    safe_queue_put(serialDisplayQueue, data, timeout=QUEUE_PUT_TIMEOUT)
                    # count for MPS
                    mps_count += 1
                    now = time.time()
                    elapsed = now - last_mps_time
                    if elapsed >= report_interval:
                        mps = mps_count / elapsed if elapsed > 0 else 0.0
                        # send MPS status to UI via statusQueue
                        safe_queue_put(statusQueue, ('msg_rate', mps), timeout=QUEUE_PUT_TIMEOUT)
                        # reset counters
                        mps_count = 0
                        last_mps_time = now
            else:
                # small sleep to avoid busy loop when no data
                try:
                    time.sleep(0.01)
                except KeyboardInterrupt:
                    break
        except KeyboardInterrupt:
            break
        except SerialException as e:
            # Connection lost: try to close and reconnect
            log_error(logQueue, "Serial Worker", f"Serial connection lost: {e}")
            port_name = ser.port if hasattr(ser, 'port') else 'unknown'
            safe_queue_put(messageQueue, f"\nConnection lost. Reconnecting to {port_name}...", 
                         timeout=QUEUE_PUT_TIMEOUT)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            # continue loop; open must be triggered by control queue
    
    log_info(logQueue, "Serial Worker", "Serial thread stopped")

def run_worker(messageQueue, serialQueue, serialDisplayQueue, stop_event=None, serialControlQueue=None, statusQueue=None, logQueue=None):
    from util.log_utils import log_info
    try:
        serial_thread(messageQueue, serialQueue, serialDisplayQueue, stop_event, serialControlQueue, statusQueue, logQueue)
    except KeyboardInterrupt:
        log_info(logQueue, "Serial Worker", "Serial worker interrupted during shutdown")
    finally:
        log_info(logQueue, "Serial Worker", "Serial worker stopped")
        print("[Serial Worker] Stopped.")
