"""
Orientation Panel for frankentrack GUI.

Displays Euler angles (Yaw, Pitch, Roll), position (X, Y, Z),
drift correction controls, and orientation reset functionality.
"""
import tkinter as tk
from tkinter import ttk

from config.config import QUEUE_PUT_TIMEOUT
from util.error_utils import safe_queue_put

from workers.gui.managers.icon_helper import set_window_icon

# Global hotkey support
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False




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
        
        # Drift correction status (display-only, control moved to CalibrationPanel)
        self.drift_status_var = tk.StringVar(value="Drift Correction Inactive")
        
        # Keyboard shortcut for reset orientation
        self.reset_shortcut_var = tk.StringVar(value="None")
        self._shortcut_binding_id = None
        self._global_hotkey_registered = False

        
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
        # Drift controls moved to `CalibrationPanel` to keep this class focused on display
        
        # Build right section components
        self._build_drift_status(right_frame)
        # Add Reset Orientation button and Set Shortcut button here
        try:
            btn_container = ttk.Frame(right_frame)
            btn_container.pack(padx=6, pady=(4, 6))
            
            self.reset_btn = ttk.Button(
                btn_container,
                text="Reset Orientation",
                command=self._on_reset
            )
            self.reset_btn.pack(side='top', pady=(0, 2))
            
            self.shortcut_btn_text = tk.StringVar(value="Set Shortcut...")
            self.shortcut_btn = ttk.Button(
                btn_container,
                textvariable=self.shortcut_btn_text,
                command=self._on_set_shortcut
            )
            self.shortcut_btn.pack(side='top')
        except Exception:
            pass
    
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
    
    # Drift control UI and logic moved to `calibration_panel.CalibrationPanel`

        
    
    def _build_drift_status(self, parent):
        """Build drift correction status indicator."""
        self.drift_status_lbl = ttk.Label(
            parent,
            textvariable=self.drift_status_var,
            foreground="red"
        )
        self.drift_status_lbl.pack(padx=6, pady=(6, 4))
    
    
    def _on_drift_angle_change(self, val):
        """Handle drift angle slider changes."""
        try:
            v = float(val)
        except Exception:
            v = 0.0
        
        self.drift_angle_display.set(f"{v:.1f}")
        # (Control forwarding moved to CalibrationPanel)

    
    
    def _on_set_shortcut(self):
        """Open dialog to capture a keyboard shortcut for reset orientation."""
        # Create popup dialog
        dialog = tk.Toplevel(self)
        dialog.title("Set Shortcut Key")
        # Use same icon as main GUI if available
        try:
            set_window_icon(dialog)
        except Exception:
            pass
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.geometry("300x120")
        
        
        
        # Center dialog over parent
        try:
            dialog.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass
        
        # Dialog content
        label = ttk.Label(
            dialog, 
            text="Press any key to set as shortcut.\n(This should be the same key as in opentrack)\n(Esc to cancel)",
            justify='center',
            padding=20
        )
        label.pack(expand=True)
        
        current_label = ttk.Label(
            dialog,
            text=f"Current: {self.reset_shortcut_var.get()}",
            foreground='gray'
        )
        current_label.pack()
        
        # Capture key press
        def on_key(event):
            # Use keysym for the key name, but also check keycode for numpad
            key = event.keysym
            keycode = event.keycode
            
            # Cancel on Escape
            if key == 'Escape':
                dialog.destroy()
                return
            
            # Windows numpad keycodes (with NumLock on, these send regular keysyms):
            # 96-105: Numpad 0-9
            # 106: Numpad *, 107: Numpad +, 109: Numpad -, 110: Numpad ., 111: Numpad /
            numpad_keycode_map = {
                96: ('KP_0', 'Numpad 0'), 97: ('KP_1', 'Numpad 1'), 98: ('KP_2', 'Numpad 2'),
                99: ('KP_3', 'Numpad 3'), 100: ('KP_4', 'Numpad 4'), 101: ('KP_5', 'Numpad 5'),
                102: ('KP_6', 'Numpad 6'), 103: ('KP_7', 'Numpad 7'), 104: ('KP_8', 'Numpad 8'),
                105: ('KP_9', 'Numpad 9'), 110: ('KP_Decimal', 'Numpad .'),
                111: ('KP_Divide', 'Numpad /'), 106: ('KP_Multiply', 'Numpad *'),
                109: ('KP_Subtract', 'Numpad -'), 107: ('KP_Add', 'Numpad +')
            }
            
            # Check if this is a numpad key by keycode
            if keycode in numpad_keycode_map:
                binding_key, display_name = numpad_keycode_map[keycode]
            elif key.startswith('KP_'):
                # NumLock off case - already has KP_ prefix
                numpad_map = {
                    'KP_0': 'Numpad 0', 'KP_1': 'Numpad 1', 'KP_2': 'Numpad 2',
                    'KP_3': 'Numpad 3', 'KP_4': 'Numpad 4', 'KP_5': 'Numpad 5',
                    'KP_6': 'Numpad 6', 'KP_7': 'Numpad 7', 'KP_8': 'Numpad 8',
                    'KP_9': 'Numpad 9', 'KP_Decimal': 'Numpad .', 'KP_Divide': 'Numpad /',
                    'KP_Multiply': 'Numpad *', 'KP_Subtract': 'Numpad -', 'KP_Add': 'Numpad +',
                    'KP_Enter': 'Numpad Enter'
                }
                binding_key = key
                display_name = numpad_map.get(key, key)
            else:
                # Regular key
                binding_key = key
                display_name = key
            
            # Store the shortcut (use binding_key for actual binding)
            self._set_reset_shortcut(binding_key, display_name)
            
            # Show brief confirmation
            label.config(text=f"Shortcut set to: {display_name}")
            dialog.after(500, dialog.destroy)
        
        dialog.bind('<Key>', on_key)
        dialog.focus_set()
        dialog.grab_set()
    
    def _set_reset_shortcut(self, key, display_name=None):
        """Set the keyboard shortcut for reset orientation.
        
        Args:
            key: Key symbol (e.g., 'r', 'F5', 'space', 'KP_0')
            display_name: Optional friendly display name (e.g., 'Numpad 0')
        """
        # Remove old binding if exists
        if self._shortcut_binding_id is not None:
            try:
                root = self.winfo_toplevel()
                root.unbind(self._shortcut_binding_id)
            except Exception:
                pass
            self._shortcut_binding_id = None
        
        # Remove old global hotkey if exists
        if self._global_hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
                self._global_hotkey_registered = False
            except Exception:
                pass
        
        # Store new shortcut (use actual keysym for persistence)
        self.reset_shortcut_var.set(key)
        
        # Use display name if provided, otherwise use key
        if display_name is None:
            display_name = key
        
        # Update button text
        self.shortcut_btn_text.set(f"Shortcut: {display_name}")
        
        # Register global hotkey
        if KEYBOARD_AVAILABLE:
            try:
                # Convert Tkinter keysym to keyboard module format
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
            # Fallback to local binding if keyboard module not available
            try:
                root = self.winfo_toplevel()
                
                # For numpad keys, bind using <KeyPress> with a filter function
                if key.startswith('KP_'):
                    numpad_keycode_map = {
                        'KP_0': 96, 'KP_1': 97, 'KP_2': 98, 'KP_3': 99, 'KP_4': 100,
                        'KP_5': 101, 'KP_6': 102, 'KP_7': 103, 'KP_8': 104, 'KP_9': 105,
                        'KP_Decimal': 110, 'KP_Divide': 111, 'KP_Multiply': 106,
                        'KP_Subtract': 109, 'KP_Add': 107
                    }
                    
                    target_keycode = numpad_keycode_map.get(key)
                    if target_keycode:
                        def keypress_handler(event):
                            if event.keycode == target_keycode:
                                self._on_reset()
                        
                        self._shortcut_binding_id = root.bind('<KeyPress>', keypress_handler, add='+')
                    else:
                        binding = f'<{key}>'
                        self._shortcut_binding_id = root.bind(binding, lambda e: self._on_reset())
                else:
                    # Regular key - use standard binding
                    binding = f'<{key}>'
                    self._shortcut_binding_id = root.bind(binding, lambda e: self._on_reset())
                    
            except Exception as ex:
                if self.message_callback:
                    self.message_callback(f"Warning: Could not bind shortcut key '{display_name}': {ex}")
    
    def _convert_keysym_to_keyboard(self, keysym):
        """Convert Tkinter keysym to keyboard module format.
        
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
    
    def _clear_reset_shortcut(self):
        """Clear the keyboard shortcut binding."""
        if self._shortcut_binding_id is not None:
            try:
                root = self.winfo_toplevel()
                # For <KeyPress> bindings with add='+', we need to unbind properly
                # Get the binding and remove it
                root.unbind('<KeyPress>', self._shortcut_binding_id)
            except Exception:
                pass
            self._shortcut_binding_id = None
        
        # Remove global hotkey
        if self._global_hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
                self._global_hotkey_registered = False
            except Exception:
                pass
        
        self.reset_shortcut_var.set("None")
        self.shortcut_btn_text.set("Set Shortcut...")
    
    def _on_reset(self):
        """Handle orientation reset button click."""
        # Send non-destructive orientation reset command to fusion worker.
        # Use 'reset_orientation' so the fusion worker resets orientation
        # state but does not clear gyro calibration (which is intended only
        # for a full session reset triggered by stopping serial).
        try:
            if self.control_queue:
                if not safe_queue_put(self.control_queue, 'reset_orientation', timeout=QUEUE_PUT_TIMEOUT):
                    if self.message_callback:
                        self.message_callback("Failed to send reset command")
                    return
        except Exception:
            # If sending the command fails for unexpected reasons, report and continue
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

    def _on_recalibrate(self):
        """Request runtime gyro bias recalibration from the fusion worker."""
        # Recalibration is handled by CalibrationPanel now; keep as no-op placeholder
        if self.message_callback:
            self.message_callback("Gyro bias recalibration requested (handled by CalibrationPanel)")
    
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
            dict: Dictionary with preferences including reset shortcut
        """
        return {
            'reset_shortcut': self.reset_shortcut_var.get()
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional preference keys including 'reset_shortcut'
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
    
    def reset_position_offsets(self):
        """Reset position offsets to zero (for testing or manual reset)."""
        self._x_offset = 0.0
        self._y_offset = 0.0
        self._last_raw_translation = (0.0, 0.0, 0.0)
        self.x_var.set("0.00")
        self.y_var.set("0.00")
        self.z_var.set("0.00")
    
    # Drift controls (get/set) have been moved to CalibrationPanel
    
