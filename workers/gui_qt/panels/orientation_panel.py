"""
PyQt5 Orientation Panel for frankentrack GUI.

Display-only panel showing Euler angles (Yaw, Pitch, Roll) and position (X, Y, Z).
No controls - purely for data visualization.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QSizePolicy)
from PyQt5.QtCore import Qt


class OrientationPanelQt(QGroupBox):
    """PyQt5 Panel for orientation and position display (display-only)."""
    
    def __init__(self, parent=None, control_queue=None, message_callback=None, padding=6):
        """
        Initialize the Orientation Panel.
        
        Args:
            parent: Parent PyQt5 widget
            control_queue: Not used (display-only panel)
            message_callback: Not used (display-only panel) 
            padding: Padding for the frame (default: 6)
        """
        super().__init__("Orientation", parent)
        
        # Euler angle display labels
        self.yaw_value_label = None
        self.pitch_value_label = None
        self.roll_value_label = None
        
        # Position display labels  
        self.x_value_label = None
        self.y_value_label = None
        self.z_value_label = None
        
        # Position offset tracking (for reset functionality)
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the orientation panel UI."""
        # Main layout - single column for data displays only
        main_layout = QVBoxLayout()
        # Add modest vertical padding inside the panel to match other panels
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(4, 6, 4, 6)
        self.setLayout(main_layout)
        
        # Allow panel to expand vertically to fill available space when appropriate
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Build display components
        self._build_euler_displays(main_layout)
        self._build_position_displays(main_layout)

    def _build_euler_displays(self, parent_layout):
        """Build Euler angle (Yaw, Pitch, Roll) display row."""
        # Create grid layout for euler angles
        euler_grid = QGridLayout()
        euler_grid.setContentsMargins(6, 4, 6, 4)  # Add horizontal + vertical padding
        
        # Row 0: Yaw, Pitch, Roll
        euler_grid.addWidget(QLabel("Yaw:"), 0, 0)
        self.yaw_value_label = QLabel("0.0")
        self.yaw_value_label.setMinimumWidth(50)
        self.yaw_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.yaw_value_label, 0, 1)
        
        euler_grid.addWidget(QLabel("Pitch:"), 0, 2)
        self.pitch_value_label = QLabel("0.0")
        self.pitch_value_label.setMinimumWidth(50)
        self.pitch_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.pitch_value_label, 0, 3)
        
        euler_grid.addWidget(QLabel("Roll:"), 0, 4)
        self.roll_value_label = QLabel("0.0")
        self.roll_value_label.setMinimumWidth(50)
        self.roll_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.roll_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(euler_grid)
    
    def _build_position_displays(self, parent_layout):
        """Build position (X, Y, Z) display row."""
        # Create grid layout for positions
        position_grid = QGridLayout()
        position_grid.setContentsMargins(6, 4, 6, 4)  # Add horizontal + vertical padding
        
        # Row 0: X, Y, Z positions
        position_grid.addWidget(QLabel("X:"), 0, 0)
        self.x_value_label = QLabel("0.00")
        self.x_value_label.setMinimumWidth(50)
        self.x_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.x_value_label, 0, 1)
        
        position_grid.addWidget(QLabel("Y:"), 0, 2)
        self.y_value_label = QLabel("0.00")
        self.y_value_label.setMinimumWidth(50)
        self.y_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.y_value_label, 0, 3)
        
        position_grid.addWidget(QLabel("Z:"), 0, 4)
        self.z_value_label = QLabel("0.00")
        self.z_value_label.setMinimumWidth(50)
        self.z_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.z_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(position_grid)
    
    def update_euler(self, yaw, pitch, roll):
        """
        Update Euler angle displays and visualization.
        
        Args:
            yaw: Yaw angle in degrees
            pitch: Pitch angle in degrees
            roll: Roll angle in degrees
        """
        try:
            self.yaw_value_label.setText(f"{float(yaw):.1f}")
            self.pitch_value_label.setText(f"{float(pitch):.1f}")
            self.roll_value_label.setText(f"{float(roll):.1f}")
            
            # Update calibration panel visualization if connected
            if hasattr(self, 'calibration_panel') and self.calibration_panel:
                self.calibration_panel.update_orientation(pitch, yaw, roll)
        except Exception:
            pass

    def update_position(self, x, y, z):
        """
        Update position display with offset handling.
        
        Args:
            x: X position
            y: Y position  
            z: Z position
        """
        try:
            # Apply position offsets
            adjusted_x = x - self._x_offset
            adjusted_y = y - self._y_offset
            
            # Store raw translation for offset calculations
            self._last_raw_translation = (x, y, z)
            
            # Update display labels
            if self.x_value_label:
                self.x_value_label.setText(f"{adjusted_x:.2f}")
            if self.y_value_label:
                self.y_value_label.setText(f"{adjusted_y:.2f}")
            if self.z_value_label:
                self.z_value_label.setText(f"{z:.2f}")
        except Exception:
            pass
    
    def update_drift_status(self, active):
        """
        Update drift correction status in calibration panel.
        
        Args:
            active: Boolean indicating if drift correction is active
        """
        try:
            # Update calibration panel visualization if connected
            if hasattr(self, 'calibration_panel') and self.calibration_panel:
                self.calibration_panel.update_drift_status(active)
        except Exception:
            pass
    

    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with empty preferences (orientation panel is display-only)
        """
        return {}
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional preference keys (orientation panel is display-only)
        """
        # Orientation panel is display-only, no preferences to restore
        pass
    
    def reset_position_offsets(self):
        """Reset position offsets to zero (for testing or manual reset)."""
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        self.x_value_label.setText("0.00")
        self.y_value_label.setText("0.00")
        self.z_value_label.setText("0.00")
    
    def connect_calibration_panel(self, calibration_panel):
        """
        Connect to the calibration panel for visualization updates.
        
        Args:
            calibration_panel: CalibrationPanelQt instance with visualization widget
        """
        # Store reference to calibration panel
        self.calibration_panel = calibration_panel