"""
PyQt Status Bar for frankentrack GUI.

PyQt version of StatusBar with identical functionality to tkinter version.
Displays real-time statistics at the bottom of the window:
- Message Rate: Messages per second from IMU
- Send Rate: UDP packets per second
- Camera FPS: Camera frames per second
"""

from PyQt5.QtWidgets import QGroupBox, QLabel, QHBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .base_panel import BasePanelQt


class StatusBarQt(QGroupBox):
    """PyQt status bar displaying real-time performance metrics."""
    
    def __init__(self, parent, relief="sunken"):
        """
        Initialize the PyQt Status Bar.
        
        Args:
            parent: Parent PyQt widget (typically the main window)
            relief: Border style (not used with QGroupBox, kept for compatibility)
        """
        super().__init__("Status", parent)
        
        # Status values (same as tkinter version)
        self._msg_rate_text = "0 msg/s"
        self._send_rate_text = "0 msg/s"
        self._camera_fps_text = "0.0 fps"
        self._device_status_text = "Device status: Unknown"
        
        self.setup_ui()
    
    def setup_ui(self):
        """Build the status bar UI (mirrors tkinter layout exactly)."""
        # Create horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 12, 2)
        layout.setSpacing(12)
        
        # Message Rate (same as tkinter)
        msg_rate_label = QLabel("Message Rate:")
        msg_rate_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(msg_rate_label)
        
        self.msg_rate_value = QLabel(self._msg_rate_text)
        self.msg_rate_value.setMinimumWidth(65)  # Similar to tkinter width=12
        self.msg_rate_value.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.msg_rate_value)
        
        # Send Rate (same as tkinter)
        send_rate_label = QLabel("Send Rate:")
        send_rate_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(send_rate_label)
        
        self.send_rate_value = QLabel(self._send_rate_text)
        self.send_rate_value.setMinimumWidth(65)  # Similar to tkinter width=12
        self.send_rate_value.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.send_rate_value)
        
        # Camera FPS (same as tkinter)
        camera_fps_label = QLabel("Camera FPS:")
        camera_fps_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(camera_fps_label)
        
        self.camera_fps_value = QLabel(self._camera_fps_text)
        self.camera_fps_value.setMinimumWidth(65)  # Similar to tkinter width=12
        self.camera_fps_value.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.camera_fps_value)
        
        # Spacer to push device status to the right (same as tkinter side="right")
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(spacer)
        
        # Device movement status (right side, same as tkinter)
        self.device_status_label = QLabel(self._device_status_text)
        self.device_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.device_status_label)
    
    def update_message_rate(self, rate):
        """
        Update the message rate display (identical to tkinter).
        
        Args:
            rate: Messages per second (float)
        """
        try:
            text = f"{float(rate):.1f} msg/s"
            self._msg_rate_text = text
            self.msg_rate_value.setText(text)
        except Exception:
            pass
    
    def update_send_rate(self, rate):
        """
        Update the send rate display (identical to tkinter).
        
        Args:
            rate: Packets per second (float)
        """
        try:
            text = f"{float(rate):.1f} msg/s"
            self._send_rate_text = text
            self.send_rate_value.setText(text)
        except Exception:
            pass
    
    def update_camera_fps(self, fps):
        """
        Update the camera FPS display (identical to tkinter).
        
        Args:
            fps: Frames per second (float)
        """
        try:
            text = f"{float(fps):.1f} fps"
            self._camera_fps_text = text
            self.camera_fps_value.setText(text)
        except Exception:
            pass
    
    def update_all(self, msg_rate=None, send_rate=None, camera_fps=None):
        """
        Update multiple metrics at once (identical to tkinter).
        
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
        Update device movement status indicator (identical to tkinter).

        Args:
            stationary: True if device is stationary, False if moving
        """
        try:
            if stationary:
                text = "Device status: stationary"
            else:
                text = "Device status: moving"
            self._device_status_text = text
            self.device_status_label.setText(text)
        except Exception:
            pass

    def update_calibration_status(self, calibrated: bool):
        """
        Update gyro calibration status indicator (identical to tkinter).

        Args:
            calibrated: True if gyro yaw bias has been calibrated
        """
        # Calibration status handled by CalibrationPanel now
        return
    
    def reset(self):
        """Reset all metrics to zero (identical to tkinter)."""
        self._msg_rate_text = "0 msg/s"
        self._send_rate_text = "0 msg/s"
        self._camera_fps_text = "0.0 fps"
        
        self.msg_rate_value.setText(self._msg_rate_text)
        self.send_rate_value.setText(self._send_rate_text)
        self.camera_fps_value.setText(self._camera_fps_text)
    
    def get_values(self):
        """
        Get current displayed values (identical to tkinter).
        
        Returns:
            dict: Dictionary with 'msg_rate', 'send_rate', 'camera_fps' keys
        """
        return {
            'msg_rate': self._msg_rate_text,
            'send_rate': self._send_rate_text,
            'camera_fps': self._camera_fps_text
        }
    
    def get_prefs(self):
        """
        Get current preferences for persistence (identical to tkinter).
        
        Returns:
            dict: Empty dict (no preferences to save for this panel)
        """
        # StatusBar doesn't have user-configurable preferences
        return {}
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences (identical to tkinter).
        
        Args:
            prefs: Dictionary with preferences (currently unused)
        """
        # No preferences to apply for this panel
        pass