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
    LOG_FILE_NAME,
    LOG_FILE_MAX_SIZE,
    WORKER_JOIN_TIMEOUT,
    WORKER_RESTART_DELAY,
    MAX_WORKER_RESTART_ATTEMPTS
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
        
        self.serialDisplayQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        self.eulerDisplayQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        self.udpControlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        
        self.messageQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        self.controlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.serialControlQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.statusQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        self.uiStatusQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)  # Dedicated UI status queue
        self.logQueue = Queue(maxsize=QUEUE_SIZE_DISPLAY)
        
        # Input worker queues
        self.inputCommandQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        self.inputResponseQueue = Queue(maxsize=QUEUE_SIZE_CONTROL)
        
        ## Init stop event
        self.stop_event = Event()
        
        ## Workers
        self.workers = []
        
        # Worker monitoring and restart capabilities
        self._worker_restart_counts = {}  # Track restart attempts per worker
        self._worker_configs = {}  # Store worker configuration for restarts
        self._monitor_thread = None
        self._monitoring_active = False
        
        ## Signal Handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        ## Start log writer thread
        self.log_thread = threading.Thread(target=self._log_writer, daemon=True)
        self.log_thread.start()
        
        # Start worker monitoring thread for automatic restart
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._worker_monitor, daemon=True)
        self._monitor_thread.start()
        
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
    
    def _worker_monitor(self):
        """Background thread that monitors worker processes and restarts them if they crash.
        
        This provides automatic recovery from worker failures without requiring
        manual intervention. Workers that exceed MAX_WORKER_RESTART_ATTEMPTS
        are not restarted to prevent infinite restart loops.
        """
        queue_health_counter = 0
        while self._monitoring_active and not self.stop_event.is_set():
            try:
                # Check all workers periodically
                time.sleep(1.0)  # Check every second
                
                if self._stopping:
                    break
                
                # Check queue health every 10 seconds
                queue_health_counter += 1
                if queue_health_counter >= 10:
                    self.log_queue_health()
                    queue_health_counter = 0
                
                # Check worker health
                dead_workers = []
                for i, worker in enumerate(self.workers):
                    if not worker.is_alive():
                        dead_workers.append((i, worker))
                
                # Restart dead workers if restart limit not exceeded
                for worker_idx, dead_worker in dead_workers:
                    worker_name = dead_worker.name
                    restart_count = self._worker_restart_counts.get(worker_name, 0)
                    
                    if restart_count < MAX_WORKER_RESTART_ATTEMPTS:
                        try:
                            print(f"[ProcessHandler] Worker {worker_name} crashed, restarting (attempt {restart_count + 1})...")
                            
                            # Get worker configuration for restart
                            if worker_name in self._worker_configs:
                                config = self._worker_configs[worker_name]
                                
                                # Wait before restart to prevent rapid restart loops
                                time.sleep(WORKER_RESTART_DELAY)
                                
                                # Create new worker process
                                new_worker = Process(
                                    target=config['target'],
                                    args=config['args'],
                                    name=config['name']
                                )
                                new_worker.start()
                                
                                # Replace dead worker in list
                                self.workers[worker_idx] = new_worker
                                
                                # Update restart count
                                self._worker_restart_counts[worker_name] = restart_count + 1
                                
                                print(f"[ProcessHandler] Worker {worker_name} restarted successfully")
                            
                        except Exception as e:
                            print(f"[ProcessHandler] Failed to restart worker {worker_name}: {e}")
                    else:
                        print(f"[ProcessHandler] Worker {worker_name} exceeded restart limit ({MAX_WORKER_RESTART_ATTEMPTS}), not restarting")
                
            except Exception as e:
                print(f"[ProcessHandler] Worker monitor error: {e}")
                # Continue monitoring despite errors
                time.sleep(5.0)
    
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
        from workers.gui_wrk import run_worker as run_gui_worker
        from workers.serial_wrk import run_worker as run_serial_worker
        from workers.fusion_wrk import run_worker as run_fusion_worker
        from workers.udp_wrk import run_worker as run_udp_worker
        from workers.input_wrk import run_worker as run_input_worker

        ## Input Worker (start first to handle shortcuts early)
        input_args = (self.inputCommandQueue, self.inputResponseQueue, self.stop_event, self.logQueue)
        input_worker = Process(
            target = run_input_worker,
            args = input_args,
            name = "InputWorker"
        )
        input_worker.start()
        self.workers.append(input_worker)
        
        # Store configuration for restart capability
        self._worker_configs["InputWorker"] = {
            'target': run_input_worker,
            'args': input_args,
            'name': "InputWorker"
        }

        ## GUI Worker
        gui_args = (self.messageQueue, self.serialDisplayQueue, self.statusQueue, 
                   self.stop_event, self.eulerDisplayQueue, self.controlQueue, 
                   self.serialControlQueue, 
                   self.udpControlQueue, self.logQueue, self.uiStatusQueue,
                   self.inputCommandQueue, self.inputResponseQueue)
        gui_worker = Process(
            target = run_gui_worker,
            args = gui_args,
            name = "GUIWorker"
        )
        gui_worker.start()
        self.workers.append(gui_worker)
        
        # Store configuration for restart capability
        self._worker_configs["GUIWorker"] = {
            'target': run_gui_worker,
            'args': gui_args,
            'name': "GUIWorker"
        }
        
        ## Serial Worker
        serial_args = (self.messageQueue, self.serialQueue, self.serialDisplayQueue, 
                   self.stop_event, self.serialControlQueue, self.statusQueue, 
                   self.logQueue, self.uiStatusQueue)
        serial_worker = Process(
            target = run_serial_worker,
            args = serial_args,
            name = "SerialWorker"
        )
        serial_worker.start()
        self.workers.append(serial_worker)
        
        # Store configuration for restart capability
        self._worker_configs["SerialWorker"] = {
            'target': run_serial_worker,
            'args': serial_args,
            'name': "SerialWorker"
        }
        
        ## Sensor Fusion Worker
        fusion_args = (self.serialQueue, self.eulerQueue, self.eulerDisplayQueue, 
                   self.controlQueue, self.statusQueue, self.stop_event, 
                   self.logQueue, self.uiStatusQueue)
        fusion_worker = Process(
            target = run_fusion_worker,
            args = fusion_args,
            name = "FusionWorker"
        )
        fusion_worker.start()
        self.workers.append(fusion_worker)
        
        # Store configuration for restart capability
        self._worker_configs["FusionWorker"] = {
            'target': run_fusion_worker,
            'args': fusion_args,
            'name': "FusionWorker"
        }

        ## UDP Worker
        udp_args = (self.eulerQueue, None, self.stop_event, 
                   None, None, self.udpControlQueue, self.statusQueue, 
                   self.logQueue)
        udp_worker = Process(
            target = run_udp_worker,
            args = udp_args,
            name = "UDPWorker"
        )
        udp_worker.start()
        self.workers.append(udp_worker)
        
        # Store configuration for restart capability
        self._worker_configs["UDPWorker"] = {
            'target': run_udp_worker,
            'args': udp_args,
            'name': "UDPWorker"
        }



        print("[ProcessHandler] All workers started.")
        
    def get_queue_health_report(self):
        """Get a comprehensive report of all queue health statistics."""
        from util.error_utils import monitor_queue_health
        
        queues = {
            'serialQueue': self.serialQueue,
            'eulerQueue': self.eulerQueue, 
            'eulerDisplayQueue': self.eulerDisplayQueue,
            'serialDisplayQueue': self.serialDisplayQueue,
            'controlQueue': self.controlQueue,
            'statusQueue': self.statusQueue,
            'messageQueue': self.messageQueue,
            'logQueue': self.logQueue
        }
        
        health_report = []
        critical_count = 0
        warning_count = 0
        
        for name, queue in queues.items():
            health = monitor_queue_health(queue, name)
            health_report.append(health)
            
            if health.get('status') == 'critical':
                critical_count += 1
            elif health.get('status') == 'warning':
                warning_count += 1
        
        summary = {
            'total_queues': len(queues),
            'critical': critical_count,
            'warnings': warning_count,
            'healthy': len(queues) - critical_count - warning_count,
            'details': health_report
        }
        
        return summary
        
    def log_queue_health(self):
        """Log current queue health to console and log file."""
        try:
            report = self.get_queue_health_report()
            
            if report['critical'] > 0 or report['warnings'] > 0:
                status_msg = f"Queue Health: {report['critical']} critical, {report['warnings']} warnings, {report['healthy']} healthy"
                print(f"[ProcessHandler] {status_msg}")
                
                # Log details for problem queues
                for queue_info in report['details']:
                    if queue_info.get('status') in ['critical', 'warning']:
                        name = queue_info['name']
                        fill_ratio = queue_info.get('fill_ratio', 0)
                        size = queue_info.get('size', 0)
                        max_size = queue_info.get('max_size', 0)
                        print(f"[ProcessHandler]   {name}: {fill_ratio:.1%} full ({size}/{max_size})")
        except Exception as e:
            print(f"[ProcessHandler] Queue health monitoring error: {e}")
    
    def get_queue_status_summary(self) -> str:
        """Get a quick summary string of queue health status."""
        try:
            report = self.get_queue_health_report()
            return f"Queues: {report['healthy']} healthy, {report['warnings']} warnings, {report['critical']} critical"
        except Exception as e:
            return f"Queue status unavailable: {e}"
        
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
            
            # Stop monitoring thread first
            self._monitoring_active = False
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=2.0)

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