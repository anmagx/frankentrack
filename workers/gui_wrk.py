"""
GUI Worker Module for Frankentrack

This module implements the main GUI application using a modular panel-based
architecture. It runs as a separate process and communicates with other workers
(serial, fusion, camera, UDP) via multiprocessing queues.

Architecture Overview:
---------------------
The GUI is organized into modular panels:
- SerialPanel: Controls serial port connection and reading
- MessagePanel: Displays messages and raw serial data
- OrientationPanel: Shows current orientation (yaw/pitch/roll) and position
- CalibrationPanel: Gyro calibration controls and status
- NetworkPanel: UDP output configuration and control
- CameraPanel: Camera selection, preview, and tracking controls
- StatusBar: System-wide status indicators (FPS, rates, calibration)

Queue-Based Communication:
-------------------------
The GUI communicates with other workers through these queues:

Input Queues (GUI reads from these):
- messageQueue: General log messages from all workers
- serialDisplayQueue: Raw serial data lines for display
- eulerDisplayQueue: Orientation angles [yaw, pitch, roll]
- translationDisplayQueue: Position data [x, y, z]
- cameraPreviewQueue: JPEG-encoded camera frames
- statusQueue: Status updates (calibration, drift, rates, etc.)

Output Queues (GUI writes to these):
- controlQueue: Commands to fusion worker ('reset', 'drift_on', etc.)
- serialControlQueue: Commands to serial worker ('start', 'stop', port, baud)
- cameraControlQueue: Commands to camera worker ('start', 'stop', camera_id, etc.)
- udpControlQueue: Commands to UDP worker ('start', 'stop', ip, port)

Preferences System:
------------------
User preferences are saved to config/config.cfg using PreferencesManager.
This includes:
- Last used serial port and baud rate
- Camera selection and tracking parameters
- UDP output settings
- Drift correction thresholds

All panels implement get_prefs() and set_prefs() for persistence.
"""

import tkinter as tk
from tkinter import ttk
import time
import os
from queue import Empty

from config.config import (
    GUI_POLL_INTERVAL_MS,
    MAX_TEXT_BUFFER_LINES,
    DEFAULT_UDP_IP,
    DEFAULT_UDP_PORT,
    DEFAULT_DETECTION_THRESHOLD,
    DEFAULT_CENTER_THRESHOLD,
    QUEUE_PUT_TIMEOUT,
    PREVIEW_WIDTH,
    PREVIEW_HEIGHT
)
from util.error_utils import safe_queue_put, safe_queue_get
from workers.gui.panels.serial_panel import SerialPanel
from workers.gui.panels.message_panel import MessagePanel
from workers.gui.panels.orientation_panel import OrientationPanel
from workers.gui.panels.status_bar import StatusBar
from workers.gui.panels.network_panel import NetworkPanel
from workers.gui.panels.camera_panel import CameraPanel
from workers.gui.managers.preferences_manager import PreferencesManager
from workers.gui.panels.calibration_panel import CalibrationPanel


