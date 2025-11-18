"""
Orientation Panel for Acceltrack GUI.

Displays Euler angles (Yaw, Pitch, Roll), position (X, Y, Z),
drift correction controls, and orientation reset functionality.
"""
import tkinter as tk
from tkinter import ttk

from config.config import (
    DEFAULT_CENTER_THRESHOLD,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put


class OrientationPanel(ttk.LabelFrame):
    """Panel for orientation and position display with drift correction."""
    
    def __init__(self, parent, control_queue, message_callback, padding=6):
        """
        Initialize the Orientation Panel.
        
        Args:
            parent: Parent tkinter widget
            control_queue: Queue for sending commands to fusion worker
            message_callback: Callable to display messages (e.g., app.append_message)
            padding: Padding for the frame (default: 6)
        """
        super().__init__(parent, text="Orientation", padding=padding)
        
        self.control_queue = control_queue
        self.message_callback = message_callback
        
        # Euler angle display variables
        self.yaw_var = tk.StringVar(value="0.0")
        self.pitch_var = tk.StringVar(value="0.0")
        self.roll_var = tk.StringVar(value="0.0")
        
        # Position display variables
        self.x_var = tk.StringVar(value="0.00")
        self.y_var = tk.StringVar(value="0.00")
        self.z_var = tk.StringVar(value="0.00")
        
        # Position offset tracking (for reset functionality)
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        
        # Drift correction controls
        self.drift_angle_var = tk.DoubleVar(value=DEFAULT_CENTER_THRESHOLD)
        self.drift_angle_display = tk.StringVar(value=f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        self.drift_status_var = tk.StringVar(value="Drift Correction Inactive")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the orientation panel UI."""
        # Main container with left and right sections
        container = ttk.Frame(self)
        container.pack(fill="x", expand=True)
        
        # Left section: Data displays and drift slider
        left_frame = ttk.Frame(container)
        left_frame.pack(side="left", fill="both", expand=True)
        
        # Right section: Status and reset button
        right_frame = ttk.Frame(container)
        right_frame.pack(side="right", fill="y")
        
        # Build left section components
        self._build_euler_displays(left_frame)
        self._build_position_displays(left_frame)
        self._build_drift_control(left_frame)
        
        # Build right section components
        self._build_drift_status(right_frame)
        self._build_reset_button(right_frame)
    
    def _build_euler_displays(self, parent):
        """Build Euler angle (Yaw, Pitch, Roll) display row."""
        # Row 0: Yaw, Pitch, Roll
        ttk.Label(parent, text="Yaw:").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.yaw_var, width=8).grid(
            row=0, column=1, sticky="w", padx=(0, 12)
        )
        
        ttk.Label(parent, text="Pitch:").grid(
            row=0, column=2, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.pitch_var, width=8).grid(
            row=0, column=3, sticky="w", padx=(0, 12)
        )
        
        ttk.Label(parent, text="Roll:").grid(
            row=0, column=4, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.roll_var, width=8).grid(
            row=0, column=5, sticky="w", padx=(0, 12)
        )
    
    def _build_position_displays(self, parent):
        """Build position (X, Y, Z) display row."""
        # Row 1: X, Y, Z positions
        ttk.Label(parent, text="X:").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.x_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(0, 12)
        )
        
        ttk.Label(parent, text="Y:").grid(
            row=1, column=2, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.y_var, width=8).grid(
            row=1, column=3, sticky="w", padx=(0, 12)
        )
        
        ttk.Label(parent, text="Z:").grid(
            row=1, column=4, sticky="w", padx=6, pady=4
        )
        ttk.Label(parent, textvariable=self.z_var, width=8).grid(
            row=1, column=5, sticky="w", padx=(0, 12)
        )
    
    def _build_drift_control(self, parent):
        """Build drift correction angle slider."""
        # Row 2: Drift correction slider
        ttk.Label(parent, text="Drift Correction Angle:").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=6
        )
        
        self.drift_scale = tk.Scale(
            parent,
            from_=0,
            to=25,
            orient="horizontal",
            length=220,
            variable=self.drift_angle_var,
            command=self._on_drift_angle_change
        )
        self.drift_scale.grid(
            row=2, column=2, columnspan=3, sticky="w", padx=6, pady=6
        )
        
        ttk.Label(parent, textvariable=self.drift_angle_display, width=4).grid(
            row=2, column=5, sticky="w", padx=(0, 12)
        )
    
    def _build_drift_status(self, parent):
        """Build drift correction status indicator."""
        self.drift_status_lbl = ttk.Label(
            parent,
            textvariable=self.drift_status_var,
            foreground="red"
        )
        self.drift_status_lbl.pack(padx=6, pady=(6, 4))
    
    def _build_reset_button(self, parent):
        """Build orientation reset button."""
        self.reset_btn = ttk.Button(
            parent,
            text="Reset Orientation",
            command=self._on_reset
        )
        self.reset_btn.pack(padx=6, pady=(4, 6))
    
    def _on_drift_angle_change(self, val):
        """Handle drift angle slider changes."""
        try:
            v = float(val)
        except Exception:
            v = 0.0
        
        self.drift_angle_display.set(f"{v:.1f}")
        
        # Send new threshold to fusion worker
        if not safe_queue_put(
            self.control_queue,
            ('set_center_threshold', float(v)),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            if self.message_callback:
                self.message_callback("Failed to send drift angle update")
    
    def _on_reset(self):
        """Handle orientation reset button click."""
        # Send reset command to fusion worker
        if not safe_queue_put(self.control_queue, 'reset', timeout=QUEUE_PUT_TIMEOUT):
            if self.message_callback:
                self.message_callback("Failed to send reset command")
            return
        
        if self.message_callback:
            self.message_callback("Orientation reset requested (from GUI)")
        
        # Reset translation offsets so displayed X/Y become zero
        try:
            lx, ly, lz = self._last_raw_translation
            # Set offsets so displayed values = raw - offset = 0
            self._x_offset = float(lx)
            self._y_offset = float(ly)
            # Update displayed values to zero
            self.x_var.set("0.00")
            self.y_var.set("0.00")
            
            if self.message_callback:
                self.message_callback("Position offsets updated to make current position zero")
        except Exception:
            pass
    
    def update_euler(self, yaw, pitch, roll):
        """
        Update Euler angle displays.
        
        Args:
            yaw: Yaw angle in degrees
            pitch: Pitch angle in degrees
            roll: Roll angle in degrees
        """
        try:
            self.yaw_var.set(f"{float(yaw):.1f}")
            self.pitch_var.set(f"{float(pitch):.1f}")
            self.roll_var.set(f"{float(roll):.1f}")
        except Exception:
            pass
    
    def update_position(self, x, y, z):
        """
        Update position displays with offset applied.
        
        Args:
            x: X position (raw)
            y: Y position (raw)
            z: Z position (raw)
        """
        try:
            # Store raw translation for reset functionality
            self._last_raw_translation = (float(x), float(y), float(z))
            
            # Apply offsets
            dx = float(x) - self._x_offset
            dy = float(y) - self._y_offset
            dz = float(z)
            
            # Update displays
            self.x_var.set(f"{dx:.2f}")
            self.y_var.set(f"{dy:.2f}")
            self.z_var.set(f"{dz:.2f}")
        except Exception:
            pass
    
    def update_drift_status(self, active):
        """
        Update drift correction status indicator.
        
        Args:
            active: Boolean indicating if drift correction is active
        """
        try:
            if active:
                self.drift_status_var.set("Drift Correction Active")
                self.drift_status_lbl.configure(foreground="blue")
            else:
                self.drift_status_var.set("Drift Correction Inactive")
                self.drift_status_lbl.configure(foreground="red")
        except Exception:
            pass
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with 'drift_angle' key
        """
        return {
            'drift_angle': str(self.drift_angle_var.get())
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional 'drift_angle' key
        """
        if prefs is None:
            return
        
        if 'drift_angle' in prefs and prefs['drift_angle']:
            try:
                angle = float(prefs['drift_angle'])
                self.drift_angle_var.set(angle)
                self.drift_angle_display.set(f"{angle:.1f}")
                
                # Send to fusion worker
                if self.control_queue:
                    safe_queue_put(
                        self.control_queue,
                        ('set_center_threshold', angle),
                        timeout=QUEUE_PUT_TIMEOUT
                    )
            except Exception:
                pass
    
    def reset_position_offsets(self):
        """Reset position offsets to zero (for testing or manual reset)."""
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        self.x_var.set("0.00")
        self.y_var.set("0.00")
        self.z_var.set("0.00")
    
    def get_drift_angle(self):
        """
        Get current drift correction angle.
        
        Returns:
            float: Current drift angle setting
        """
        return self.drift_angle_var.get()
    
    def set_drift_angle(self, angle):
        """
        Set drift correction angle programmatically.
        
        Args:
            angle: Drift angle in degrees (0-25)
        """
        try:
            angle = float(angle)
            angle = max(0.0, min(25.0, angle))  # Clamp to valid range
            self.drift_angle_var.set(angle)
            self.drift_angle_display.set(f"{angle:.1f}")
            
            # Send to fusion worker
            if self.control_queue:
                safe_queue_put(
                    self.control_queue,
                    ('set_center_threshold', angle),
                    timeout=QUEUE_PUT_TIMEOUT
                )
        except Exception:
            pass
