"""
Keyboard and gamepad shortcut helper for PyQt5 GUI.

Provides unified shortcut capture and management functionality
for both keyboard and gamepad inputs.
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence

# Global hotkey support
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


class KeyCaptureDialog(QDialog):
    """Dialog to capture keyboard shortcuts."""
    
    def __init__(self, parent=None, current_shortcut="None"):
        super().__init__(parent)
        self.setWindowTitle("Set Shortcut Key")
        self.setFixedSize(300, 120)
        self.setModal(True)
        
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
        self.current_label.setProperty("status", "disabled")
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


class ShortcutManager:
    """Manages keyboard and gamepad shortcuts for PyQt5 applications."""
    
    def __init__(self, parent_widget, message_callback=None):
        """
        Initialize the shortcut manager.
        
        Args:
            parent_widget: Parent PyQt5 widget for shortcuts
            message_callback: Optional callback for status messages
        """
        self.parent_widget = parent_widget
        self.message_callback = message_callback
        
        # Shortcut state
        self.reset_shortcut = "None"
        self._qt_shortcut = None
        self._global_hotkey_registered = False
    
    def capture_shortcut(self, current_shortcut="None"):
        """
        Open dialog to capture a new shortcut.
        
        Args:
            current_shortcut: Current shortcut for display
            
        Returns:
            tuple: (key, display_name) or (None, None) if cancelled
        """
        dialog = KeyCaptureDialog(self.parent_widget, current_shortcut)
        
        if dialog.exec_() == QDialog.Accepted and dialog.captured_key:
            return dialog.captured_key, dialog.display_name
        
        return None, None
    
    def set_shortcut(self, key, display_name=None, callback=None):
        """
        Set a keyboard shortcut.
        
        Args:
            key: Key symbol (e.g., 'r', 'F5', 'space', 'KP_0')
            display_name: Optional friendly display name
            callback: Function to call when shortcut is triggered
            
        Returns:
            bool: True if shortcut was set successfully
        """
        # Clear existing shortcut
        self.clear_shortcut()
        
        # Store new shortcut
        self.reset_shortcut = key
        
        # Use display name if provided, otherwise use key
        if display_name is None:
            display_name = key
        
        if not callback:
            return False
        
        # Try to register global hotkey first
        if KEYBOARD_AVAILABLE:
            try:
                hotkey_str = self._convert_keysym_to_keyboard(key)
                
                if hotkey_str:
                    keyboard.add_hotkey(hotkey_str, callback, suppress=False)
                    self._global_hotkey_registered = True
                    
                    if self.message_callback:
                        self.message_callback(f"Global hotkey registered: {display_name}")
                    return True
                else:
                    if self.message_callback:
                        self.message_callback(f"Warning: Could not map key '{display_name}' for global hotkey")
            except Exception as ex:
                if self.message_callback:
                    self.message_callback(f"Warning: Could not register global hotkey '{display_name}': {ex}")
        
        # Fallback to Qt shortcut
        try:
            qt_sequence = self._convert_keysym_to_qt_sequence(key)
            if qt_sequence:
                from PyQt5.QtWidgets import QShortcut
                self._qt_shortcut = QShortcut(QKeySequence(qt_sequence), self.parent_widget.window())
                self._qt_shortcut.activated.connect(callback)
                
                if self.message_callback:
                    self.message_callback(f"Local shortcut registered: {display_name}")
                return True
            else:
                if self.message_callback:
                    self.message_callback(f"Warning: Could not map key '{display_name}' for local shortcut")
        except Exception as ex:
            if self.message_callback:
                self.message_callback(f"Warning: Could not register local shortcut '{display_name}': {ex}")
        
        return False
    
    def clear_shortcut(self):
        """Clear the current keyboard shortcut."""
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
    
    def _convert_keysym_to_keyboard(self, keysym):
        """Convert tkinter-style keysym to keyboard module format."""
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
        """Convert tkinter-style keysym to Qt key sequence."""
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