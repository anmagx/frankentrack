# process_man.py
from multiprocessing import Process, Queue, Event
import signal
import sys
import time
import threading
import os

# Import config constants
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
    
    def _log_writer(self):
        """Background thread that writes log messages to file."""
        from datetime import datetime
        from queue import Empty
        
        log_file = LOG_FILE_NAME  # Use constant from config
        
        # Rotate log if it gets too large
        try:
            if os.path.exists(log_file) and os.path.getsize(log_file) > LOG_FILE_MAX_SIZE:
                backup = f"acceltrack_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
        """Handle Ctrl+C and termination signals"""
        print("\n[ProcessHandler] Shutdown signal received, stopping workers...")
        self.stop_workers()
        sys.exit(0)
    
    def start_workers(self):
        print("[ProcessHandler] Starting workers...")
        
        ## Import worker target here to avoid circular import
        from workers.gui_wrk import run_worker as run_gui_worker
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
                   self.udpControlQueue, self.logQueue),
            name = "GUIWorker"
        )
        gui_worker.start()
        self.workers.append(gui_worker)
        
        ## Serial Worker
        serial_worker = Process(
            target = run_serial_worker,
            args = (self.messageQueue, self.serialQueue, self.serialDisplayQueue, 
                   self.stop_event, self.serialControlQueue, self.statusQueue, 
                   self.logQueue),
            name = "SerialWorker"
        )
        serial_worker.start()
        self.workers.append(serial_worker)
        
        ## Sensor Fusion Worker
        fusion_worker = Process(
            target = run_fusion_worker,
            args = (self.serialQueue, self.eulerQueue, self.eulerDisplayQueue, 
                   self.controlQueue, self.statusQueue, self.stop_event, 
                   self.logQueue),
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

        print("[ProcessHandler] All workers started.")
        
    def stop_workers(self):
        """Stop all worker processes"""
        print("[ProcessHandler] Stopping workers...")
        
        self.stop_event.set()
        time.sleep(0.5)     
        
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                
        for worker in self.workers:
            worker.join(timeout=WORKER_JOIN_TIMEOUT)  # Use constant
            if worker.is_alive():
                print(f"[ProcessHandler] Warning: Worker {worker.name} did not terminate in time.")
                worker.kill()
        
        print("[ProcessHandler] All workers stopped.")