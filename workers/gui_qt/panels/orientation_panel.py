"""
PyQt5 Orientation Panel for frankentrack GUI.

Displays Euler angles (Yaw, Pitch, Roll), position (X, Y, Z),
drift correction controls, and orientation reset functionality.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QPushButton, QComboBox, QDialog, QApplication,
                             QShortcut)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence

from config.config import QUEUE_PUT_TIMEOUT
from util.error_utils import safe_queue_put

# Global hotkey support
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


class KeyCaptureDialog(QDialog):
    """Dialog to capture keyboard shortcuts for reset orientation."""
    
    def __init__(self, parent=None, current_shortcut="None"):
        super().__init__(parent)
        self.setWindowTitle("Set Shortcut Key")
        self.setFixedSize(300, 120)
        self.setModal(True)
        
        # Center dialog over parent
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 300) // 2
            y = parent_geo.y() + (parent_geo.height() - 120) // 2
            self.move(x, y)
        
        # Dialog layout
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel("Press any key to set as shortcut.\n"
                             "(This should be the same key as in opentrack)\n"
                             "(Esc to cancel)")
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)
        
        # Current shortcut display
        self.current_label = QLabel(f"Current: {current_shortcut}")
        self.current_label.setStyleSheet("color: gray;")
        self.current_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.current_label)
        
        self.setLayout(layout)
        
        # Result storage
        self.captured_key = None
        self.display_name = None
    
    def keyPressEvent(self, event):
        """Capture key press events."""
        # Cancel on Escape
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        
        # Get key information
        key = event.key()
        text = event.text()
        
        # Map Qt keys to tkinter-compatible keysyms
        key_map = self._get_key_mapping()
        
        if key in key_map:
            binding_key, display_name = key_map[key]
        elif text and text.isprintable() and len(text) == 1:
            # Regular printable character
            binding_key = text.lower()
            display_name = text.lower()
        else:
            # Unknown key
            binding_key = f"Key_{key}"
            display_name = f"Key_{key}"
        
        # Store result
        self.captured_key = binding_key
        self.display_name = display_name
        
        # Show confirmation briefly
        self.current_label.setText(f"Shortcut set to: {display_name}")
        QApplication.processEvents()
        
        # Close dialog after brief delay
        self.accept()
    
    def _get_key_mapping(self):
        """Get mapping of Qt keys to tkinter-compatible keysyms."""
        return {
            # Function keys
            Qt.Key_F1: ('F1', 'F1'), Qt.Key_F2: ('F2', 'F2'), 
            Qt.Key_F3: ('F3', 'F3'), Qt.Key_F4: ('F4', 'F4'),
            Qt.Key_F5: ('F5', 'F5'), Qt.Key_F6: ('F6', 'F6'),
            Qt.Key_F7: ('F7', 'F7'), Qt.Key_F8: ('F8', 'F8'),
            Qt.Key_F9: ('F9', 'F9'), Qt.Key_F10: ('F10', 'F10'),
            Qt.Key_F11: ('F11', 'F11'), Qt.Key_F12: ('F12', 'F12'),
            
            # Numpad keys
            Qt.Key_0: ('KP_0', 'Numpad 0'), Qt.Key_1: ('KP_1', 'Numpad 1'),
            Qt.Key_2: ('KP_2', 'Numpad 2'), Qt.Key_3: ('KP_3', 'Numpad 3'),
            Qt.Key_4: ('KP_4', 'Numpad 4'), Qt.Key_5: ('KP_5', 'Numpad 5'),
            Qt.Key_6: ('KP_6', 'Numpad 6'), Qt.Key_7: ('KP_7', 'Numpad 7'),
            Qt.Key_8: ('KP_8', 'Numpad 8'), Qt.Key_9: ('KP_9', 'Numpad 9'),
            
            # Special keys
            Qt.Key_Space: ('space', 'Space'),
            Qt.Key_Return: ('Return', 'Enter'),
            Qt.Key_Enter: ('Return', 'Enter'),
            Qt.Key_Backspace: ('BackSpace', 'Backspace'),
            Qt.Key_Tab: ('Tab', 'Tab'),
            Qt.Key_Delete: ('Delete', 'Delete'),
            Qt.Key_Insert: ('Insert', 'Insert'),
            Qt.Key_Home: ('Home', 'Home'),
            Qt.Key_End: ('End', 'End'),
            Qt.Key_PageUp: ('Prior', 'Page Up'),
            Qt.Key_PageDown: ('Next', 'Page Down'),
            Qt.Key_Up: ('Up', 'Up'),
            Qt.Key_Down: ('Down', 'Down'),
            Qt.Key_Left: ('Left', 'Left'),
            Qt.Key_Right: ('Right', 'Right')
        }


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
        
        # Drift correction status
        self.drift_status_label = None
        
        # Filter selection
        self.filter_combo = None
        
        # Keyboard shortcut for reset orientation
        self.reset_shortcut = "None"
        self.reset_button = None
        self.shortcut_button = None
        self._global_hotkey_registered = False
        self._qt_shortcut = None
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the orientation panel UI."""
        # Main layout
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)
        
        # Left section: Data displays
        left_frame = QGroupBox()
        left_layout = QVBoxLayout()
        left_frame.setLayout(left_layout)
        
        # Right section: Controls
        right_frame = QGroupBox()
        right_layout = QVBoxLayout()
        right_frame.setLayout(right_layout)
        
        # Build components
        self._build_euler_displays(left_layout)
        self._build_position_displays(left_layout)
        self._build_drift_status(right_layout)
        self._build_filter_selection(right_layout)
        self._build_reset_controls(right_layout)
        
        # Add to main layout
        main_layout.addWidget(left_frame, stretch=1)
        main_layout.addWidget(right_frame, stretch=0)
    
    def _build_euler_displays(self, parent_layout):
        """Build Euler angle (Yaw, Pitch, Roll) display row."""
        # Create grid layout for euler angles
        euler_grid = QGridLayout()
        
        # Row 0: Yaw, Pitch, Roll
        euler_grid.addWidget(QLabel("Yaw:"), 0, 0)
        self.yaw_value_label = QLabel("0.0")
        self.yaw_value_label.setMinimumWidth(60)
        euler_grid.addWidget(self.yaw_value_label, 0, 1)
        
        euler_grid.addWidget(QLabel("Pitch:"), 0, 2)
        self.pitch_value_label = QLabel("0.0")
        self.pitch_value_label.setMinimumWidth(60)
        euler_grid.addWidget(self.pitch_value_label, 0, 3)
        
        euler_grid.addWidget(QLabel("Roll:"), 0, 4)
        self.roll_value_label = QLabel("0.0")
        self.roll_value_label.setMinimumWidth(60)
        euler_grid.addWidget(self.roll_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(euler_grid)
    
    def _build_position_displays(self, parent_layout):
        """Build position (X, Y, Z) display row."""
        # Create grid layout for positions
        position_grid = QGridLayout()
        
        # Row 0: X, Y, Z positions
        position_grid.addWidget(QLabel("X:"), 0, 0)
        self.x_value_label = QLabel("0.00")
        self.x_value_label.setMinimumWidth(60)
        position_grid.addWidget(self.x_value_label, 0, 1)
        
        position_grid.addWidget(QLabel("Y:"), 0, 2)
        self.y_value_label = QLabel("0.00")
        self.y_value_label.setMinimumWidth(60)
        position_grid.addWidget(self.y_value_label, 0, 3)
        
        position_grid.addWidget(QLabel("Z:"), 0, 4)
        self.z_value_label = QLabel("0.00")
        self.z_value_label.setMinimumWidth(60)
        position_grid.addWidget(self.z_value_label, 0, 5)
        
        # Add grid to parent layout
        parent_layout.addLayout(position_grid)
    
    def _build_drift_status(self, parent_layout):
        """Build drift correction status indicator."""
        self.drift_status_label = QLabel("Drift Correction Inactive")
        self.drift_status_label.setStyleSheet("color: red;")
        self.drift_status_label.setAlignment(Qt.AlignCenter)
        parent_layout.addWidget(self.drift_status_label)
    
    def _build_filter_selection(self, parent_layout):
        """Build filter selection dropdown."""
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['complementary', 'quaternion'])
        self.filter_combo.setCurrentText('complementary')
        self.filter_combo.currentTextChanged.connect(self._on_filter_change)
        filter_layout.addWidget(self.filter_combo)
        
        parent_layout.addLayout(filter_layout)
    
    def _build_reset_controls(self, parent_layout):
        """Build reset orientation button and shortcut controls."""
        # Reset orientation button
        self.reset_button = QPushButton("Reset Orientation")
        self.reset_button.clicked.connect(self._on_reset)
        parent_layout.addWidget(self.reset_button)
        
        # Set shortcut button
        self.shortcut_button = QPushButton("Set Shortcut...")
        self.shortcut_button.clicked.connect(self._on_set_shortcut)
        parent_layout.addWidget(self.shortcut_button)
    
    def _on_filter_change(self, filter_type):
        """Send filter selection change to fusion worker via control queue."""
        try:
            if self.control_queue:
                # Send tuple command: ('set_filter', 'quaternion'|'complementary')
                safe_queue_put(self.control_queue, ('set_filter', filter_type), timeout=QUEUE_PUT_TIMEOUT)
                if self.message_callback:
                    self.message_callback(f"Filter changed to: {filter_type}")
        except Exception as ex:
            if self.message_callback:
                self.message_callback(f"Failed to set filter to: {filter_type} - {ex}")
    
    def _on_set_shortcut(self):
        """Open dialog to capture a keyboard shortcut for reset orientation."""
        dialog = KeyCaptureDialog(self, self.reset_shortcut)
        
        if dialog.exec_() == QDialog.Accepted and dialog.captured_key:
            self._set_reset_shortcut(dialog.captured_key, dialog.display_name)
    
    def _set_reset_shortcut(self, key, display_name=None):
        """Set the keyboard shortcut for reset orientation.
        
        Args:
            key: Key symbol (e.g., 'r', 'F5', 'space', 'KP_0')
            display_name: Optional friendly display name (e.g., 'Numpad 0')
        """
        # Remove old Qt shortcut
        if self._qt_shortcut:
            self._qt_shortcut.setEnabled(False)
            self._qt_shortcut = None
        
        # Remove old global hotkey if exists
        if self._global_hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
                self._global_hotkey_registered = False
            except Exception:
                pass
        
        # Store new shortcut
        self.reset_shortcut = key
        
        # Use display name if provided, otherwise use key
        if display_name is None:
            display_name = key
        
        # Update button text
        self.shortcut_button.setText(f"Shortcut: {display_name}")
        
        # Register global hotkey
        if KEYBOARD_AVAILABLE:
            try:
                # Convert keysym to keyboard module format
                hotkey_str = self._convert_keysym_to_keyboard(key)
                
                if hotkey_str:
                    # Register global hotkey
                    keyboard.add_hotkey(hotkey_str, self._on_reset, suppress=False)
                    self._global_hotkey_registered = True
                    
                    if self.message_callback:
                        self.message_callback(f"Global hotkey registered: {display_name}")
                else:
                    if self.message_callback:
                        self.message_callback(f"Warning: Could not map key '{display_name}' for global hotkey")
            except Exception as ex:
                if self.message_callback:
                    self.message_callback(f"Warning: Could not register global hotkey '{display_name}': {ex}")
        else:
            # Fallback to Qt shortcut if keyboard module not available
            try:
                # Convert to Qt key sequence
                qt_sequence = self._convert_keysym_to_qt_sequence(key)
                if qt_sequence:
                    self._qt_shortcut = QShortcut(QKeySequence(qt_sequence), self.window())
                    self._qt_shortcut.activated.connect(self._on_reset)
                    
                    if self.message_callback:
                        self.message_callback(f"Local shortcut registered: {display_name}")
                else:
                    if self.message_callback:
                        self.message_callback(f"Warning: Could not map key '{display_name}' for local shortcut")
            except Exception as ex:
                if self.message_callback:
                    self.message_callback(f"Warning: Could not register local shortcut '{display_name}': {ex}")
    
    def _convert_keysym_to_keyboard(self, keysym):
        """Convert tkinter-style keysym to keyboard module format.
        
        Args:
            keysym: Tkinter key symbol (e.g., 'r', 'F5', 'KP_0')
            
        Returns:
            String for keyboard module, or None if conversion fails
        """
        # Map numpad keys
        numpad_map = {
            'KP_0': 'num 0', 'KP_1': 'num 1', 'KP_2': 'num 2',
            'KP_3': 'num 3', 'KP_4': 'num 4', 'KP_5': 'num 5',
            'KP_6': 'num 6', 'KP_7': 'num 7', 'KP_8': 'num 8',
            'KP_9': 'num 9', 'KP_Decimal': 'num decimal',
            'KP_Divide': 'num divide', 'KP_Multiply': 'num multiply',
            'KP_Subtract': 'num subtract', 'KP_Add': 'num add',
            'KP_Enter': 'num enter'
        }
        
        if keysym in numpad_map:
            return numpad_map[keysym]
        
        # Map function keys
        if keysym.startswith('F') and len(keysym) <= 3:
            try:
                # F1-F24
                num = int(keysym[1:])
                if 1 <= num <= 24:
                    return keysym.lower()
            except ValueError:
                pass
        
        # Map special keys
        special_map = {
            'space': 'space',
            'Return': 'enter',
            'BackSpace': 'backspace',
            'Tab': 'tab',
            'Escape': 'esc',
            'Delete': 'delete',
            'Insert': 'insert',
            'Home': 'home',
            'End': 'end',
            'Prior': 'page up',
            'Next': 'page down',
            'Up': 'up',
            'Down': 'down',
            'Left': 'left',
            'Right': 'right'
        }
        
        if keysym in special_map:
            return special_map[keysym]
        
        # For regular single character keys, use lowercase
        if len(keysym) == 1:
            return keysym.lower()
        
        return None
    
    def _convert_keysym_to_qt_sequence(self, keysym):
        """Convert tkinter-style keysym to Qt key sequence.
        
        Args:
            keysym: Tkinter key symbol (e.g., 'r', 'F5', 'space')
            
        Returns:
            String for QKeySequence, or None if conversion fails
        """
        # Map special keys to Qt format
        special_map = {
            'space': 'Space',
            'Return': 'Return',
            'BackSpace': 'Backspace',
            'Tab': 'Tab',
            'Escape': 'Escape',
            'Delete': 'Delete',
            'Insert': 'Insert',
            'Home': 'Home',
            'End': 'End',
            'Prior': 'PgUp',
            'Next': 'PgDown',
            'Up': 'Up',
            'Down': 'Down',
            'Left': 'Left',
            'Right': 'Right'
        }
        
        if keysym in special_map:
            return special_map[keysym]
        
        # Function keys are already in correct format
        if keysym.startswith('F') and len(keysym) <= 3:
            return keysym
        
        # Regular single character keys
        if len(keysym) == 1:
            return keysym.upper()
        
        return None
    
    def _clear_reset_shortcut(self):
        """Clear the keyboard shortcut binding."""
        # Remove Qt shortcut
        if self._qt_shortcut:
            self._qt_shortcut.setEnabled(False)
            self._qt_shortcut = None
        
        # Remove global hotkey
        if self._global_hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
                self._global_hotkey_registered = False
            except Exception:
                pass
        
        self.reset_shortcut = "None"
        self.shortcut_button.setText("Set Shortcut...")
    
    def _on_reset(self):
        """Handle orientation reset button click."""
        # Send non-destructive orientation reset command to fusion worker.
        try:
            if self.control_queue:
                if not safe_queue_put(self.control_queue, 'reset_orientation', timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send reset command")
                    return
        except Exception as ex:
            if self.message_callback:
                self.message_callback(f"Failed to send reset command: {ex}")
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
            self.x_value_label.setText("0.00")
            self.y_value_label.setText("0.00")

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
            self.yaw_value_label.setText(f"{float(yaw):.1f}")
            self.pitch_value_label.setText(f"{float(pitch):.1f}")
            self.roll_value_label.setText(f"{float(roll):.1f}")
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
            self.x_value_label.setText(f"{dx:.2f}")
            self.y_value_label.setText(f"{dy:.2f}")
            self.z_value_label.setText(f"{dz:.2f}")
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
                self.drift_status_label.setText("Drift Correction Active")
                self.drift_status_label.setStyleSheet("color: blue;")
            else:
                self.drift_status_label.setText("Drift Correction Inactive")
                self.drift_status_label.setStyleSheet("color: red;")
        except Exception:
            pass
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with preferences including reset shortcut and filter
        """
        return {
            'reset_shortcut': self.reset_shortcut,
            'filter': self.filter_combo.currentText() if self.filter_combo else 'complementary'
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional preference keys including 'reset_shortcut' and 'filter'
        """
        # Restore keyboard shortcut if saved
        shortcut = prefs.get('reset_shortcut', 'None')
        if shortcut and shortcut != 'None':
            try:
                # Generate display name for numpad keys
                display_name = shortcut
                if shortcut.startswith('KP_'):
                    numpad_map = {
                        'KP_0': 'Numpad 0', 'KP_1': 'Numpad 1', 'KP_2': 'Numpad 2',
                        'KP_3': 'Numpad 3', 'KP_4': 'Numpad 4', 'KP_5': 'Numpad 5',
                        'KP_6': 'Numpad 6', 'KP_7': 'Numpad 7', 'KP_8': 'Numpad 8',
                        'KP_9': 'Numpad 9', 'KP_Decimal': 'Numpad .', 'KP_Divide': 'Numpad /',
                        'KP_Multiply': 'Numpad *', 'KP_Subtract': 'Numpad -', 'KP_Add': 'Numpad +',
                        'KP_Enter': 'Numpad Enter'
                    }
                    display_name = numpad_map.get(shortcut, shortcut)
                self._set_reset_shortcut(shortcut, display_name)
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
    
    def reset_position_offsets(self):
        """Reset position offsets to zero (for testing or manual reset)."""
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        self.x_value_label.setText("0.00")
        self.y_value_label.setText("0.00")
        self.z_value_label.setText("0.00")