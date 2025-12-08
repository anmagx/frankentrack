"""
PyQt5 Calibration Panel for frankentrack GUI.

Contains drift correction angle control, and runtime
controls for resetting orientation and recalibrating gyro bias.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QSlider, QFrame, QWidget, QComboBox, QDialog, QApplication, QShortcut)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QKeySequence

import math

# Try to import pygame for gamepad/joystick support
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

from config.config import (
    DEFAULT_CENTER_THRESHOLD,
    THRESH_DEBOUNCE_MS,
    QUEUE_PUT_TIMEOUT,
    VISUALIZATION_RANGE,
    VISUALIZATION_SIZE
)
from util.error_utils import safe_queue_put
from workers.gui_qt.helpers.shortcut_helper import ShortcutManager


class InputCaptureThread(QThread):
    """Thread to capture gamepad/joystick inputs without blocking the UI."""
    
    input_captured = pyqtSignal(str, str)  # (key_id, display_name)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        
    def run(self):
        """Run the input capture loop."""
        if not PYGAME_AVAILABLE:
            return
            
        try:
            # Initialize pygame without setting environment variables to avoid Qt conflicts
            pygame.mixer.quit()  # Disable sound to reduce conflicts
            pygame.init()
            
            # Only initialize joystick subsystem
            if pygame.get_init():
                pygame.joystick.init()
            else:
                return
            
            # Get list of connected joysticks
            joystick_count = pygame.joystick.get_count()
            joysticks = []
            
            for i in range(joystick_count):
                joy = pygame.joystick.Joystick(i)
                joy.init()
                joysticks.append(joy)
            
            self.running = True
            clock = pygame.time.Clock()
            
            while self.running:
                pygame.event.pump()
                
                # Check each joystick for button presses
                for i, joystick in enumerate(joysticks):
                    # Check buttons
                    for button_id in range(joystick.get_numbuttons()):
                        if joystick.get_button(button_id):
                            joy_name = joystick.get_name()
                            key_id = f"joy{i}_button{button_id}"
                            display_name = f"{joy_name} Button {button_id + 1}"
                            self.input_captured.emit(key_id, display_name)
                            self.running = False
                            return
                    
                    # Check hat (D-pad) inputs
                    for hat_id in range(joystick.get_numhats()):
                        hat = joystick.get_hat(hat_id)
                        if hat != (0, 0):  # Any direction pressed
                            joy_name = joystick.get_name()
                            direction = ""
                            if hat[0] == -1: direction += "Left"
                            elif hat[0] == 1: direction += "Right"
                            if hat[1] == -1: direction += "Down"
                            elif hat[1] == 1: direction += "Up"
                            
                            key_id = f"joy{i}_hat{hat_id}_{hat[0]}_{hat[1]}"
                            display_name = f"{joy_name} D-pad {direction}"
                            self.input_captured.emit(key_id, display_name)
                            self.running = False
                            return
                
                clock.tick(60)  # 60 FPS polling
                
        except Exception as e:
            # Silently handle input capture errors
            pass
        finally:
            try:
                if pygame.get_init():
                    pygame.quit()
            except Exception:
                pass
    
    def stop(self):
        """Stop the capture thread."""
        self.running = False


class KeyCaptureDialog(QDialog):
    """Simple dialog to capture a single keyboard key."""
    
    def __init__(self, parent=None, current_key=None):
        super().__init__(parent)
        self.setWindowTitle("Capture Reset Shortcut")
        self.setModal(True)
        self.resize(300, 150)
        
        # Apply dark mode styling if parent uses dark theme
        if parent:
            # Check if parent is using dark theme by examining background color
            bg_color = parent.palette().color(parent.backgroundRole())
            is_dark = bg_color.value() < 128
            
            if is_dark:
                # Apply dark theme stylesheet
                dark_style = """
                QDialog {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QLabel {
                    color: #ffffff;
                    background-color: transparent;
                }
                QLabel[status="disabled"] {
                    color: #888888;
                }
                """
                self.setStyleSheet(dark_style)
        
        # Center dialog over parent
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 300) // 2
            y = parent_geo.y() + (parent_geo.height() - 120) // 2
            self.move(x, y)
        
        self.captured_key = current_key if current_key and current_key != 'None' else None
        self.display_name = None
        
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel("Press any key or gamepad button to set as shortcut:")
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)
        
        # Additional info
        info_label = QLabel("(Keyboard, gamepad buttons, or D-pad supported)\\n(Esc to cancel)")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        if current_key and current_key != 'None':
            layout.addWidget(QLabel(f"Current: {current_key}"))
            
        self.status_label = QLabel("Waiting for input...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        
        # Start gamepad capture thread
        if PYGAME_AVAILABLE:
            try:
                self.capture_thread = InputCaptureThread()
                self.capture_thread.input_captured.connect(self._on_gamepad_input)
                self.capture_thread.start()
            except Exception:
                self.capture_thread = None
                self.status_label.setText("Gamepad support not available")
        else:
            self.capture_thread = None
            self.status_label.setText("Gamepad support not available")
    
    def _on_gamepad_input(self, key_id, display_name):
        """Handle gamepad input capture."""
        self.captured_key = key_id
        self.display_name = display_name
        self.status_label.setText(f"Captured: {display_name}")
        QApplication.processEvents()
        QTimer.singleShot(500, self.accept)
    
    def closeEvent(self, event):
        """Clean up when dialog closes."""
        if hasattr(self, 'capture_thread') and self.capture_thread:
            try:
                self.capture_thread.stop()
                self.capture_thread.wait(1000)  # Wait up to 1 second
            except Exception:
                pass
        super().closeEvent(event)
    
    def keyPressEvent(self, event):
        """Capture the pressed key."""
        key = event.key()
        
        # ESC to cancel
        if key == 0x01000000:  # Qt.Key_Escape
            self.reject()
            return
            
        # Map numpad keys to their string representations
        numpad_keys = {
            0x01000030: 'KP_0',  # Qt.Key_0 on numpad
            0x01000031: 'KP_1',  # Qt.Key_1 on numpad
            0x01000032: 'KP_2',
            0x01000033: 'KP_3',
            0x01000034: 'KP_4',
            0x01000035: 'KP_5',
            0x01000036: 'KP_6',
            0x01000037: 'KP_7',
            0x01000038: 'KP_8',
            0x01000039: 'KP_9',
            0x01000041: 'KP_Decimal',  # Qt.Key_Period on numpad
            0x01000042: 'KP_Divide',
            0x01000043: 'KP_Multiply',
            0x01000044: 'KP_Subtract',
            0x01000045: 'KP_Add',
            0x01000046: 'KP_Enter',    # Qt.Key_Enter on numpad
        }
        
        # Check if it's a numpad key
        if key in numpad_keys:
            self.captured_key = numpad_keys[key]
            self.display_name = f"Numpad {numpad_keys[key][3:]}"
        else:
            # For regular keys, use the text
            text = event.text()
            if text and text.isprintable():
                self.captured_key = text.lower()
                self.display_name = text.upper()
            else:
                # Special keys like F1-F12, Space, etc.
                key_name = QKeySequence(key).toString()
                if key_name:
                    self.captured_key = key_name.lower()
                    self.display_name = key_name
                else:
                    self.status_label.setText("Unsupported key, try another")
                    return
        
        self.status_label.setText(f"Captured: {self.display_name}")
        QTimer.singleShot(500, self.accept)


class GamepadMonitorThread(QThread):
    """Thread to monitor gamepad inputs for reset shortcut activation."""
    
    shortcut_triggered = pyqtSignal()
    
    def __init__(self, key_id, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.running = False
        
        # Parse the key_id to get joystick and button/hat info
        self.joy_id = None
        self.button_id = None
        self.hat_id = None
        self.hat_value = None
        
        if key_id.startswith("joy") and "_button" in key_id:
            # Format: joy0_button3
            parts = key_id.split("_")
            self.joy_id = int(parts[0][3:])  # Remove "joy" prefix
            self.button_id = int(parts[1][6:])  # Remove "button" prefix
        elif key_id.startswith("joy") and "_hat" in key_id:
            # Format: joy0_hat0_1_0
            parts = key_id.split("_")
            self.joy_id = int(parts[0][3:])
            self.hat_id = int(parts[1][3:])  # Remove "hat" prefix
            self.hat_value = (int(parts[2]), int(parts[3]))
    
    def run(self):
        """Monitor for the specific gamepad input."""
        if not PYGAME_AVAILABLE or self.joy_id is None:
            return
            
        try:
            # Initialize pygame without setting environment variables to avoid Qt conflicts
            pygame.mixer.quit()  # Disable sound to reduce conflicts
            pygame.init()
            
            # Only initialize joystick subsystem
            if pygame.get_init():
                pygame.joystick.init()
            else:
                return
            
            if pygame.joystick.get_count() <= self.joy_id:
                return  # Joystick not connected
            
            joystick = pygame.joystick.Joystick(self.joy_id)
            joystick.init()
            
            self.running = True
            clock = pygame.time.Clock()
            
            while self.running:
                pygame.event.pump()
                
                triggered = False
                
                if self.button_id is not None:
                    # Monitor button press
                    if self.button_id < joystick.get_numbuttons():
                        if joystick.get_button(self.button_id):
                            triggered = True
                elif self.hat_id is not None and self.hat_value is not None:
                    # Monitor hat/D-pad press
                    if self.hat_id < joystick.get_numhats():
                        current_hat = joystick.get_hat(self.hat_id)
                        if current_hat == self.hat_value:
                            triggered = True
                
                if triggered:
                    self.shortcut_triggered.emit()
                    # Small delay to prevent rapid firing
                    self.msleep(200)
                
                clock.tick(30)  # 30 FPS for monitoring
                
        except Exception as e:
            # Silently handle gamepad monitor errors
            pass
        finally:
            try:
                if pygame.get_init():
                    pygame.quit()
            except Exception:
                pass
    
    def stop(self):
        """Stop monitoring."""
        self.running = False


class OrientationVisualizationWidget(QWidget):
    """Real-time visualization of pitch, yaw, and roll orientation."""
    
    def __init__(self, parent=None, range_degrees=None):
        """
        Initialize the orientation visualization.
        
        Args:
            parent: Parent widget
            range_degrees: +/- range for pitch/yaw axes in degrees (defaults to config value)
        """
        super().__init__(parent)
        # Use config value if not specified, allows for dynamic updates
        self.range_degrees = range_degrees if range_degrees is not None else VISUALIZATION_RANGE
        self.setFixedSize(VISUALIZATION_SIZE, VISUALIZATION_SIZE)
        
        # Current orientation values
        self.pitch = 0.0
        self.yaw = 0.0
        self.roll = 0.0
        
        # Drift correction status
        self.drift_correction_active = False
        self.drift_angle_yaw = 5.0  # Default yaw drift angle in degrees
        self.drift_angle_pitch = 5.0  # Default pitch drift angle in degrees
        self.drift_angle_roll = 5.0  # Default roll drift angle in degrees
        
        # Widget appearance
        self.setStyleSheet("background-color: black; border: 1px solid gray;")
    
    def update_orientation(self, pitch, yaw, roll):
        """
        Update the visualization with new orientation data.
        
        Args:
            pitch: Pitch angle in degrees
            yaw: Yaw angle in degrees  
            roll: Roll angle in degrees
        """
        self.pitch = float(pitch)
        self.yaw = float(yaw)
        self.roll = float(roll)
        self.update()  # Trigger repaint
    
    def update_drift_correction(self, active):
        """
        Update the drift correction status.
        
        Args:
            active: Boolean indicating if drift correction is active
        """
        self.drift_correction_active = bool(active)
        self.update()  # Trigger repaint
    
    def update_drift_angle_yaw(self, angle):
        """
        Update the yaw drift angle for ellipse calculation.
        
        Args:
            angle: Yaw drift angle in degrees
        """
        self.drift_angle_yaw = float(angle)
        self.update()  # Trigger repaint
    
    def update_drift_angle_pitch(self, angle):
        """
        Update the pitch drift angle for ellipse calculation.
        
        Args:
            angle: Pitch drift angle in degrees
        """
        self.drift_angle_pitch = float(angle)
        self.update()  # Trigger repaint
    
    def update_drift_angle_roll(self, angle):
        """
        Update the roll drift angle for ellipse calculation.
        
        Args:
            angle: Roll drift angle in degrees
        """
        self.drift_angle_roll = float(angle)
        self.update()  # Trigger repaint

    def paintEvent(self, event):
        """
        Draw the orientation visualization.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get widget center and size
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Draw coordinate system
        self._draw_coordinate_system(painter, center_x, center_y, width, height)
        
        # Draw orientation indicator
        self._draw_orientation_indicator(painter, center_x, center_y, width, height)
        
        # Draw drift correction circle
        self._draw_drift_correction_circle(painter, center_x, center_y)
    
    def _get_theme_colors(self):
        """
        Get theme-appropriate colors based on current application style.
        
        Returns:
            dict: Dictionary of color values for different elements
        """
        # Try to detect if we're in dark mode by checking widget background
        bg_color = self.palette().color(self.backgroundRole())
        is_dark = bg_color.value() < 128  # Dark if background is dark
        
        if is_dark:
            return {
                'grid': QColor(80, 80, 80),
                'axis': QColor(160, 160, 160),
                'text': QColor(200, 200, 200),
                'center': QColor(255, 255, 255),
                'within_threshold': QColor(100, 150, 255),  # Blue
                'outside_threshold': QColor(100, 255, 100),  # Green
                'drift_active': QColor(255, 100, 100),  # Red
                'drift_inactive': QColor(100, 100, 100)  # Gray
            }
        else:
            return {
                'grid': QColor(200, 200, 200),
                'axis': QColor(100, 100, 100),
                'text': QColor(50, 50, 50),
                'center': QColor(0, 0, 0),
                'within_threshold': QColor(0, 50, 200),  # Dark Blue
                'outside_threshold': QColor(0, 150, 0),  # Dark Green
                'drift_active': QColor(200, 0, 0),  # Dark Red
                'drift_inactive': QColor(150, 150, 150)  # Light Gray
            }
            
    
    def _draw_coordinate_system(self, painter, center_x, center_y, width, height):
        """
        Draw the coordinate grid and axes.
        """
        colors = self._get_theme_colors()
        
        # Get current range from config (allows dynamic updates)
        current_range = VISUALIZATION_RANGE
        
        # Grid lines
        painter.setPen(QPen(colors['grid'], 1))
        
        # Vertical grid lines
        for i in range(-2, 3):  
            if i != 0:
                x = center_x + i * (width // 5)
                if 5 <= x <= width - 5:
                    painter.drawLine(x, 5, x, height - 5)
        
        # Horizontal grid lines  
        for i in range(-2, 3):  
            if i != 0:
                y = center_y + i * (height // 5)
                if 5 <= y <= height - 5:
                    painter.drawLine(5, y, width - 5, y)
        
        # Center axes
        painter.setPen(QPen(colors['axis'], 2))
        painter.drawLine(center_x, 5, center_x, height - 5)  # Vertical axis
        painter.drawLine(5, center_y, width - 5, center_y)   # Horizontal axis
        
        # Corner range labels (use current config value)
        painter.setPen(QPen(colors['text'], 1))
        painter.drawText(5, 15, f"{current_range:.0f}")
        painter.drawText(width - 25, 15, f"{current_range:.0f}")
        painter.drawText(5, height - 5, f"{-current_range:.0f}")
        painter.drawText(width - 30, height - 5, f"{-current_range:.0f}")
    
    def _draw_orientation_indicator(self, painter, center_x, center_y, width, height):
        """
        Draw the orientation indicator line with color based on threshold status.
        Blue when all angles are within their respective thresholds, green when outside.
        """
        colors = self._get_theme_colors()
        
        # Get current range from config (allows dynamic updates)
        current_range = VISUALIZATION_RANGE
        
        # Calculate position based on pitch/yaw
        # Yaw maps to X axis, Pitch maps to Y axis
        yaw_ratio = max(-1.0, min(1.0, -self.yaw / current_range))  # Negate yaw
        pitch_ratio = max(-1.0, min(1.0, self.pitch / current_range))
        
        indicator_x = center_x + yaw_ratio * (width // 2 - 10)
        indicator_y = center_y + pitch_ratio * (height // 2 - 10)
        
        # Calculate line endpoints based on roll angle
        roll_rad = math.radians(self.roll)
        line_length = 20
        
        start_x = indicator_x - line_length * math.cos(roll_rad)
        start_y = indicator_y - line_length * math.sin(roll_rad)
        end_x = indicator_x + line_length * math.cos(roll_rad)
        end_y = indicator_y + line_length * math.sin(roll_rad)
        
        # Check if all angles are within their respective thresholds
        def _angle_diff(a, b):
            diff = abs(a - b)
            return min(diff, 360 - diff)
        
        yaw_within = _angle_diff(self.yaw, 0) < self.drift_angle_yaw
        pitch_within = _angle_diff(self.pitch, 0) < self.drift_angle_pitch
        roll_within = _angle_diff(self.roll, 0) < self.drift_angle_roll
        
        all_within_threshold = yaw_within and pitch_within and roll_within
        
        # Choose line color: blue if within all thresholds, green if outside
        if all_within_threshold:
            line_color = colors['within_threshold']
        else:
            line_color = colors['outside_threshold']
        
        # Draw orientation line
        painter.setPen(QPen(line_color, 3))
        painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))
        
        # Draw center dot
        painter.setPen(QPen(colors['center'], 2))
        painter.drawEllipse(int(indicator_x - 3), int(indicator_y - 3), 6, 6)
    
    def _draw_drift_correction_circle(self, painter, center_x, center_y):
        """
        Draw the drift correction status ellipse at the center.
        Ellipse size corresponds to the yaw and pitch drift correction angles scaled to coordinate system.
        Forms a circle when yaw and pitch angles are equal, ellipse when different.
        Red outline at all times, blue filled when drift correction is active.
        """
        colors = self._get_theme_colors()
        
        # Get current range and size from config (allows dynamic updates)
        current_range = VISUALIZATION_RANGE
        current_size = VISUALIZATION_SIZE
        
        # Calculate radii based on drift angles (scale to visualization coordinate system)
        widget_size = min(current_size, self.height())
        usable_radius = (widget_size // 2) - 10  # Usable radius in pixels (margin for edges)
        pixels_per_degree = usable_radius / current_range  # Pixels per degree
        
        # Convert drift angles directly to pixels
        # Yaw maps to horizontal (width), pitch maps to vertical (height)
        ellipse_width_pixels = int(self.drift_angle_yaw * pixels_per_degree * 2)  # Full width
        ellipse_height_pixels = int(self.drift_angle_pitch * pixels_per_degree * 2)  # Full height
        
        # Ensure minimum visibility and maximum size
        ellipse_width_pixels = max(4, min(ellipse_width_pixels, usable_radius * 2))
        ellipse_height_pixels = max(4, min(ellipse_height_pixels, usable_radius * 2))
        
        # Calculate ellipse rectangle
        ellipse_rect_x = center_x - ellipse_width_pixels // 2
        ellipse_rect_y = center_y - ellipse_height_pixels // 2
        
        if self.drift_correction_active:
            # Active: Blue filled with red outline
            painter.setBrush(QColor(100, 150, 255, 100))  # Semi-transparent blue fill
            painter.setPen(QPen(QColor(255, 50, 50), 2))  # Red outline
            painter.drawEllipse(ellipse_rect_x, ellipse_rect_y, ellipse_width_pixels, ellipse_height_pixels)
        else:
            # Inactive: Red outline only
            painter.setBrush(Qt.NoBrush)  # No fill
            painter.setPen(QPen(QColor(255, 50, 50), 2))  # Red outline
            painter.drawEllipse(ellipse_rect_x, ellipse_rect_y, ellipse_width_pixels, ellipse_height_pixels)


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
        self.drift_angle_yaw_value = DEFAULT_CENTER_THRESHOLD
        self.drift_angle_pitch_value = DEFAULT_CENTER_THRESHOLD
        self.drift_angle_roll_value = DEFAULT_CENTER_THRESHOLD
        self.drift_angle_yaw_label = None
        self.drift_angle_pitch_label = None
        self.drift_angle_roll_label = None
        
        # Status indicator for gyro calibration
        self.calib_status_label = None
        
        # Debounce timers for sending drift angle updates
        self._drift_yaw_send_timer = QTimer()
        self._drift_yaw_send_timer.setSingleShot(True)
        self._drift_yaw_send_timer.timeout.connect(self._apply_drift_angle_yaw)
        self._pending_drift_yaw_value = None
        
        self._drift_pitch_send_timer = QTimer()
        self._drift_pitch_send_timer.setSingleShot(True)
        self._drift_pitch_send_timer.timeout.connect(self._apply_drift_angle_pitch)
        self._pending_drift_pitch_value = None
        
        self._drift_roll_send_timer = QTimer()
        self._drift_roll_send_timer.setSingleShot(True)
        self._drift_roll_send_timer.timeout.connect(self._apply_drift_angle_roll)
        self._pending_drift_roll_value = None

        # Orientation visualization widget
        self.visualization_widget = None
        
        # Drift correction status
        self.drift_status_label = None
        
        # Filter selection
        self.filter_combo = None
        
        # Reset orientation controls
        self.reset_shortcut = "None"
        self.reset_shortcut_display_name = "None"
        self.reset_button = None
        self._global_hotkey_registered = False
        self._qt_shortcut = None
        self._gamepad_monitor = None
        
        # Position offset tracking (for reset functionality)
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)

        self._build_ui()
        
        # Send initial drift angle to fusion worker after UI is built
        self._initial_drift_sent = False
        QTimer.singleShot(100, self._send_initial_drift_angle)

    def _build_ui(self):
        """Build the calibration panel UI."""
        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(4, 2, 4, 2)
        
        # Filter and reset controls frame at top
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setSpacing(4)
        controls_layout.setContentsMargins(6, 4, 6, 4)
        
        # Filter selection (left side)
        filter_label = QLabel("Filter:")
        controls_layout.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['complementary', 'quaternion'])
        self.filter_combo.setCurrentText('complementary')
        self.filter_combo.currentTextChanged.connect(self._on_filter_change)
        controls_layout.addWidget(self.filter_combo)
        
        # Add stretch to separate left and right controls
        controls_layout.addStretch()
        
        # Gyro calibration controls (right side)
        self.calib_status_label = QLabel("Gyro: Not calibrated")
        self.calib_status_label.setAlignment(Qt.AlignCenter)
        self.calib_status_label.setProperty("status", "error")
        controls_layout.addWidget(self.calib_status_label)
        
        self.recal_button = QPushButton("Recalibrate Gyro Bias")
        self.recal_button.clicked.connect(self._on_recalibrate)
        self.recal_button.setEnabled(False)  # Start disabled until processing is active
        controls_layout.addWidget(self.recal_button)
        
        main_layout.addWidget(controls_frame)
        
        # Second row of controls
        controls2_frame = QFrame()
        controls2_layout = QHBoxLayout(controls2_frame)
        controls2_layout.setSpacing(4)
        controls2_layout.setContentsMargins(6, 4, 6, 4)
        
        # Add stretch to push reset controls to the right
        controls2_layout.addStretch()
        
        # Reset controls (right side)
        self.reset_button = QPushButton("Reset Orientation")
        self.reset_button.clicked.connect(self._on_reset_orientation)
        controls2_layout.addWidget(self.reset_button)
        
        main_layout.addWidget(controls2_frame)
        
        # Add dividing line below gyro controls
        divider_frame = QFrame()
        divider_frame.setFrameShape(QFrame.HLine)
        divider_frame.setFrameShadow(QFrame.Sunken)
        divider_frame.setMaximumHeight(2)
        divider_frame.setStyleSheet("""
            QFrame {
                color: #888888;
                background-color: #888888;
                border: 1px solid #888888;
            }
        """)
        main_layout.addWidget(divider_frame)
        
        # Horizontal layout for sliders and visualization
        sliders_viz_layout = QHBoxLayout()
        
        # Drift correction sliders frame
        sliders_frame = QFrame()
        sliders_layout = QVBoxLayout(sliders_frame)
        sliders_layout.setSpacing(8)  # Space between each slider group
        sliders_layout.setContentsMargins(6, 4, 6, 4)
        
        # Yaw drift correction
        yaw_group = QVBoxLayout()
        yaw_group.setSpacing(2)  # Minimal space between label and slider
        drift_yaw_label = QLabel("Drift Correction Angle - Yaw:")
        drift_yaw_label.setAlignment(Qt.AlignLeft)
        yaw_group.addWidget(drift_yaw_label)
        
        # Create horizontal layout for slider + value in one line
        yaw_row = QHBoxLayout()
        yaw_row.setContentsMargins(0, 0, 0, 0)  # No margins
        yaw_row.setSpacing(4)  # Small space between slider and value
        
        self.drift_yaw_slider = QSlider(Qt.Horizontal)
        self.drift_yaw_slider.setMinimum(0)
        self.drift_yaw_slider.setMaximum(250)  # 0-25.0 with 0.1 precision
        self.drift_yaw_slider.setValue(int(DEFAULT_CENTER_THRESHOLD * 10))
        self.drift_yaw_slider.valueChanged.connect(self._on_drift_yaw_angle_change)
        yaw_row.addWidget(self.drift_yaw_slider)
        
        self.drift_angle_yaw_label = QLabel(f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        self.drift_angle_yaw_label.setMinimumWidth(40)
        self.drift_angle_yaw_label.setAlignment(Qt.AlignLeft)
        yaw_row.addWidget(self.drift_angle_yaw_label)
        
        yaw_group.addLayout(yaw_row)
        sliders_layout.addLayout(yaw_group)
        
        # Pitch drift correction
        pitch_group = QVBoxLayout()
        pitch_group.setSpacing(2)  # Minimal space between label and slider
        drift_pitch_label = QLabel("Drift Correction Angle - Pitch:")
        drift_pitch_label.setAlignment(Qt.AlignLeft)
        pitch_group.addWidget(drift_pitch_label)
        
        # Create horizontal layout for slider + value in one line
        pitch_row = QHBoxLayout()
        pitch_row.setContentsMargins(0, 0, 0, 0)  # No margins
        pitch_row.setSpacing(4)  # Small space between slider and value
        
        self.drift_pitch_slider = QSlider(Qt.Horizontal)
        self.drift_pitch_slider.setMinimum(0)
        self.drift_pitch_slider.setMaximum(250)  # 0-25.0 with 0.1 precision
        self.drift_pitch_slider.setValue(int(DEFAULT_CENTER_THRESHOLD * 10))
        self.drift_pitch_slider.valueChanged.connect(self._on_drift_pitch_angle_change)
        pitch_row.addWidget(self.drift_pitch_slider)
        
        self.drift_angle_pitch_label = QLabel(f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        self.drift_angle_pitch_label.setMinimumWidth(40)
        self.drift_angle_pitch_label.setAlignment(Qt.AlignLeft)
        pitch_row.addWidget(self.drift_angle_pitch_label)
        
        pitch_group.addLayout(pitch_row)
        sliders_layout.addLayout(pitch_group)
        
        # Roll drift correction
        roll_group = QVBoxLayout()
        roll_group.setSpacing(2)  # Minimal space between label and slider
        drift_roll_label = QLabel("Drift Correction Angle - Roll:")
        drift_roll_label.setAlignment(Qt.AlignLeft)
        roll_group.addWidget(drift_roll_label)
        
        # Create horizontal layout for slider + value in one line
        roll_row = QHBoxLayout()
        roll_row.setContentsMargins(0, 0, 0, 0)  # No margins
        roll_row.setSpacing(4)  # Small space between slider and value
        
        self.drift_roll_slider = QSlider(Qt.Horizontal)
        self.drift_roll_slider.setMinimum(0)
        self.drift_roll_slider.setMaximum(250)  # 0-25.0 with 0.1 precision
        self.drift_roll_slider.setValue(int(DEFAULT_CENTER_THRESHOLD * 10))
        self.drift_roll_slider.valueChanged.connect(self._on_drift_roll_angle_change)
        roll_row.addWidget(self.drift_roll_slider)
        
        self.drift_angle_roll_label = QLabel(f"{DEFAULT_CENTER_THRESHOLD:.1f}")
        self.drift_angle_roll_label.setMinimumWidth(40)
        self.drift_angle_roll_label.setAlignment(Qt.AlignLeft)
        roll_row.addWidget(self.drift_angle_roll_label)
        
        roll_group.addLayout(roll_row)
        sliders_layout.addLayout(roll_group)
        
        # Add sliders frame to horizontal layout
        sliders_viz_layout.addWidget(sliders_frame, stretch=1)
        
        # Visualization frame
        viz_frame = QFrame()
        viz_layout = QVBoxLayout(viz_frame)
        viz_layout.setSpacing(4)
        viz_layout.setContentsMargins(6, 4, 6, 4)
        
        # Visualization title
        viz_title = QLabel("Orientation")
        viz_title.setAlignment(Qt.AlignCenter)
        viz_layout.addWidget(viz_title)
        
        # Create visualization widget
        self.visualization_widget = OrientationVisualizationWidget(self)
        viz_layout.addWidget(self.visualization_widget)
        
        # Drift correction status indicator
        self.drift_status_label = QLabel("Drift Correction Inactive")
        self.drift_status_label.setProperty("status", "error")
        self.drift_status_label.setAlignment(Qt.AlignCenter)
        viz_layout.addWidget(self.drift_status_label)
        
        # Add visualization frame to horizontal layout
        sliders_viz_layout.addWidget(viz_frame, stretch=0)
        
        # Add horizontal layout to main layout
        main_layout.addLayout(sliders_viz_layout)

    def _on_drift_yaw_angle_change(self, value):
        """Handle yaw drift angle slider changes with debouncing."""
        try:
            # Convert slider value (0-250) to float (0.0-25.0)
            v = float(value) / 10.0
        except Exception:
            v = 0.0

        # Quantize to 0.1 and update display immediately
        vq = round(v * 10.0) / 10.0
        self.drift_angle_yaw_value = vq
        self.drift_angle_yaw_label.setText(f"{vq:.1f}")
        
        # Update visualization widget immediately
        if self.visualization_widget:
            self.visualization_widget.update_drift_angle_yaw(vq)

        # Store the value for debounced sending
        self._pending_drift_yaw_value = vq
        
        # Restart debounce timer
        self._drift_yaw_send_timer.stop()
        self._drift_yaw_send_timer.start(THRESH_DEBOUNCE_MS)

    def _on_drift_pitch_angle_change(self, value):
        """Handle pitch drift angle slider changes with debouncing."""
        try:
            # Convert slider value (0-250) to float (0.0-25.0)
            v = float(value) / 10.0
        except Exception:
            v = 0.0

        # Quantize to 0.1 and update display immediately
        vq = round(v * 10.0) / 10.0
        self.drift_angle_pitch_value = vq
        self.drift_angle_pitch_label.setText(f"{vq:.1f}")
        
        # Update visualization widget immediately
        if self.visualization_widget:
            self.visualization_widget.update_drift_angle_pitch(vq)

        # Store the value for debounced sending
        self._pending_drift_pitch_value = vq
        
        # Restart debounce timer
        self._drift_pitch_send_timer.stop()
        self._drift_pitch_send_timer.start(THRESH_DEBOUNCE_MS)

    def _on_drift_roll_angle_change(self, value):
        """Handle roll drift angle slider changes with debouncing."""
        try:
            # Convert slider value (0-250) to float (0.0-25.0)
            v = float(value) / 10.0
        except Exception:
            v = 0.0

        # Quantize to 0.1 and update display immediately
        vq = round(v * 10.0) / 10.0
        self.drift_angle_roll_value = vq
        self.drift_angle_roll_label.setText(f"{vq:.1f}")
        
        # Update visualization widget immediately
        if self.visualization_widget:
            self.visualization_widget.update_drift_angle_roll(vq)

        # Store the value for debounced sending
        self._pending_drift_roll_value = vq
        
        # Restart debounce timer
        self._drift_roll_send_timer.stop()
        self._drift_roll_send_timer.start(THRESH_DEBOUNCE_MS)

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
    
    def _set_reset_shortcut(self, key, display_name):
        """Set the keyboard or gamepad shortcut for reset orientation."""
        # Clean up existing shortcuts
        try:
            if hasattr(self, '_shortcut_obj') and self._shortcut_obj:
                self._shortcut_obj.setKey(QKeySequence())
                self._shortcut_obj.deleteLater()
                self._shortcut_obj = None
        except Exception:
            pass
        
        # Stop existing gamepad monitor
        try:
            if self._gamepad_monitor:
                self._gamepad_monitor.stop()
                self._gamepad_monitor.wait(1000)
                self._gamepad_monitor = None
        except Exception:
            pass

        try:
            self.reset_shortcut = key
            self.reset_shortcut_display_name = display_name if display_name else key
            if key and key != 'None':
                self.reset_button.setText(f"Reset Orientation ({display_name})")
            else:
                self.reset_button.setText("Reset Orientation")
            
            # Register appropriate input handler
            if key and key != 'None':
                if key.startswith('joy'):
                    # Gamepad input
                    try:
                        self._gamepad_monitor = GamepadMonitorThread(key, self)
                        self._gamepad_monitor.shortcut_triggered.connect(self._on_reset_orientation)
                        self._gamepad_monitor.start()
                        
                        if self.message_callback:
                            QTimer.singleShot(0, lambda: self.message_callback(f"Reset shortcut set to: {display_name}"))
                    except Exception as ex:
                        if self.message_callback:
                            QTimer.singleShot(0, lambda msg=f"Failed to set gamepad shortcut: {ex}": self.message_callback(msg))
                else:
                    # Keyboard input
                    try:
                        import keyboard
                        # Clear existing hotkey if any
                        try:
                            keyboard.unhook_all()
                        except Exception:
                            pass
                        
                        # Register new hotkey
                        keyboard.on_press_key(key, lambda _: self._on_reset_orientation())
                        
                        if self.message_callback:
                            QTimer.singleShot(0, lambda: self.message_callback(f"Reset shortcut set to: {display_name}"))
                    except Exception as ex:
                        if self.message_callback:
                            QTimer.singleShot(0, lambda msg=f"Failed to set keyboard shortcut: {ex}": self.message_callback(msg))
        except Exception as ex:
            if self.message_callback:
                QTimer.singleShot(0, lambda msg=f"Failed to set shortcut: {ex}": self.message_callback(msg))
    
    def _on_reset_orientation(self):
        """Handle orientation reset button click."""
        # Send non-destructive orientation reset command to fusion worker
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
            
            if self.message_callback:
                QTimer.singleShot(0, lambda: self.message_callback("Position offsets updated to make current position zero"))
        except Exception:
            pass

    def update_calibration_status(self, calibrated):
        """Update gyro calibration status with color changes.
        
        Args:
            calibrated: Boolean indicating if gyro is calibrated
        """
        try:
            if calibrated:
                # Info color for calibrated
                self.calib_status_label.setText("Gyro: Calibrated")
                self.calib_status_label.setProperty("status", "info")
                self.calib_status_label.style().polish(self.calib_status_label)
            else:
                # Error color for not calibrated
                self.calib_status_label.setText("Gyro: Not calibrated")
                self.calib_status_label.setProperty("status", "error")
                self.calib_status_label.style().polish(self.calib_status_label)
        except Exception:
            pass

    def get_prefs(self):
        """Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with drift angles, filter, and reset shortcut preferences
        """
        # Persist all drift angles to one decimal place
        try:
            yaw_v = round(float(self.drift_angle_yaw_value) * 10.0) / 10.0
            pitch_v = round(float(self.drift_angle_pitch_value) * 10.0) / 10.0
            roll_v = round(float(self.drift_angle_roll_value) * 10.0) / 10.0
            return {
                'drift_angle_yaw': f"{yaw_v:.1f}",
                'drift_angle_pitch': f"{pitch_v:.1f}",
                'drift_angle_roll': f"{roll_v:.1f}",
                'filter': self.filter_combo.currentText() if self.filter_combo else 'complementary',
                'reset_shortcut': self.reset_shortcut,
                'reset_shortcut_display_name': self.reset_shortcut_display_name
            }
        except Exception:
            return {
                'drift_angle_yaw': f"{DEFAULT_CENTER_THRESHOLD:.1f}",
                'drift_angle_pitch': f"{DEFAULT_CENTER_THRESHOLD:.1f}",
                'drift_angle_roll': f"{DEFAULT_CENTER_THRESHOLD:.1f}",
                'filter': 'complementary',
                'reset_shortcut': 'None',
                'reset_shortcut_display_name': 'None'
            }

    def set_prefs(self, prefs):
        """Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional drift_angle preferences
        """
        if prefs is None:
            return
        
        # Handle new format (separate yaw, pitch, and roll)
        if 'drift_angle_yaw' in prefs and prefs['drift_angle_yaw']:
            try:
                angle = float(prefs['drift_angle_yaw'])
                angle = round(angle * 10.0) / 10.0
                self.set_drift_angle_yaw(angle)
            except Exception:
                pass
        
        if 'drift_angle_pitch' in prefs and prefs['drift_angle_pitch']:
            try:
                angle = float(prefs['drift_angle_pitch'])
                angle = round(angle * 10.0) / 10.0
                self.set_drift_angle_pitch(angle)
            except Exception:
                pass
        
        if 'drift_angle_roll' in prefs and prefs['drift_angle_roll']:
            try:
                angle = float(prefs['drift_angle_roll'])
                angle = round(angle * 10.0) / 10.0
                self.set_drift_angle_roll(angle)
            except Exception:
                pass
        
        # Backward compatibility: if old format exists but new doesn't, use for all three
        if ('drift_angle' in prefs and prefs['drift_angle'] and 
            'drift_angle_yaw' not in prefs and 'drift_angle_pitch' not in prefs and 'drift_angle_roll' not in prefs):
            try:
                angle = float(prefs['drift_angle'])
                angle = round(angle * 10.0) / 10.0
                self.set_drift_angle_yaw(angle)
                self.set_drift_angle_pitch(angle)
                self.set_drift_angle_roll(angle)
            except Exception:
                pass
        
        # Restore filter selection if saved
        try:
            filter_type = prefs.get('filter', 'complementary')
            if self.filter_combo:
                self.filter_combo.setCurrentText(filter_type)
                # Notify fusion worker of the preference (best-effort)
                try:
                    self._on_filter_change(filter_type)
                except Exception:
                    pass
        except Exception:
            pass
        
        # Restore keyboard/gamepad shortcut if saved
        shortcut = prefs.get('reset_shortcut', 'None')
        if shortcut and shortcut != 'None':
            try:
                # Try to get saved display name first
                display_name = prefs.get('reset_shortcut_display_name', shortcut)
                
                # If no saved display name, generate one
                if display_name == shortcut or not display_name:
                    if shortcut.startswith('KP_'):
                        # Generate display name for numpad keys
                        numpad_map = {
                            'KP_0': 'Numpad 0', 'KP_1': 'Numpad 1', 'KP_2': 'Numpad 2',
                            'KP_3': 'Numpad 3', 'KP_4': 'Numpad 4', 'KP_5': 'Numpad 5',
                            'KP_6': 'Numpad 6', 'KP_7': 'Numpad 7', 'KP_8': 'Numpad 8',
                            'KP_9': 'Numpad 9', 'KP_Decimal': 'Numpad .', 'KP_Divide': 'Numpad /',
                            'KP_Multiply': 'Numpad *', 'KP_Subtract': 'Numpad -', 'KP_Add': 'Numpad +',
                            'KP_Enter': 'Numpad Enter'
                        }
                        display_name = numpad_map.get(shortcut, shortcut)
                    elif shortcut.startswith('joy'):
                        # For gamepad shortcuts without saved name, show generic label
                        display_name = f"Gamepad ({shortcut})"
                    else:
                        # For other keys, use the shortcut itself
                        display_name = shortcut.upper()
                
                self._set_reset_shortcut(shortcut, display_name)
            except Exception:
                pass
        else:
            # Ensure button shows no shortcut
            if self.reset_button:
                self.reset_button.setText("Reset Orientation")

    def get_drift_angle_yaw(self):
        """Get current yaw drift angle value.
        
        Returns:
            float: Current yaw drift angle
        """
        return self.drift_angle_yaw_value
    
    def get_drift_angle_pitch(self):
        """Get current pitch drift angle value.
        
        Returns:
            float: Current pitch drift angle
        """
        return self.drift_angle_pitch_value

    def get_drift_angle_roll(self):
        """Get current roll drift angle value.
        
        Returns:
            float: Current roll drift angle
        """
        return self.drift_angle_roll_value

    def set_drift_angle_yaw(self, angle):
        """Set yaw drift angle programmatically.
        
        Args:
            angle: Yaw drift angle value (0.0-25.0)
        """
        try:
            angle = float(angle)
            angle = max(0.0, min(25.0, angle))
            angle = round(angle * 10.0) / 10.0
            
            self.drift_angle_yaw_value = angle
            self.drift_angle_yaw_label.setText(f"{angle:.1f}")
            self.drift_yaw_slider.setValue(int(angle * 10))
            
            if self.control_queue:
                safe_queue_put(self.control_queue, ('set_center_threshold_yaw', float(angle)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def set_drift_angle_pitch(self, angle):
        """Set pitch drift angle programmatically.
        
        Args:
            angle: Pitch drift angle value (0.0-25.0)
        """
        try:
            angle = float(angle)
            angle = max(0.0, min(25.0, angle))
            angle = round(angle * 10.0) / 10.0
            
            self.drift_angle_pitch_value = angle
            self.drift_angle_pitch_label.setText(f"{angle:.1f}")
            self.drift_pitch_slider.setValue(int(angle * 10))
            
            if self.control_queue:
                safe_queue_put(self.control_queue, ('set_center_threshold_pitch', float(angle)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _apply_drift_angle_yaw(self):
        """Send the quantized yaw drift angle to the control queue (debounced)."""
        try:
            if self._pending_drift_yaw_value is not None and self.control_queue:
                if not safe_queue_put(self.control_queue, ('set_center_threshold_yaw', float(self._pending_drift_yaw_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send yaw drift angle update")
                else:
                    if self.message_callback:
                        self.message_callback(f"Yaw drift angle updated to {self._pending_drift_yaw_value:.1f}°")
                self._pending_drift_yaw_value = None
        except Exception:
            pass

    def _apply_drift_angle_pitch(self):
        """Send the quantized pitch drift angle to the control queue (debounced)."""
        try:
            if self._pending_drift_pitch_value is not None and self.control_queue:
                if not safe_queue_put(self.control_queue, ('set_center_threshold_pitch', float(self._pending_drift_pitch_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send pitch drift angle update")
                else:
                    if self.message_callback:
                        self.message_callback(f"Pitch drift angle updated to {self._pending_drift_pitch_value:.1f}°")
                self._pending_drift_pitch_value = None
        except Exception:
            pass

    def _apply_drift_angle_roll(self):
        """Send the quantized roll drift angle to the control queue (debounced)."""
        try:
            if self._pending_drift_roll_value is not None and self.control_queue:
                if not safe_queue_put(self.control_queue, ('set_center_threshold_roll', float(self._pending_drift_roll_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send roll drift angle update")
                else:
                    if self.message_callback:
                        self.message_callback(f"Roll drift angle updated to {self._pending_drift_roll_value:.1f}°")
                self._pending_drift_roll_value = None
        except Exception:
            pass

    def _send_initial_drift_angle(self):
        """Send the initial drift angle values to the fusion worker."""
        try:
            # Prevent double sending of initial values
            if self._initial_drift_sent or not self.control_queue:
                return
            self._initial_drift_sent = True
            
            if self.control_queue:
                # Send yaw drift angle
                if not safe_queue_put(self.control_queue, ('set_center_threshold_yaw', float(self.drift_angle_yaw_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send initial yaw drift angle")
                else:
                    if self.message_callback:
                        self.message_callback(f"Initial yaw drift angle set to {self.drift_angle_yaw_value:.1f}°")
                
                # Send pitch drift angle
                if not safe_queue_put(self.control_queue, ('set_center_threshold_pitch', float(self.drift_angle_pitch_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send initial pitch drift angle")
                else:
                    if self.message_callback:
                        self.message_callback(f"Initial pitch drift angle set to {self.drift_angle_pitch_value:.1f}°")
                
                # Send roll drift angle
                if not safe_queue_put(self.control_queue, ('set_center_threshold_roll', float(self.drift_angle_roll_value)), timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send initial roll drift angle")
                else:
                    if self.message_callback:
                        self.message_callback(f"Initial roll drift angle set to {self.drift_angle_roll_value:.1f}°")
        except Exception:
            pass
    
    def update_orientation(self, pitch, yaw, roll):
        """Update the orientation visualization with current angles.
        
        Args:
            pitch: Pitch angle in degrees
            yaw: Yaw angle in degrees
            roll: Roll angle in degrees
        """
        if self.visualization_widget:
            self.visualization_widget.update_orientation(pitch, yaw, roll)
    
    def update_drift_status(self, active):
        """Update the drift correction status in visualization and label.
        
        Args:
            active: Boolean indicating if drift correction is active
        """
        try:
            # Update visualization widget
            if self.visualization_widget:
                self.visualization_widget.update_drift_correction(active)
            
            # Update status label
            if self.drift_status_label:
                if active:
                    self.drift_status_label.setText("Drift Correction Active")
                    self.drift_status_label.setProperty("status", "enabled")
                else:
                    self.drift_status_label.setText("Drift Correction Inactive")
                    self.drift_status_label.setProperty("status", "error")
                self.drift_status_label.style().polish(self.drift_status_label)
        except Exception:
            pass
    
    def update_processing_status(self, status):
        """
        Update processing status and enable/disable recalibrate button accordingly.
        
        Args:
            status: String 'active' or 'inactive' indicating processing state
        """
        try:
            is_active = (status == 'active')
            self.recal_button.setEnabled(is_active)
            
            # Update button text and styling to reflect state
            if is_active:
                self.recal_button.setText("Recalibrate Gyro Bias")
                # Remove disabled styling
                self.recal_button.setProperty("status", "")
            else:
                self.recal_button.setText("Recalibrate Gyro Bias")
                # Apply disabled styling to match serial panel
                self.recal_button.setProperty("status", "disabled")
            self.recal_button.style().polish(self.recal_button)
            
            # Also update the status label styling when not active
            if not is_active and self.calib_status_label.text() == "Gyro: Not calibrated":
                self.calib_status_label.setProperty("status", "disabled")
                self.calib_status_label.style().polish(self.calib_status_label)
        except Exception:
            pass
    
    def clear_calibration_state(self):
        """
        Clear calibration state when serial is stopped.
        Reset gyro bias status and disable recalibration button.
        """
        try:
            # Reset gyro calibration status to "not calibrated" with disabled styling
            self.calib_status_label.setText("Gyro: Not calibrated")
            self.calib_status_label.setProperty("status", "disabled")
            self.calib_status_label.style().polish(self.calib_status_label)
            
            # Disable recalibration button with disabled styling
            self.recal_button.setEnabled(False)
            self.recal_button.setProperty("status", "disabled")
            self.recal_button.style().polish(self.recal_button)
        except Exception:
            pass
    
    def cleanup(self):
        """Clean up threads and resources when the panel is destroyed."""
        try:
            # Stop gamepad monitor thread if running
            if self._gamepad_monitor:
                self._gamepad_monitor.stop()
                self._gamepad_monitor.wait(2000)  # Wait up to 2 seconds
                self._gamepad_monitor = None
            
            # Clean up keyboard hooks
            try:
                import keyboard
                keyboard.unhook_all()
            except ImportError:
                pass  # keyboard module not available
            except Exception:
                pass  # Already cleaned up or other error
            
            # Cleanup pygame if it was initialized
            if PYGAME_AVAILABLE:
                try:
                    pygame.quit()
                except Exception:
                    pass
                    
        except Exception as ex:
            print(f"Error during cleanup: {ex}")
    
    def closeEvent(self, event):
        """Handle panel close event."""
        self.cleanup()
        super().closeEvent(event)
    
    def __del__(self):
        """Destructor - ensure cleanup happens."""
        try:
            self.cleanup()
        except Exception:
            pass