# process_man.py
"""Process manager: create and manage worker processes and inter-process queues.

This module exposes `ProcessHandler`, a convenience class that initializes
the multiprocessing queues, starts worker processes (GUI, Serial, Fusion,
UDP, Camera), and provides a safe shutdown path. The manager also runs a
background log writer thread that drains `logQueue` and writes messages to
`LOG_FILE_NAME`.

The implementation focuses on robustness: queues have limited size, workers
are started as separate processes, and `stop_workers()` uses a shutdown
lock to avoid race conditions from repeated signals.
"""

from multiprocessing import Process, Queue, Event
import signal
import sys
import time
import threading
import os

# Import config constants
from config import config
from config.config import (
    QUEUE_SIZE_DATA,
    QUEUE_SIZE_DISPLAY,
    QUEUE_SIZE_CONTROL,
    QUEUE_SIZE_PREVIEW,
    LOG_FILE_NAME,
    LOG_FILE_MAX_SIZE,
    WORKER_JOIN_TIMEOUT
)

class ProcessHandler:
    """Manager for application worker processes and shared queues.

    Responsibilities:
    - Create and own all multiprocessing queues and the global stop event.
    - Start worker processes with the correct queue bindings.
    - Provide `stop_workers()` that signals shutdown and cleans up processes.
    - Run a background log writer thread that persists log entries to disk.
    """

    def __init__(self):
        ## Init Queues (use config constants)
        self.serialQueue = Queue(maxsize=QUEUE_SIZE_DATA)
        self.eulerQueue = Queue(maxsize=QUEUE_SIZE_DATA)
        self.translationQueue = Queue(maxsize=QUEUE_SIZE_DATA)
        
        self.serialDisplayQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        self.eulerDisplayQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        self.translationDisplayQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        # Camera control + preview queues
        self.cameraControlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.cameraPreviewQueue = Queue(maxsize=QUEUE_SIZE_PREVIEW)
        self.udpControlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        
        self.messageQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        self.controlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.serialControlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.statusQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        self.uiStatusQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)  # Dedicated UI status queue
        self.logQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        ## Init stop event
        self.stop_event = Event()
        
        ## Workers
        self.workers = []
        
        ## Signal Handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        ## Start log writer thread
        self.log_thread = threading.Thread(target=self._log_writer, daemon=True)
        self.log_thread.start()
        
        # Shutdown lock to prevent race conditions when stopping workers
        # (e.g., signal handler vs. explicit shutdown)
        self._shutdown_lock = threading.Lock()
        self._stopping = False
    
    def _log_writer(self):
        """Background thread that writes log messages from `logQueue` to file.

        This thread runs in the main process (not a worker) and listens for
        tuples of the form `(level, worker_name, message)` put into
        `self.logQueue`. Entries are timestamped and appended to `LOG_FILE_NAME`.

        The writer attempts a simple log rotation based on `LOG_FILE_MAX_SIZE`.
        It is robust to transient IO errors and will silently drop malformed
        entries to avoid crashing the manager during shutdown.
        """
        from datetime import datetime
        from queue import Empty
        
        log_file = LOG_FILE_NAME  # Use constant from config
        
        # Rotate log if it gets too large
        try:
            if os.path.exists(log_file) and os.path.getsize(log_file) > LOG_FILE_MAX_SIZE:
                backup = f"frankentrack_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                os.rename(log_file, backup)
        except Exception:
            pass
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                while not self.stop_event.is_set():
                    try:
                        # Log format: (level, worker_name, message)
                        log_entry = self.logQueue.get(timeout=0.5)
                        
                        if isinstance(log_entry, tuple) and len(log_entry) >= 3:
                            level, worker, msg = log_entry[0], log_entry[1], log_entry[2]
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            line = f"[{timestamp}] [{level:5s}] [{worker:15s}] {msg}\n"
                            f.write(line)
                            f.flush()
                        
                    except Empty:
                        pass
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ProcessHandler] Log writer error: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle OS termination signals (SIGINT, SIGTERM).

        This handler delegates to `stop_workers()` to perform an orderly
        shutdown and then exits the process. The actual shutdown sequence is
        guarded by a lock to avoid concurrent invocations from repeated
        signals.
        """
        print("\n[ProcessHandler] Shutdown signal received, stopping workers...")
        # Let stop_workers handle re-entrancy via the shutdown lock
        try:
            self.stop_workers()
        except Exception:
            # Ensure we still exit even if shutdown encountered issues
            pass
        sys.exit(0)
    
    def start_workers(self):
        """Create and start all application worker processes.

        Each worker is started as a separate `multiprocessing.Process` with
        queues wired according to the system architecture. This method should
        be called once from the main entrypoint. It intentionally imports
        worker modules here to avoid circular import problems at module
        import time.
        """
        print("[ProcessHandler] Starting workers...")
        
        ## Import worker target here to avoid circular import
        from workers.gui_wrk_launcher import run_worker as run_gui_worker
        from workers.serial_wrk import run_worker as run_serial_worker
        from workers.fusion_wrk import run_worker as run_fusion_worker
        from workers.udp_wrk import run_worker as run_udp_worker
        from workers.camera_wrk import run_worker as run_camera_worker

        ## GUI Worker
        gui_worker = Process(
            target = run_gui_worker,
            args = (self.messageQueue, self.serialDisplayQueue, self.statusQueue, 
                   self.stop_event, self.eulerDisplayQueue, self.controlQueue, 
                   self.serialControlQueue, self.translationDisplayQueue, 
                   self.cameraControlQueue, self.cameraPreviewQueue, 
                   self.udpControlQueue, self.logQueue, self.uiStatusQueue),
            name = "GUIWorker"
        )
        gui_worker.start()
        self.workers.append(gui_worker)
        
        ## Serial Worker
        serial_worker = Process(
            target = run_serial_worker,
            args = (self.messageQueue, self.serialQueue, self.serialDisplayQueue, 
                   self.stop_event, self.serialControlQueue, self.statusQueue, 
                   self.logQueue, self.uiStatusQueue), 
            name = "SerialWorker"
        )
        serial_worker.start()
        self.workers.append(serial_worker)
        
        ## Sensor Fusion Worker
        fusion_worker = Process(
            target = run_fusion_worker,
            args = (self.serialQueue, self.eulerQueue, self.eulerDisplayQueue, 
                   self.controlQueue, self.statusQueue, self.stop_event, 
                   self.logQueue, self.uiStatusQueue),
            name = "FusionWorker"
        )
        fusion_worker.start()
        self.workers.append(fusion_worker)

        ## UDP Worker
        udp_worker = Process(
            target = run_udp_worker,
            args = (self.eulerQueue, self.translationQueue, self.stop_event, 
                   None, None, self.udpControlQueue, self.statusQueue, 
                   self.logQueue),
            name = "UDPWorker"
        )
        udp_worker.start()
        self.workers.append(udp_worker)

        ## Camera Worker
        camera_worker = Process(
            target = run_camera_worker,
            args = (self.translationQueue, self.translationDisplayQueue, 
                   self.cameraControlQueue, self.stop_event, 
                   self.cameraPreviewQueue, self.statusQueue, self.logQueue),
            name = "CameraWorker"
        )
        camera_worker.start()
        self.workers.append(camera_worker)
        # Print process details for debugging worker startup
        try:
            print(f"[ProcessHandler] Started CameraWorker pid={camera_worker.pid} alive={camera_worker.is_alive()}")
        except Exception:
            pass

        print("[ProcessHandler] All workers started.")
        
    def stop_workers(self):
        """Stop and cleanup all worker processes.

        The shutdown flow is:
        - Acquire shutdown lock to prevent re-entrancy.
        - Set the global `stop_event` so workers can exit cleanly.
        - Allow a brief grace period for processes to exit.
        - Force-terminate remaining alive processes and join them with a
          timeout (`WORKER_JOIN_TIMEOUT`).

        This method is safe to call multiple times; concurrent calls will be
        ignored while a shutdown is in progress.
        """
        # Prevent concurrent shutdown attempts
        acquired = self._shutdown_lock.acquire(blocking=False)
        if not acquired:
            print("[ProcessHandler] stop_workers already in progress, skipping duplicate call.")
            return

        try:
            if self._stopping:
                print("[ProcessHandler] stop already in progress, skipping.")
                return

            self._stopping = True
            print("[ProcessHandler] Stopping workers...")

            # Signal workers to stop
            self.stop_event.set()
            time.sleep(0.5)

            # Terminate any remaining alive processes
            for worker in self.workers:
                try:
                    if worker.is_alive():
                        worker.terminate()
                except Exception:
                    pass

            # Join with timeout and force-kill if necessary
            for worker in self.workers:
                try:
                    worker.join(timeout=WORKER_JOIN_TIMEOUT)  # Use constant
                    if worker.is_alive():
                        print(f"[ProcessHandler] Warning: Worker {worker.name} did not terminate in time.")
                        try:
                            worker.kill()
                        except Exception:
                            pass
                except Exception:
                    pass

            print("[ProcessHandler] All workers stopped.")
        finally:
            self._stopping = False
            try:
                self._shutdown_lock.release()
            except RuntimeError:
                # lock wasn't acquired or already released
                pass