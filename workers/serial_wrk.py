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

def open_serial(port, baud, retry_delay, messageQueue, stop_event=None, serialControlQueue=None, statusQueue=None, uiStatusQueue=None):
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
            # Notify GUI of successful connection
            if statusQueue:
                safe_queue_put(statusQueue, ('serial_connection', 'connected'), timeout=QUEUE_PUT_TIMEOUT)
            if uiStatusQueue:
                safe_queue_put(uiStatusQueue, ('serial_connection', 'connected'), timeout=QUEUE_PUT_TIMEOUT)
            return ser
        except SerialException as e:
            # Notify GUI of connection error on each retry
            if statusQueue:
                safe_queue_put(statusQueue, ('serial_connection', 'error'), timeout=QUEUE_PUT_TIMEOUT)
            if uiStatusQueue:
                safe_queue_put(uiStatusQueue, ('serial_connection', 'error'), timeout=QUEUE_PUT_TIMEOUT)
            time.sleep(retry_delay)

def serial_thread(messageQueue=None, serialQueue=None, serialDisplayQueue=None, stop_event=None, serialControlQueue=None, statusQueue=None, logQueue=None, uiStatusQueue=None):
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
    
    # Track activity to avoid spamming statusQueue
    last_activity_report = 0
    activity_report_interval = 2.0  # Only report activity every 2 seconds

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
                    ser = open_serial(port, baud, SERIAL_RETRY_DELAY, messageQueue, stop_event, serialControlQueue, statusQueue, uiStatusQueue)
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
                        # Notify GUI of serial stop/disconnection
                        if statusQueue:
                            safe_queue_put(statusQueue, ('serial_connection', 'stopped'), timeout=QUEUE_PUT_TIMEOUT)
                        if uiStatusQueue:
                            safe_queue_put(uiStatusQueue, ('serial_connection', 'stopped'), timeout=QUEUE_PUT_TIMEOUT)

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
                    # forward serial payload with queue monitoring
                    if not safe_queue_put(serialQueue, data, timeout=QUEUE_PUT_TIMEOUT, 
                                         log_failures=True, context="Serial data", queue_name="serialQueue"):
                        # Track drops for diagnostics
                        drop_count = getattr(ser, '_drop_count', 0) + 1
                        setattr(ser, '_drop_count', drop_count)
                        if drop_count % 50 == 0:  # Log every 50 drops
                            log_error(logQueue, "Serial Worker", f"Dropped {drop_count} frames due to full serialQueue")
                    
                    safe_queue_put(serialDisplayQueue, data, timeout=QUEUE_PUT_TIMEOUT, 
                                  queue_name="serialDisplayQueue")
                    
                    # Throttle data activity notifications to avoid flooding statusQueue
                    now = time.time()
                    if now - last_activity_report >= activity_report_interval:
                        if statusQueue:
                            safe_queue_put(statusQueue, ('serial_data', True), timeout=QUEUE_PUT_TIMEOUT)
                        if uiStatusQueue:
                            safe_queue_put(uiStatusQueue, ('serial_data', True), timeout=QUEUE_PUT_TIMEOUT)
                        last_activity_report = now
                        
                    # count for MPS
                    mps_count += 1
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
            # Notify GUI of connection error
            if statusQueue:
                safe_queue_put(statusQueue, ('serial_connection', 'error'), timeout=QUEUE_PUT_TIMEOUT)
            if uiStatusQueue:
                safe_queue_put(uiStatusQueue, ('serial_connection', 'error'), timeout=QUEUE_PUT_TIMEOUT)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            # continue loop; open must be triggered by control queue
    
    log_info(logQueue, "Serial Worker", "Serial thread stopped")

def run_worker(messageQueue, serialQueue, serialDisplayQueue, stop_event=None, serialControlQueue=None, statusQueue=None, logQueue=None, uiStatusQueue=None):
    from util.log_utils import log_info
    try:
        serial_thread(messageQueue, serialQueue, serialDisplayQueue, stop_event, serialControlQueue, statusQueue, logQueue, uiStatusQueue)
    except KeyboardInterrupt:
        log_info(logQueue, "Serial Worker", "Serial worker interrupted during shutdown")
    finally:
        log_info(logQueue, "Serial Worker", "Serial worker stopped")
        print("[Serial Worker] Stopped.")
