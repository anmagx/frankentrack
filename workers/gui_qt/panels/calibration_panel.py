"""
PyQt5 Calibration Panel for frankentrack GUI.

Contains drift correction angle control, and runtime
controls for resetting orientation and recalibrating gyro bias.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QSlider, QFrame)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from config.config import (
    DEFAULT_CENTER_THRESHOLD,
    THRESH_DEBOUNCE_MS,
    QUEUE_PUT_TIMEOUT,
)
from util.error_utils import safe_queue_put


class CalibrationPanelQt(QGroupBox):
    """PyQt5 Panel that groups calibration-related controls.

    This is intentionally small and self-contained so the main
    `OrientationPanel` can remain focused on display-only concerns.
    """

    def __init__(self, parent=None, control_queue=None, message_callback=None, padding=6):
        super().__init__("Calibration", parent)
        
        self.control_queue = control_queue
        self.message_callback = message_callback

        # Drift correction controls
        self.drift_angle_value = DEFAULT_CENTER_THRESHOLD
        self.drift_angle_label = None
        
        # Status indicator for gyro calibration
        self.calib_status_label = None
        
        # Debounce timer for sending drift angle updates
        self._drift_send_timer = QTimer()
        self._drift_send_timer.setSingleShot(True)
        self._drift_send_timer.timeout.connect(self._apply_drift_angle)
        self._pending_drift_value = None

        self._build_ui()

    def _build_ui(self):
        """Build the calibration panel UI."""
        # Main layout
        main_layout = QGridLayout()
        self.setLayout(main_layout)
        
        # Configure column weights to match tkinter behavior
        for i in range(6):
            main_layout.setColumnStretch(i, 1)
        main_layout.setColumnStretch(5, 0)  # Right column tight
        
        # Drift correction angle label
        drift_label = QLabel("Drift Correction Angle:")
        drift_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(drift_label, 0, 0, 1, 6)
        
        # Drift angle slider
        self.drift_slider = QSlider(Qt.Horizontal)
        self.drift_slider.setMinimum(0)
        self.drift_slider.setMaximum(250)  # 0-25.0 with 0.1 precision
        self.drift_slider.setValue(int(DEFAULT_CENTER_THRESHOLD * 10))
        self.drift_slider.valueChanged.connect(self._on_drift_angle_change)
        main_layout.addWidget(self.drift_slider, 1, 0, 1, 4)
        
        # Drift angle display
        self.drift_angle_label = QLabel(f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        self.drift_angle_label.setMinimumWidth(40)
        self.drift_angle_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(self.drift_angle_label, 1, 4)
        
        # Button frame placeholder (left side under slider)
        btn_frame = QFrame()
        main_layout.addWidget(btn_frame, 2, 0, 1, 4)
        
        # Status frame (right side)
        status_frame = QFrame()
        status_layout = QVBoxLayout()
        status_frame.setLayout(status_layout)
        
        # Calibration status label
        self.calib_status_label = QLabel("Gyro: Not calibrated")
        self.calib_status_label.setAlignment(Qt.AlignCenter)
        self.calib_status_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.calib_status_label)
        
        # Recalibrate button
        self.recal_button = QPushButton("Recalibrate Gyro Bias")
        self.recal_button.clicked.connect(self._on_recalibrate)
        status_layout.addWidget(self.recal_button)
        
        # Add status frame to main layout (top-right)
        main_layout.addWidget(status_frame, 0, 5, 3, 1, Qt.AlignTop | Qt.AlignRight)

    def _on_drift_angle_change(self, value):
        """Handle drift angle slider changes with debouncing."""
        try:
            # Convert slider value (0-250) to float (0.0-25.0)
            v = float(value) / 10.0
        except Exception:
            v = 0.0

        # Quantize to 0.1 and update display immediately
        vq = round(v * 10.0) / 10.0
        self.drift_angle_value = vq
        self.drift_angle_label.setText(f"{vq:.1f}")

        # Store the value for debounced sending
        self._pending_drift_value = vq
        
        # Restart debounce timer
        self._drift_send_timer.stop()
        self._drift_send_timer.start(THRESH_DEBOUNCE_MS)

    def _on_reset(self):
        """Handle reset button click (if needed in future)."""
        if not safe_queue_put(self.control_queue, 'reset', timeout=QUEUE_PUT_TIMEOUT):
            if self.message_callback:
                self.message_callback("Failed to send reset command")
            return

        if self.message_callback:
            self.message_callback("Orientation reset requested (from GUI)")

    def _on_recalibrate(self):
        """Handle recalibrate gyro bias button click."""
        if not safe_queue_put(self.control_queue, ('recalibrate_gyro_bias',), timeout=QUEUE_PUT_TIMEOUT):
            if self.message_callback:
                self.message_callback("Failed to send recalibration request")
            return

        if self.message_callback:
            self.message_callback("Gyro bias recalibration requested")

    def update_calibration_status(self, calibrated):
        """Update gyro calibration status with color changes.
        
        Args:
            calibrated: Boolean indicating if gyro is calibrated
        """
        try:
            if calibrated:
                # Blue text for calibrated
                self.calib_status_label.setText("Gyro: Calibrated")
                self.calib_status_label.setStyleSheet("color: blue;")
            else:
                # Red text for not calibrated
                self.calib_status_label.setText("Gyro: Not calibrated")
                self.calib_status_label.setStyleSheet("color: red;")
        except Exception:
            pass

    def get_prefs(self):
        """Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with drift_angle preference
        """
        # Persist the drift angle to one decimal place
        try:
            v = round(float(self.drift_angle_value) * 10.0) / 10.0
            return {'drift_angle': f"{v:.1f}"}
        except Exception:
            return {'drift_angle': f"{DEFAULT_CENTER_THRESHOLD:.1f}"}

    def set_prefs(self, prefs):
        """Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional drift_angle preference
        """
        if prefs is None:
            return
        if 'drift_angle' in prefs and prefs['drift_angle']:
            try:
                angle = float(prefs['drift_angle'])
                # Quantize to 0.1
                angle = round(angle * 10.0) / 10.0
                self.set_drift_angle(angle)
            except Exception:
                pass

    def get_drift_angle(self):
        """Get current drift angle value.
        
        Returns:
            float: Current drift angle
        """
        return self.drift_angle_value

    def set_drift_angle(self, angle):
        """Set drift angle programmatically.
        
        Args:
            angle: Drift angle value (0.0-25.0)
        """
        try:
            angle = float(angle)
            angle = max(0.0, min(25.0, angle))
            # Quantize to 0.1 when programmatically setting
            angle = round(angle * 10.0) / 10.0
            
            # Update internal value and display
            self.drift_angle_value = angle
            self.drift_angle_label.setText(f"{angle:.1f}")
            
            # Update slider position
            self.drift_slider.setValue(int(angle * 10))
            
            # Send to control queue immediately (not debounced for programmatic changes)
            if self.control_queue:
                safe_queue_put(self.control_queue, ('set_center_threshold', float(angle)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _apply_drift_angle(self):
        """Send the quantized drift angle to the control queue (debounced)."""
        try:
            if self._pending_drift_value is not None and self.control_queue:
                if not safe_queue_put(self.control_queue, ('set_center_threshold', float(self._pending_drift_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send drift angle update")
                else:
                    if self.message_callback:
                        self.message_callback(f"Drift angle updated to {self._pending_drift_value:.1f}°")
                self._pending_drift_value = None
        except Exception:
            pass