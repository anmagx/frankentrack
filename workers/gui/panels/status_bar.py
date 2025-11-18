"""
Status Bar for Acceltrack GUI.

Displays real-time statistics at the bottom of the window:
- Message Rate: Messages per second from IMU
- Send Rate: UDP packets per second
- Camera FPS: Camera frames per second
"""
import tkinter as tk
from tkinter import ttk


class StatusBar(ttk.Frame):
    """Status bar displaying real-time performance metrics."""
    
    def __init__(self, parent, relief="sunken"):
        """
        Initialize the Status Bar.
        
        Args:
            parent: Parent tkinter widget (typically the root window)
            relief: Border style (default: "sunken")
        """
        super().__init__(parent, relief=relief)
        
        # Status variables
        self.msg_rate_var = tk.StringVar(value="0 msg/s")
        self.send_rate_var = tk.StringVar(value="0 msg/s")
        self.camera_fps_var = tk.StringVar(value="0.0 fps")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the status bar UI."""
        # Message Rate
        ttk.Label(self, text="Message Rate:").pack(
            side="left", padx=(8, 2), pady=2
        )
        ttk.Label(self, textvariable=self.msg_rate_var, width=12).pack(
            side="left"
        )
        
        # Send Rate
        ttk.Label(self, text="Send Rate:").pack(
            side="left", padx=(12, 2), pady=2
        )
        ttk.Label(self, textvariable=self.send_rate_var, width=12).pack(
            side="left"
        )
        
        # Camera FPS
        ttk.Label(self, text="Camera FPS:").pack(
            side="left", padx=(12, 2), pady=2
        )
        ttk.Label(self, textvariable=self.camera_fps_var, width=12).pack(
            side="left"
        )
    
    def update_message_rate(self, rate):
        """
        Update the message rate display.
        
        Args:
            rate: Messages per second (float)
        """
        try:
            self.msg_rate_var.set(f"{float(rate):.1f} msg/s")
        except Exception:
            pass
    
    def update_send_rate(self, rate):
        """
        Update the send rate display.
        
        Args:
            rate: Packets per second (float)
        """
        try:
            self.send_rate_var.set(f"{float(rate):.1f} msg/s")
        except Exception:
            pass
    
    def update_camera_fps(self, fps):
        """
        Update the camera FPS display.
        
        Args:
            fps: Frames per second (float)
        """
        try:
            self.camera_fps_var.set(f"{float(fps):.1f} fps")
        except Exception:
            pass
    
    def update_all(self, msg_rate=None, send_rate=None, camera_fps=None):
        """
        Update multiple metrics at once.
        
        Args:
            msg_rate: Optional message rate to update
            send_rate: Optional send rate to update
            camera_fps: Optional camera FPS to update
        """
        if msg_rate is not None:
            self.update_message_rate(msg_rate)
        if send_rate is not None:
            self.update_send_rate(send_rate)
        if camera_fps is not None:
            self.update_camera_fps(camera_fps)
    
    def reset(self):
        """Reset all metrics to zero."""
        self.msg_rate_var.set("0 msg/s")
        self.send_rate_var.set("0 msg/s")
        self.camera_fps_var.set("0.0 fps")
    
    def get_values(self):
        """
        Get current displayed values.
        
        Returns:
            dict: Dictionary with 'msg_rate', 'send_rate', 'camera_fps' keys
        """
        return {
            'msg_rate': self.msg_rate_var.get(),
            'send_rate': self.send_rate_var.get(),
            'camera_fps': self.camera_fps_var.get()
        }
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Empty dict (no preferences to save for this panel)
        """
        # StatusBar doesn't have user-configurable preferences
        return {}
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with preferences (currently unused)
        """
        # No preferences to apply for this panel
        pass
