"""
PyQt5 Orientation Panel for frankentrack GUI.

Displays Euler angles (Yaw, Pitch, Roll), position (X, Y, Z),
drift correction controls, and orientation reset functionality.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QPushButton, QComboBox)
from PyQt5.QtCore import Qt, QTimer

from config.config import QUEUE_PUT_TIMEOUT
from util.error_utils import safe_queue_put
from workers.gui_qt.helpers.shortcut_helper import ShortcutManager


class OrientationPanelQt(QGroupBox):
    """PyQt5 Panel for orientation and position display with drift correction."""
    
    def __init__(self, parent=None, control_queue=None, message_callback=None, padding=6):
        """
        Initialize the Orientation Panel.
        
        Args:
            parent: Parent PyQt5 widget
            control_queue: Queue for sending commands to fusion worker
            message_callback: Callable to display messages (e.g., app.append_message)
            padding: Padding for the frame (default: 6)
        """
        super().__init__("Orientation", parent)
        
        self.control_queue = control_queue
        self.message_callback = message_callback
        
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
        
        # Initialize shortcut manager
        self.shortcut_manager = ShortcutManager(self, message_callback)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the orientation panel UI."""
        # Main layout - single column for data and controls
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(4, 2, 4, 2)
        self.setLayout(main_layout)

        # Build components
        self._build_euler_displays(main_layout)
        self._build_position_displays(main_layout)
        self._build_control_row(main_layout)

    def _build_control_row(self, parent_layout):
        """Build control row with reset buttons and filter selection."""
        # Create horizontal layout for controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(6, 0, 6, 0)  # Add horizontal padding
        
        # Filter selection (left-aligned)
        filter_label = QLabel("Filter:")
        controls_layout.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['complementary', 'quaternion'])
        self.filter_combo.setCurrentText('complementary')
        self.filter_combo.currentTextChanged.connect(self._on_filter_change)
        controls_layout.addWidget(self.filter_combo)
        
        # Add stretch to push buttons to the right
        controls_layout.addStretch()
        
        # Reset orientation button (right-aligned)
        self.reset_button = QPushButton("Reset Orientation")
        self.reset_button.clicked.connect(self._on_reset)
        controls_layout.addWidget(self.reset_button)
        
        # Set shortcut button (right-aligned)
        self.shortcut_button = QPushButton("Set Shortcut...")
        self.shortcut_button.clicked.connect(self._on_set_shortcut)
        controls_layout.addWidget(self.shortcut_button)
        
        # Add the control layout to parent
        parent_layout.addLayout(controls_layout)

    def _build_euler_displays(self, parent_layout):
        """Build Euler angle (Yaw, Pitch, Roll) display row."""
        # Create grid layout for euler angles
        euler_grid = QGridLayout()
        euler_grid.setContentsMargins(6, 0, 6, 0)  # Add horizontal padding
        
        # Row 0: Yaw, Pitch, Roll
        euler_grid.addWidget(QLabel("Yaw:"), 0, 0)
        self.yaw_value_label = QLabel("0.0")
        self.yaw_value_label.setMinimumWidth(60)
        self.yaw_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.yaw_value_label, 0, 1)
        
        euler_grid.addWidget(QLabel("Pitch:"), 0, 2)
        self.pitch_value_label = QLabel("0.0")
        self.pitch_value_label.setMinimumWidth(60)
        self.pitch_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.pitch_value_label, 0, 3)
        
        euler_grid.addWidget(QLabel("Roll:"), 0, 4)
        self.roll_value_label = QLabel("0.0")
        self.roll_value_label.setMinimumWidth(60)
        self.roll_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        euler_grid.addWidget(self.roll_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(euler_grid)
    
    def _build_position_displays(self, parent_layout):
        """Build position (X, Y, Z) display row."""
        # Create grid layout for positions
        position_grid = QGridLayout()
        position_grid.setContentsMargins(6, 0, 6, 0)  # Add horizontal padding
        
        # Row 0: X, Y, Z positions
        position_grid.addWidget(QLabel("X:"), 0, 0)
        self.x_value_label = QLabel("0.00")
        self.x_value_label.setMinimumWidth(60)
        self.x_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.x_value_label, 0, 1)
        
        position_grid.addWidget(QLabel("Y:"), 0, 2)
        self.y_value_label = QLabel("0.00")
        self.y_value_label.setMinimumWidth(60)
        self.y_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.y_value_label, 0, 3)
        
        position_grid.addWidget(QLabel("Z:"), 0, 4)
        self.z_value_label = QLabel("0.00")
        self.z_value_label.setMinimumWidth(60)
        self.z_value_label.setAlignment(Qt.AlignCenter)  # Center the value
        position_grid.addWidget(self.z_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(position_grid)
    
    def _on_filter_change(self, filter_type):
        """Send filter selection change to fusion worker via control queue."""
        try:
            if self.control_queue:
                # Send tuple command: ('set_filter', 'quaternion'|'complementary')
                safe_queue_put(self.control_queue, ('set_filter', filter_type), timeout=QUEUE_PUT_TIMEOUT)
                if self.message_callback:
                    QTimer.singleShot(0, lambda msg=f"Filter changed to: {filter_type}": self.message_callback(msg))
        except Exception as ex:
            if self.message_callback:
                QTimer.singleShot(0, lambda msg=f"Failed to set filter to: {filter_type} - {ex}": self.message_callback(msg))
    
    def _on_set_shortcut(self):
        """Open dialog to capture a keyboard shortcut for reset orientation."""
        key, display_name = self.shortcut_manager.capture_shortcut(self.shortcut_manager.reset_shortcut)
        
        if key:
            # Set the shortcut with reset callback
            success = self.shortcut_manager.set_shortcut(key, display_name, self._on_reset)
            if success:
                # Update button text using timer to ensure main thread
                QTimer.singleShot(0, lambda: self.shortcut_button.setText(f"Shortcut: {display_name}"))
    
    def _on_reset(self):
        """Handle orientation reset button click."""
        # Send non-destructive orientation reset command to fusion worker.
        try:
            if self.control_queue:
                if not safe_queue_put(self.control_queue, 'reset_orientation', timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        QTimer.singleShot(0, lambda: self.message_callback("Failed to send reset command"))
                    return
        except Exception as ex:
            if self.message_callback:
                QTimer.singleShot(0, lambda msg=f"Failed to send reset command: {ex}": self.message_callback(msg))
            return

        if self.message_callback:
            QTimer.singleShot(0, lambda: self.message_callback("Orientation reset requested (from GUI)"))

        # Reset translation offsets so displayed X/Y become zero
        try:
            lx, ly, lz = self._last_raw_translation
            # Set offsets so displayed values = raw - offset = 0
            self._x_offset = float(lx)
            self._y_offset = float(ly)
            # Update displayed values to zero
            self.x_value_label.setText("0.00")
            self.y_value_label.setText("0.00")

            if self.message_callback:
                QTimer.singleShot(0, lambda: self.message_callback("Position offsets updated to make current position zero"))
        except Exception:
            pass
    
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
        # Orientation panel is now display-only, no preferences to restore
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