"""
Alternative GUI entry point for testing refactored components.

This provides a way to run the new refactored GUI in parallel with the
production gui_wrk.py. Use this for integration testing before switching.

Usage from process_man.py:
    # Import the new GUI instead of the old one
    from workers import gui_wrk_v2 as gui_wrk
    # OR keep both and launch via environment variable
"""
import tkinter as tk
from tkinter import ttk
import time
from queue import Empty

from config.config import (
    GUI_POLL_INTERVAL_MS,
    MAX_TEXT_BUFFER_LINES,
    DEFAULT_UDP_IP,
    DEFAULT_UDP_PORT,
    DEFAULT_DETECTION_THRESHOLD,
    DEFAULT_CENTER_THRESHOLD,
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


class AppV2(tk.Tk):
    """
    Refactored GUI application (Version 2).
    
    This version uses modular panels instead of monolithic code.
    It maintains full compatibility with the existing queue-based architecture.
    """
    
    def __init__(self, messageQueue, serialDisplayQueue, statusQueue, stop_event, 
                 eulerDisplayQueue=None, controlQueue=None, serialControlQueue=None, 
                 translationDisplayQueue=None, cameraControlQueue=None, 
                 cameraPreviewQueue=None, udpControlQueue=None, poll_ms=GUI_POLL_INTERVAL_MS):
        super().__init__()
        self.title("acceltrack v.01 (Refactored)")
        self.resizable(False, False)
        
        # Store queues
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
        
        # Internal buffers
        self._msg_buffer = []
        self._serial_buffer = []
        self._max_lines = MAX_TEXT_BUFFER_LINES
        
        # Preferences manager
        self.prefs_manager = PreferencesManager()
        
        self._build_layout()
        self._load_preferences()
        
        # Start polling
        self.after(self.poll_ms, self._poll_queues)
        self.protocol('WM_DELETE_WINDOW', self._on_close)
    
    def _build_layout(self):
        """Build the main layout using refactored panels."""
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=8, pady=8)
        
        left_col = ttk.Frame(content)
        left_col.pack(side="left", fill="both", expand=True)
        
        right_col = ttk.Frame(content)
        right_col.pack(side="right", fill="y")
        
        # Create SerialPanel (refactored)
        self.serial_panel = SerialPanel(
            left_col,
            self.serialControlQueue,
            self.append_message,
            padding=8
        )
        self.serial_panel.pack(fill="x", expand=False, padx=0, pady=0)
        
        # Create MessagePanel (refactored)
        self.message_panel = MessagePanel(
            left_col,
            serial_height=8,
            message_height=8,
            padding=6
        )
        self.message_panel.pack(fill="both", expand=True, padx=0, pady=(8, 8))
        
        # Create OrientationPanel (refactored)
        self.orientation_panel = OrientationPanel(
            left_col,
            self.controlQueue,
            self.append_message,
            padding=6
        )
        self.orientation_panel.pack(fill="x", expand=False, padx=0, pady=(0, 8))
        
        # Create NetworkPanel (refactored) in right column
        self.network_panel = NetworkPanel(
            right_col,
            self.udpControlQueue,
            self.append_message,
            padding=6
        )
        self.network_panel.pack(fill="x", expand=False, padx=(8, 0), pady=(0, 8))
        
        # Create CameraPanel (refactored)
        self.camera_panel = CameraPanel(
            right_col,
            self.cameraControlQueue,
            self.messageQueue,
            padding=6
        )
        self.camera_panel.pack(fill="both", expand=True, padx=(8, 0), pady=(8, 0))
        
        # Create StatusBar (refactored) - pack at window bottom
        self.status_bar = StatusBar(self, relief="sunken")
        self.status_bar.pack(side="bottom", fill="x")
    
    def append_message(self, msg):
        """Append a message to the message buffer."""
        if hasattr(self, 'message_panel'):
            self.message_panel.append_message(msg)
        else:
            # Fallback if panel not ready
            self._msg_buffer.append(str(msg))
            if len(self._msg_buffer) > self._max_lines:
                self._msg_buffer = self._msg_buffer[-self._max_lines:]
        
        # Also print for debugging
        print(f"[GUI] {msg}")
    
    def _load_preferences(self):
        """Load and apply saved preferences."""
        prefs = self.prefs_manager.load()
        
        if not prefs:
            return  # No saved preferences, use defaults
        
        # Apply to SerialPanel
        if hasattr(self, 'serial_panel'):
            self.serial_panel.set_prefs(prefs)
        
        # Apply to OrientationPanel
        if hasattr(self, 'orientation_panel'):
            self.orientation_panel.set_prefs(prefs)
        
        # Apply to NetworkPanel
        if hasattr(self, 'network_panel'):
            self.network_panel.set_prefs(prefs)
        
        # Apply to CameraPanel
        if hasattr(self, 'camera_panel'):
            self.camera_panel.set_prefs(prefs)
        
        self.append_message("Preferences loaded")
    
    def _save_preferences(self):
        """Save current preferences."""
        # Collect preferences from all panels
        prefs = {}
        
        # SerialPanel preferences
        if hasattr(self, 'serial_panel'):
            prefs.update(self.serial_panel.get_prefs())
        
        # OrientationPanel preferences
        if hasattr(self, 'orientation_panel'):
            prefs.update(self.orientation_panel.get_prefs())
        
        # NetworkPanel preferences
        if hasattr(self, 'network_panel'):
            prefs.update(self.network_panel.get_prefs())
        
        # CameraPanel preferences
        if hasattr(self, 'camera_panel'):
            prefs.update(self.camera_panel.get_prefs())
        
        # Save using PreferencesManager
        if self.prefs_manager.save(prefs):
            self.append_message("Preferences saved")
        else:
            self.append_message("Failed to save preferences")
    
    def _poll_queues(self):
        """Poll all queues for updates."""
        try:
            # Drain messageQueue
            while True:
                msg = safe_queue_get(self.messageQueue, timeout=0.0, default=None)
                if msg is None:
                    break
                self.append_message(msg)
            
            # Drain serialDisplayQueue
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
            
            # Update message panel displays (batched for efficiency)
            if hasattr(self, 'message_panel'):
                self.message_panel.update_displays()
            
            # Drain eulerDisplayQueue (optional)
            while True:
                e = safe_queue_get(self.eulerDisplayQueue, timeout=0.0, default=None)
                if e is None:
                    break
                # expect [Yaw, Pitch, Roll] or [Yaw, Pitch, Roll, X, Y, Z]
                try:
                    if hasattr(self, 'orientation_panel') and len(e) >= 3:
                        yaw, pitch, roll = float(e[0]), float(e[1]), float(e[2])
                        self.orientation_panel.update_euler(yaw, pitch, roll)
                except Exception:
                    pass
            
            # Drain translationDisplayQueue (optional)
            while True:
                t = safe_queue_get(self.translationDisplayQueue, timeout=0.0, default=None)
                if t is None:
                    break
                # Handle translation data [x, y, z]
                try:
                    if hasattr(self, 'orientation_panel') and isinstance(t, (list, tuple)) and len(t) >= 3:
                        # Check if it's a status message
                        if isinstance(t[0], str) and t[0].startswith('_CAM_'):
                            self.append_message(f"Camera status: {t[1]}")
                        else:
                            # Raw translation
                            x, y, z = float(t[0]), float(t[1]), float(t[2])
                            self.orientation_panel.update_position(x, y, z)
                except Exception:
                    pass
            
            # Drain statusQueue
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
                        if hasattr(self, 'status_bar'):
                            try:
                                self.status_bar.update_device_status(bool(status[1]))
                            except Exception:
                                pass
                    elif status[0] == 'gyro_calibrated':
                        if hasattr(self, 'status_bar'):
                            try:
                                self.status_bar.update_calibration_status(bool(status[1]))
                            except Exception:
                                pass
                    elif status[0] == 'msg_rate':
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_message_rate(float(status[1]))
                    elif status[0] == 'send_rate':
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_send_rate(float(status[1]))
                    elif status[0] == 'cam_fps':
                        if hasattr(self, 'status_bar'):
                            self.status_bar.update_camera_fps(float(status[1]))
            
            # Drain cameraPreviewQueue
            while True:
                preview = safe_queue_get(self.cameraPreviewQueue, timeout=0.0, default=None)
                if preview is None:
                    break
                # Handle preview frame (JPEG bytes). Camera worker may send
                # either raw bytes or a tuple (bytes, timestamp), accept both.
                if hasattr(self, 'camera_panel'):
                    try:
                        if isinstance(preview, (bytes, bytearray)):
                            self.camera_panel.update_preview(preview)
                        elif isinstance(preview, (list, tuple)) and len(preview) >= 1 and isinstance(preview[0], (bytes, bytearray)):
                            self.camera_panel.update_preview(preview[0])
                    except Exception:
                        pass
            
            # Check stop event
            if self.stop_event and hasattr(self.stop_event, 'is_set') and self.stop_event.is_set():
                self.quit()
                return
        
        finally:
            self.after(self.poll_ms, self._poll_queues)
    
    def _on_close(self):
        """Handle window close event."""
        self._save_preferences()
        
        if self.stop_event and hasattr(self.stop_event, 'set'):
            try:
                self.stop_event.set()
            except Exception:
                pass
        
        try:
            if self.messageQueue:
                self.messageQueue.put_nowait('GUI shutting down')
        except Exception:
            pass
        
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
    Entry point compatible with process_man.ProcessHandler.
    
    This is a drop-in replacement for gui_wrk.run_worker() that uses
    the refactored GUI components.
    """
    from util.log_utils import log_info, log_error
    import traceback
    
    log_info(logQueue, "GUI Worker V2", "Starting refactored GUI worker")
    print("[GUI Worker V2] Starting refactored GUI worker...")
    
    try:
        print("[GUI Worker V2] Creating AppV2 instance...")
        app = AppV2(
            messageQueue, serialDisplayQueue, statusQueue, stop_event,
            eulerDisplayQueue=eulerDisplayQueue, controlQueue=controlQueue,
            serialControlQueue=serialControlQueue, 
            translationDisplayQueue=translationDisplayQueue,
            cameraControlQueue=cameraControlQueue, 
            cameraPreviewQueue=cameraPreviewQueue,
            udpControlQueue=udpControlQueue
        )
        print("[GUI Worker V2] App created, starting mainloop...")
        app.mainloop()
        log_info(logQueue, "GUI Worker V2", "GUI window closed normally")
        print("[GUI Worker V2] GUI window closed normally")
    except KeyboardInterrupt:
        log_info(logQueue, "GUI Worker V2", "Interrupted by user")
        print("[GUI Worker V2] Interrupted by user")
        try:
            app.quit()
        except Exception:
            pass
    except Exception as e:
        error_msg = f"GUI error: {e}\n{traceback.format_exc()}"
        log_error(logQueue, "GUI Worker V2", error_msg)
        print(f"[GUI Worker V2] ERROR: {error_msg}")
        try:
            app.quit()
        except Exception:
            pass
