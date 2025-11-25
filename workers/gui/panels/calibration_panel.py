"""
Calibration Panel for frankentrack GUI.

Contains drift correction angle control, and runtime
controls for resetting orientation and recalibrating gyro bias.
"""
import tkinter as tk
from tkinter import ttk

from config.config import (
    DEFAULT_CENTER_THRESHOLD,
    THRESH_DEBOUNCE_MS,
    QUEUE_PUT_TIMEOUT,
)
from util.error_utils import safe_queue_put


class CalibrationPanel(ttk.LabelFrame):
    """Panel that groups calibration-related controls.

    This is intentionally small and self-contained so the main
    `OrientationPanel` can remain focused on display-only concerns.
    """

    def __init__(self, parent, control_queue, message_callback, padding=6):
        super().__init__(parent, text="Calibration", padding=padding)
        self.control_queue = control_queue
        self.message_callback = message_callback

        # Drift correction controls
        self.drift_angle_var = tk.DoubleVar(value=DEFAULT_CENTER_THRESHOLD)
        self.drift_angle_display = tk.StringVar(value=f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        # Status indicator for gyro calibration
        self.calib_status_var = tk.StringVar(value="Gyro: Not calibrated")
        # Debounce job id for sending drift angle updates
        self._drift_send_job = None

        self._build_ui()

    def _build_ui(self):
        # simple grid layout: label, slider+display, buttons
        for i in range(6):
            self.grid_columnconfigure(i, weight=1)
        # keep the right-most status column tight so the status_frame hugs its content
        self.grid_columnconfigure(5, weight=0)

        ttk.Label(self, text="Drift Correction Angle:", anchor="w").grid(
            row=0, column=0, columnspan=6, sticky="ew", padx=6, pady=6
        )

        # Left-aligned slider and display
        self.drift_scale = ttk.Scale(
            self,
            from_=0,
            to=25,
            orient="horizontal",
            variable=self.drift_angle_var,
            command=self._on_drift_angle_change,
        )
        # Place slider starting at column 0 so it is left-aligned
        self.drift_scale.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=6)

        ttk.Label(self, textvariable=self.drift_angle_display, width=5, anchor="w").grid(
            row=1, column=4, sticky="w", padx=(0, 12)
        )

        # Buttons left-aligned under the slider (placeholder area)
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=4, pady=(4, 6), sticky="w")

        # Right-side status area (gyro calibration indicator + recalibrate button)
        status_frame = ttk.Frame(self)
        # anchor the status frame to the top-right of the panel so it stays on the right
        status_frame.grid(row=0, column=5, rowspan=3, sticky="ne", padx=(6, 8))

        # Calibration status label (text + color changed by update_calibration_status)
        self._calib_status_lbl = ttk.Label(status_frame, textvariable=self.calib_status_var, anchor="center", justify="center")
        self._calib_status_lbl.pack(anchor="center", pady=(6, 2))

        # Place Recalibrate button directly under the calibration indicator, centered
        self.recal_btn = ttk.Button(status_frame, text="Recalibrate Gyro Bias", command=self._on_recalibrate)
        self.recal_btn.pack(anchor="center", pady=(2, 6))

    def _on_drift_angle_change(self, val):
        try:
            v = float(val)
        except Exception:
            v = 0.0

        # Quantize to 0.1 and update display immediately
        vq = round(v * 10.0) / 10.0
        self.drift_angle_display.set(f"{vq:.1f}")

        # Debounce sending updates to avoid flooding the control queue
        if self._drift_send_job is not None:
            try:
                self.after_cancel(self._drift_send_job)
            except Exception:
                pass
        self._drift_send_job = self.after(THRESH_DEBOUNCE_MS, lambda: self._apply_drift_angle(vq))

    def _on_reset(self):
        if not safe_queue_put(self.control_queue, 'reset', timeout=QUEUE_PUT_TIMEOUT):
            if self.message_callback:
                self.message_callback("Failed to send reset command")
            return

        if self.message_callback:
            self.message_callback("Orientation reset requested (from GUI)")

    def _on_recalibrate(self):
        if not safe_queue_put(self.control_queue, ('recalibrate_gyro_bias',), timeout=QUEUE_PUT_TIMEOUT):
            if self.message_callback:
                self.message_callback("Failed to send recalibration request")
            return

        if self.message_callback:
            self.message_callback("Gyro bias recalibration requested")

    
    def update_calibration_status(self, calibrated: bool):
        """Update gyro calibration status with emoji."""
        try:
            if calibrated:
                # Blue text for calibrated
                self.calib_status_var.set("Gyro: Calibrated")
                self._calib_status_lbl.configure(foreground="blue")
            else:
                # Red text for not calibrated
                self.calib_status_var.set("Gyro: Not calibrated")
                self._calib_status_lbl.configure(foreground="red")
        except Exception:
            pass

    def get_prefs(self):
        # Persist the drift angle to one decimal place
        try:
            v = round(float(self.drift_angle_var.get()) * 10.0) / 10.0
            return {'drift_angle': f"{v:.1f}"}
        except Exception:
            return {'drift_angle': f"{DEFAULT_CENTER_THRESHOLD:.1f}"}

    def set_prefs(self, prefs):
        if prefs is None:
            return
        if 'drift_angle' in prefs and prefs['drift_angle']:
            try:
                angle = float(prefs['drift_angle'])
                # Quantize to 0.1
                angle = round(angle * 10.0) / 10.0
                self.drift_angle_var.set(angle)
                self.drift_angle_display.set(f"{angle:.1f}")
                if self.control_queue:
                    safe_queue_put(self.control_queue, ('set_center_threshold', float(angle)), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

    def get_drift_angle(self):
        return self.drift_angle_var.get()

    def set_drift_angle(self, angle):
        try:
            angle = float(angle)
            angle = max(0.0, min(25.0, angle))
            # Quantize to 0.1 when programmatically setting
            angle = round(angle * 10.0) / 10.0
            self.drift_angle_var.set(angle)
            self.drift_angle_display.set(f"{angle:.1f}")
            if self.control_queue:
                safe_queue_put(self.control_queue, ('set_center_threshold', float(angle)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _apply_drift_angle(self, vq: float):
        """Send the quantized drift angle to the control queue (debounced)."""
        try:
            self._drift_send_job = None
            if self.control_queue:
                if not safe_queue_put(self.control_queue, ('set_center_threshold', float(vq)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send drift angle update")
        except Exception:
            pass
