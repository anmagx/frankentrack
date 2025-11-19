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
        self.device_status_var = tk.StringVar(value="Unknown")
        self.calib_status_var = tk.StringVar(value="Not calibrated")
        
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
        
        # Device movement status
        self._device_status_lbl = tk.Label(self, textvariable=self.device_status_var, width=20, bg="yellow")
        self._device_status_lbl.pack(side="left", padx=(12, 8))
        # Calibration status
        self._calib_status_lbl = tk.Label(self, textvariable=self.calib_status_var, width=18, bg="red")
        self._calib_status_lbl.pack(side="left", padx=(6, 8))
    
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

    def update_device_status(self, stationary: bool):
        """
        Update device movement status indicator.

        Args:
            stationary: True if device is stationary, False if moving
        """
        try:
            if stationary:
                self.device_status_var.set("Device: Stationary")
                self._device_status_lbl.configure(bg="green")
            else:
                self.device_status_var.set("Device: Moving")
                self._device_status_lbl.configure(bg="yellow")
        except Exception:
            pass

    def update_calibration_status(self, calibrated: bool):
        """
        Update gyro calibration status indicator.

        Args:
            calibrated: True if gyro yaw bias has been calibrated
        """
        try:
            if calibrated:
                self.calib_status_var.set("Gyro: Calibrated")
                self._calib_status_lbl.configure(bg="green")
            else:
                self.calib_status_var.set("Gyro: Not calibrated")
                self._calib_status_lbl.configure(bg="red")
        except Exception:
            pass
    
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