class AppV2(tk.Tk):
    """
    Modular GUI application for Frankentrack headtracking system.

    This is the main window class that orchestrates all GUI panels and handles
    communication with worker processes through multiprocessing queues.

    The GUI runs in its own process and polls queues at regular intervals
    (default: 50ms) to update displays and send commands to workers.

    Key Responsibilities:
    --------------------
    1. Create and manage all GUI panels (serial, camera, orientation, etc.)
    2. Poll input queues for updates from workers
    3. Route commands from panels to appropriate worker queues
    4. Save/load user preferences
    5. Handle application shutdown gracefully

    Threading Model:
    ---------------
    - Runs in main thread of GUI process
    - Uses after() for non-blocking queue polling
    - All queue operations use timeouts to prevent blocking
    - stop_event signals shutdown to all workers

    Attributes:
    ----------
    messageQueue : Queue
        Receives log messages from all workers
    serialDisplayQueue : Queue
        Receives raw serial data lines for display
    eulerDisplayQueue : Queue
        Receives orientation angles [yaw, pitch, roll]
    translationDisplayQueue : Queue
        Receives position data [x, y, z]
    statusQueue : Queue
        Receives status updates (rates, calibration, etc.)
    cameraPreviewQueue : Queue
        Receives JPEG frames from camera worker
    controlQueue : Queue
        Sends commands to fusion worker
    serialControlQueue : Queue
        Sends commands to serial worker
    cameraControlQueue : Queue
        Sends commands to camera worker
    udpControlQueue : Queue
        Sends commands to UDP worker
    stop_event : multiprocessing.Event
        Signals shutdown to all workers
    """
    
    def __init__(self, messageQueue, serialDisplayQueue, statusQueue, stop_event, 
                 eulerDisplayQueue=None, controlQueue=None, serialControlQueue=None, 
                 translationDisplayQueue=None, cameraControlQueue=None, 
                 cameraPreviewQueue=None, udpControlQueue=None, poll_ms=GUI_POLL_INTERVAL_MS):
        """
        Initialize the GUI application.

        Parameters:
        ----------
        messageQueue : Queue
            Queue for receiving log messages from workers
        serialDisplayQueue : Queue
            Queue for receiving raw serial data
        statusQueue : Queue
            Queue for receiving status updates
        stop_event : multiprocessing.Event
            Event to signal shutdown to all workers
        eulerDisplayQueue : Queue, optional
            Queue for receiving orientation angles
        controlQueue : Queue, optional
            Queue for sending commands to fusion worker
        serialControlQueue : Queue, optional
            Queue for sending commands to serial worker
        translationDisplayQueue : Queue, optional
            Queue for receiving position data
        cameraControlQueue : Queue, optional
            Queue for sending commands to camera worker
        cameraPreviewQueue : Queue, optional
            Queue for receiving camera preview frames
        udpControlQueue : Queue, optional
            Queue for sending commands to UDP worker
        poll_ms : int, optional
            Polling interval in milliseconds (default: from config)
        """
        super().__init__()
        self.title("frankentrack v0.11-alpha GUI")
        self.resizable(False, False)
        
        # Set App User Model ID for Windows taskbar icon
        try:
            import ctypes
            myappid = 'anmagx.frankentrack.headtracker.01'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
        
        # Set window icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img', 'icon.ico')
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass  # Silently fail if icon not found
        
        # Store queues for communication with workers
        self.messageQueue = messageQueue
        self.serialDisplayQueue = serialDisplayQueue
        self.statusQueue = statusQueue
        self.eulerDisplayQueue = eulerDisplayQueue
        self.controlQueue = controlQueue
        self.serialControlQueue = serialControlQueue
        self.translationDisplayQueue = translationDisplayQueue
        self.cameraControlQueue = cameraControlQueue
        self.cameraPreviewQueue = cameraPreviewQueue
        self.udpControlQueue = udpControlQueue
        self.stop_event = stop_event
        
        self.poll_ms = int(poll_ms)
        
        # Internal buffers for message/serial data (fallback if panels not ready)
        self._msg_buffer = []
        self._serial_buffer = []
        self._max_lines = MAX_TEXT_BUFFER_LINES
        
        # Preferences manager handles saving/loading user settings
        self.prefs_manager = PreferencesManager()
        
        # build UI
        self._build_layout()
        # load user preferences
        self._load_preferences()

        # If no user prefs/config file exists, auto-start camera enumeration once
        try:
            # Use PreferencesManager.exists() to determine if saved prefs exist.
            # Schedule enumeration when the GUI becomes idle (no fixed delay).
            if not self.prefs_manager.exists():
                self.after_idle(self.camera_panel._on_enumerate_clicked)
        except Exception:
            pass
        
        # Start polling queues after GUI is built
        self.after(self.poll_ms, self._poll_queues)
        self.protocol('WM_DELETE_WINDOW', self._on_close)
    
    def _build_layout(self):
        """
        Build the main GUI layout with all panels.

        Layout Structure:
        ----------------
        ┌─────────────────────────────────────────────┐
        │  Content Frame                              │
        │  ┌────────────────┬────────────────────┐   │
        │  │ Left Column    │ Right Column       │   │
        │  │ ┌────────────┐ │ ┌────────────────┐ │   │
        │  │ │SerialPanel │ │ │ NetworkPanel   │ │   │
        │  │ └────────────┘ │ └────────────────┘ │   │
        │  │ ┌────────────┐ │ ┌────────────────┐ │   │
        │  │ │MessagePanel│ │ │  CameraPanel   │ │   │
        │  │ └────────────┘ │ └────────────────┘ │   │
        │  │ ┌────────────┐ │                    │   │
        │  │ │OrientPanel │ │                    │   │
        │  │ └────────────┘ │                    │   │
        │  │ ┌────────────┐ │                    │   │
        │  │ │CalibPanel  │ │                    │   │
        │  │ └────────────┘ │                    │   │
        │  └────────────────┴────────────────────┘   │
        └─────────────────────────────────────────────┘
        ┌─────────────────────────────────────────────┐
        │  Status Bar                                 │
        └─────────────────────────────────────────────┘

        Each panel is self-contained and handles its own UI and logic.
        Panels communicate with workers via the queues passed to __init__.
        """
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Left column: Serial, Messages, Orientation, Calibration
        left_col = ttk.Frame(content)
        left_col.pack(side="left", fill="both", expand=True)
        
        # Right column: Network, Camera
        right_col = ttk.Frame(content)
        right_col.pack(side="right", fill="y")
        
        # SerialPanel: COM port selection, baud rate, start/stop
        self.serial_panel = SerialPanel(
            left_col,
            self.serialControlQueue,
            self.append_message,
            padding=8,
            on_stop=self._on_serial_stop
        )
        self.serial_panel.pack(fill="x", expand=False, padx=0, pady=0)
        
        # MessagePanel: Displays log messages and raw serial data
        self.message_panel = MessagePanel(
            left_col,
            serial_height=8,
            message_height=8,
            padding=6
        )
        self.message_panel.pack(fill="both", expand=True, padx=0, pady=(8, 8))
        
        # OrientationPanel: Shows current yaw/pitch/roll and position
        self.orientation_panel = OrientationPanel(
            left_col,
            self.controlQueue,
            self.append_message,
            padding=6
        )
        self.orientation_panel.pack(fill="x", expand=False, padx=0, pady=(0, 8))

        # CalibrationPanel: Gyro calibration controls
        self.calibration_panel = CalibrationPanel(
            left_col,
            self.controlQueue,
            self.append_message,
            padding=6
        )
        self.calibration_panel.pack(fill="x", expand=False, padx=0, pady=(0, 8))
        
        # NetworkPanel: UDP output configuration (IP, port, start/stop)
        self.network_panel = NetworkPanel(
            right_col,
            self.udpControlQueue,
            self.append_message,
            padding=6
        )
        self.network_panel.pack(fill="x", expand=False, padx=(8, 0), pady=(0, 8))
        
        # CameraPanel: Camera selection, preview, tracking controls
        self.camera_panel = CameraPanel(
            right_col,
            self.cameraControlQueue,
            self.messageQueue,
            padding=6
        )
        self.camera_panel.pack(fill="both", expand=True, padx=(8, 0), pady=(8, 0))
        
        # StatusBar: Shows message rate, send rate, camera FPS, calibration status
        self.status_bar = StatusBar(self, relief="sunken")
        self.status_bar.pack(side="bottom", fill="x")
    
    def append_message(self, msg):
        """
        Append a message to the message display.

        This is used by panels to log user actions and system events.
        Messages are displayed in the MessagePanel and also printed to console.

        Parameters:
        ----------
        msg : str
            Message to display
        """
        if hasattr(self, 'message_panel'):
            self.message_panel.append_message(msg)
        else:
            # Fallback if panel not ready yet
            self._msg_buffer.append(str(msg))
            if len(self._msg_buffer) > self._max_lines:
                self._msg_buffer = self._msg_buffer[-self._max_lines:]
        
        # Also print to console for debugging
        print(f"[GUI] {msg}")
    
    def _load_preferences(self):
        """
        Load and apply saved user preferences.

        Preferences are loaded from config/config.cfg and applied to all panels.
        This includes:
        - Last used serial port and baud rate
        - Camera selection and tracking settings
        - UDP output configuration
        - Drift correction thresholds

        If no saved preferences exist, panels use their default values.
        """
        prefs = self.prefs_manager.load()
        
        if not prefs:
            return  # No saved preferences, use defaults
        
        # Apply preferences to each panel
        if hasattr(self, 'serial_panel'):
            self.serial_panel.set_prefs(prefs)
        
        if hasattr(self, 'orientation_panel'):
            self.orientation_panel.set_prefs(prefs)
        
        if hasattr(self, 'calibration_panel'):
            self.calibration_panel.set_prefs(prefs)
        
        if hasattr(self, 'network_panel'):
            self.network_panel.set_prefs(prefs)
        
        if hasattr(self, 'camera_panel'):
            self.camera_panel.set_prefs(prefs)
        
        self.append_message("Preferences loaded")

    def _on_serial_stop(self):
        """
        Handle serial reading stop event.

        When serial reading stops, we need to reset the system state:

        1. Request fusion worker to reset (clears gyro bias and state)
        2. Drain display queues to clear stale data from UI
        3. Mark gyro as uncalibrated (user must recalibrate)

        Why drain queues?
        ----------------
        When serial stops, there may be stale sensor data in the queues.
        Draining ensures the UI shows fresh data when serial restarts.

        Why NOT drain control queues?
        -----------------------------
        Control queues (serialControlQueue, controlQueue) carry commands
        that must be delivered to workers. Draining them would lose commands.

        Why request reset?
        -----------------
        The gyro bias computed during calibration is only valid for the
        current session. Starting a new serial session requires fresh
        calibration to account for sensor drift.
        """
        try:
            self.append_message("Serial stopped: requesting recalibration and draining queues")

            # Request fusion worker to reset its state
            try:
                if self.controlQueue:
                    safe_queue_put(self.controlQueue, ('reset',), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

            # Drain display queues (but NOT control queues)
            for q in (self.messageQueue, self.serialDisplayQueue,
                      self.eulerDisplayQueue, self.translationDisplayQueue,
                      self.cameraPreviewQueue, self.statusQueue):
                if not q:
                    continue
                try:
                    while True:
                        item = safe_queue_get(q, timeout=0.0, default=None)
                        if item is None:
                            break
                except Exception:
                    pass

            # Mark gyro as uncalibrated
            try:
                if self.statusQueue:
                    safe_queue_put(self.statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

        except Exception:
            try:
                self.append_message("Error while performing serial stop actions")
            except Exception:
                pass
    
    def _save_preferences(self):
        """
        Save current user preferences to config/config.cfg.

        Preferences are collected from all panels using their get_prefs() methods.
        This includes:
        - Serial port and baud rate
        - Camera ID and tracking parameters
        - UDP IP and port
        - Drift correction thresholds

        Preferences are saved in JSON format and automatically loaded on next startup.
        """
        # Collect preferences from all panels
        prefs = {}
        
        if hasattr(self, 'serial_panel'):
            prefs.update(self.serial_panel.get_prefs())
        
        if hasattr(self, 'orientation_panel'):
            prefs.update(self.orientation_panel.get_prefs())
        
        if hasattr(self, 'calibration_panel'):
            prefs.update(self.calibration_panel.get_prefs())
        
        if hasattr(self, 'network_panel'):
            prefs.update(self.network_panel.get_prefs())
        
        if hasattr(self, 'camera_panel'):
            prefs.update(self.camera_panel.get_prefs())
        
        # Save using PreferencesManager
        if self.prefs_manager.save(prefs):
            self.append_message("Preferences saved")
        else:
            self.append_message("Failed to save preferences")
    
    def _poll_queues(self):
        """
        Poll all input queues for updates from workers.

        This method is called repeatedly (default: every 50ms) to check for
        new data from worker processes. It drains each queue completely to
        avoid lag and updates the corresponding GUI panels.

        Queue Processing Order:
        ----------------------
        1. messageQueue: Log messages (highest priority)
        2. serialDisplayQueue: Raw serial data
        3. eulerDisplayQueue: Orientation angles [yaw, pitch, roll]
        4. translationDisplayQueue: Position data [x, y, z]
        5. statusQueue: Status updates (rates, calibration, etc.)
        6. cameraPreviewQueue: Preview frames (JPEG bytes)

        Each queue is drained completely (until empty) to prevent backlog.
        Updates are batched where possible for performance.

        Threading Safety:
        ----------------
        - All queue operations use timeout=0.0 (non-blocking)
        - safe_queue_get() handles Empty exceptions
        - GUI updates are safe (called from main thread via after())

        Performance:
        -----------
        - Drains all available items per queue per poll
        - MessagePanel batches text updates (update_displays())
        - Camera preview drops frames if processing is slow

        Shutdown:
        --------
        If stop_event is set, calls quit() and returns immediately.
        Otherwise, schedules itself to run again after poll_ms.
        """
        try:
            # 1. Drain messageQueue (log messages from all workers)
            while True:
                msg = safe_queue_get(self.messageQueue, timeout=0.0, default=None)
                if msg is None:
                    break
                self.append_message(msg)
            
            # 2. Drain serialDisplayQueue (raw serial data lines)
            while True:
                s = safe_queue_get(self.serialDisplayQueue, timeout=0.0, default=None)
                if s is None:
                    break
                if hasattr(self, 'message_panel'):
                    self.message_panel.append_serial(s)
                else:
                    self._serial_buffer.append(str(s))
                    if len(self._serial_buffer) > self._max_lines:
                        self._serial_buffer = self._serial_buffer[-self._max_lines:]
            
            # Update message panel displays (batched for performance)
            if hasattr(self, 'message_panel'):
                self.message_panel.update_displays()
            
            # 3. Drain eulerDisplayQueue (orientation angles)
            # Expected format: [yaw, pitch, roll] or [yaw, pitch, roll, x, y, z]
            while True:
                e = safe_queue_get(self.eulerDisplayQueue, timeout=0.0, default=None)
                if e is None:
                    break
                try:
                    if hasattr(self, 'orientation_panel') and len(e) >= 3:
                        yaw, pitch, roll = float(e[0]), float(e[1]), float(e[2])
                        self.orientation_panel.update_euler(yaw, pitch, roll)
                except Exception:
                    pass
            
            # 4. Drain translationDisplayQueue (position data)
            # Expected format: [x, y, z] or ('_CAM_STATUS', message)
            while True:
                t = safe_queue_get(self.translationDisplayQueue, timeout=0.0, default=None)
                if t is None:
                    break
                try:
                    if hasattr(self, 'orientation_panel') and isinstance(t, (list, tuple)) and len(t) >= 3:
                        # Check if it's a camera status message
                        if isinstance(t[0], str) and t[0].startswith('_CAM_'):
                            self.append_message(f"Camera status: {t[1]}")
                        else:
                            # Raw translation coordinates
                            x, y, z = float(t[0]), float(t[1]), float(t[2])
                            self.orientation_panel.update_position(x, y, z)
                except Exception:
                    pass
            
            # 5. Drain statusQueue (system status updates)
            # Expected format: (status_type, value)
            # Status types:
            # - 'drift_correction': bool - drift correction active/inactive
            # - 'stationary': bool - device stationary/moving
            # - 'gyro_calibrated': bool - gyro calibration status
            # - 'msg_rate': float - message rate in Hz
            # - 'send_rate': float - UDP send rate in Hz
            # - 'cam_fps': float - camera FPS
            while True:
                status = safe_queue_get(self.statusQueue, timeout=0.0, default=None)
                if status is None:
                    break
                if isinstance(status, tuple) and len(status) >= 2:
                    if status[0] == 'drift_correction':
                        if hasattr(self, 'orientation_panel'):
                            active = bool(status[1])
                            self.orientation_panel.update_drift_status(active)
                    elif status[0] == 'stationary':
                        # Device stationary/moving status (shown in status bar)
                        if hasattr(self, 'status_bar'):
                            try:
                                self.status_bar.update_device_status(bool(status[1]))
                            except Exception:
                                pass
                    elif status[0] == 'gyro_calibrated':
                        # Gyro calibration status (shown in calibration panel)
                        if hasattr(self, 'calibration_panel'):
                            try:
                                self.calibration_panel.update_calibration_status(bool(status[1]))
                            except Exception:
                                pass
                        elif hasattr(self, 'status_bar'):
                            try:
                                self.status_bar.update_calibration_status(bool(status[1]))
                            except Exception:
                                pass
                    elif status[0] == 'msg_rate':
                        # Message rate in Hz (shown in status bar)
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_message_rate(float(status[1]))
                    elif status[0] == 'send_rate':
                        # UDP send rate in Hz (shown in status bar)
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_send_rate(float(status[1]))
                    elif status[0] == 'cam_fps':
                        # Camera FPS (shown in status bar)
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_camera_fps(float(status[1]))
            
            # 6. Drain cameraPreviewQueue (JPEG preview frames)
            # Expected format: bytes or (bytes, timestamp)
            while True:
                preview = safe_queue_get(self.cameraPreviewQueue, timeout=0.0, default=None)
                if preview is None:
                    break
                if hasattr(self, 'camera_panel'):
                    try:
                        if isinstance(preview, (bytes, bytearray)):
                            self.camera_panel.update_preview(preview)
                        elif isinstance(preview, (list, tuple)) and len(preview) >= 1 and isinstance(preview[0], (bytes, bytearray)):
                            self.camera_panel.update_preview(preview[0])
                    except Exception:
                        pass
            
            # Check for shutdown signal
            if self.stop_event and hasattr(self.stop_event, 'is_set') and self.stop_event.is_set():
                self.quit()
                return
        
        finally:
            # Schedule next poll (runs continuously until quit)
            self.after(self.poll_ms, self._poll_queues)
    
    def _on_close(self):
        """
        Handle window close event.

        Shutdown sequence:
        -----------------
        1. Save user preferences to config.cfg
        2. Set stop_event to signal all workers to shutdown
        3. Send shutdown message to messageQueue
        4. Quit the GUI main loop

        This ensures clean shutdown of all worker processes and
        preservation of user settings for next session.
        """
        self._save_preferences()
        
        # Signal all workers to stop
        if self.stop_event and hasattr(self.stop_event, 'set'):
            try:
                self.stop_event.set()
            except Exception:
                pass
        
        # Send shutdown message
        try:
            if self.messageQueue:
                self.messageQueue.put_nowait('GUI shutting down')
        except Exception:
            pass
        
        # Quit the GUI
        try:
            self.quit()
        except Exception:
            try:
                self.destroy()
            except Exception:
                pass


def run_worker(messageQueue, serialDisplayQueue, statusQueue, stop_event, 
               eulerDisplayQueue=None, controlQueue=None, serialControlQueue=None, 
               translationDisplayQueue=None, cameraControlQueue=None, 
               cameraPreviewQueue=None, udpControlQueue=None, logQueue=None):
    """
    Entry point for GUI worker process.

    This function is called by process_man.ProcessHandler to start the GUI
    in a separate process. It creates the main window and runs the Tkinter
    event loop.

    Process Architecture:
    --------------------
    The GUI runs as a separate process (not thread) to avoid blocking other
    workers. This allows:
    - Non-blocking camera preview rendering
    - Responsive UI even during heavy sensor processing
    - Clean isolation of GUI state from worker state

    Communication:
    -------------
    All communication with other workers happens through multiprocessing queues.
    See module docstring for queue details.

    Error Handling:
    --------------
    - Logs all errors to logQueue
    - Prints errors to console for debugging
    - Catches KeyboardInterrupt for clean shutdown
    - Ensures app.quit() is called on all exit paths

    Parameters:
    ----------
    messageQueue : Queue
        Queue for receiving log messages
    serialDisplayQueue : Queue
        Queue for receiving raw serial data
    statusQueue : Queue
        Queue for receiving status updates
    stop_event : multiprocessing.Event
        Event to signal shutdown
    eulerDisplayQueue : Queue, optional
        Queue for receiving orientation angles
    controlQueue : Queue, optional
        Queue for sending commands to fusion worker
    serialControlQueue : Queue, optional
        Queue for sending commands to serial worker
    translationDisplayQueue : Queue, optional
        Queue for receiving position data
    cameraControlQueue : Queue, optional
        Queue for sending commands to camera worker
    cameraPreviewQueue : Queue, optional
        Queue for receiving camera preview frames
    udpControlQueue : Queue, optional
        Queue for sending commands to UDP worker
    logQueue : Queue, optional
        Queue for sending log messages to log worker
    """
    from util.log_utils import log_info, log_error
    import traceback
    
    log_info(logQueue, "GUI Worker", "Starting GUI worker")
    print("[GUI Worker] Starting GUI worker...")
    
    try:
        print("[GUI Worker] Creating AppV2 instance...")
        app = AppV2(
            messageQueue, serialDisplayQueue, statusQueue, stop_event,
            eulerDisplayQueue=eulerDisplayQueue, controlQueue=controlQueue,
            serialControlQueue=serialControlQueue, 
            translationDisplayQueue=translationDisplayQueue,
            cameraControlQueue=cameraControlQueue, 
            cameraPreviewQueue=cameraPreviewQueue,
            udpControlQueue=udpControlQueue
        )
        print("[GUI Worker] App created, starting mainloop...")
        app.mainloop()
        log_info(logQueue, "GUI Worker", "GUI window closed normally")
        print("[GUI Worker] GUI window closed normally")
    except KeyboardInterrupt:
        log_info(logQueue, "GUI Worker", "Interrupted by user")
        print("[GUI Worker] Interrupted by user")
        try:
            app.quit()
        except Exception:
            pass
    except Exception as e:
        error_msg = f"GUI error: {e}\n{traceback.format_exc()}"
        log_error(logQueue, "GUI Worker", error_msg)
        print(f"[GUI Worker] ERROR: {error_msg}")
        try:
            app.quit()
        except Exception:
            pass
