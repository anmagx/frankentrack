"""
Preferences panel for frankentrack GUI.

Provides user interface for application settings including theme selection.
"""
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QSpacerItem, QSizePolicy, QDialog, QSlider
)

from workers.gui_qt.managers.preferences_manager import PreferencesManager
from config.config import DEFAULT_THEME, THEMES_ENABLED, ALPHA_YAW, ALPHA_ROLL, ALPHA_PITCH, THRESH_DEBOUNCE_MS

# Import KeyCaptureDialog from calibration panel
from .calibration_panel import KeyCaptureDialog


class PreferencesPanel(QWidget):
    """Panel for application preferences and settings."""
    
    # Signal emitted when theme changes
    theme_changed = pyqtSignal(str)  # theme_name
    preferences_changed = pyqtSignal()  # General signal for any preference change
    
    def __init__(self, parent=None, preferences_manager=None):
        """
        Initialize preferences panel.
        
        Args:
            parent: Parent widget
            preferences_manager: PreferencesManager instance
        """
        super().__init__(parent)
        self.prefs_manager = preferences_manager or PreferencesManager()
        self.reset_shortcut = "None"
        self.calibration_panel = None  # Will be set by parent
        
        # Drift correction alpha values
        self.alpha_yaw = ALPHA_YAW
        self.alpha_pitch = ALPHA_PITCH
        self.alpha_roll = ALPHA_ROLL
        
        # Debounce timers for alpha updates
        self._alpha_yaw_timer = QTimer()
        self._alpha_yaw_timer.setSingleShot(True)
        self._alpha_yaw_timer.timeout.connect(self._apply_alpha_yaw)
        self._pending_alpha_yaw = None
        
        self._alpha_pitch_timer = QTimer()
        self._alpha_pitch_timer.setSingleShot(True)
        self._alpha_pitch_timer.timeout.connect(self._apply_alpha_pitch)
        self._pending_alpha_pitch = None
        
        self._alpha_roll_timer = QTimer()
        self._alpha_roll_timer.setSingleShot(True)
        self._alpha_roll_timer.timeout.connect(self._apply_alpha_roll)
        self._pending_alpha_roll = None
        
        # Debounce timer for preference saving
        self._prefs_save_timer = QTimer()
        self._prefs_save_timer.setSingleShot(True)
        self._prefs_save_timer.timeout.connect(self._emit_preferences_changed)
        
        self.setup_ui()
        self.load_preferences()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Theme selection group
        if THEMES_ENABLED:
            theme_group = QGroupBox("Appearance")
            theme_layout = QHBoxLayout()
            
            theme_label = QLabel("Theme:")
            self.theme_combo = QComboBox()
            self.theme_combo.addItems(["light", "dark"])
            self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
            
            theme_layout.addWidget(theme_label)
            theme_layout.addWidget(self.theme_combo)
            theme_layout.addStretch()
            
            theme_group.setLayout(theme_layout)
            layout.addWidget(theme_group)
        
        # Keyboard shortcuts group
        shortcuts_group = QGroupBox("Keyboard Shortcuts")
        shortcuts_layout = QVBoxLayout()
        
        # Reset orientation shortcut
        reset_layout = QHBoxLayout()
        reset_layout.addWidget(QLabel("Reset Orientation:"))
        
        self.shortcut_button = QPushButton("Set Shortcut...")
        self.shortcut_button.clicked.connect(self._on_set_shortcut)
        reset_layout.addWidget(self.shortcut_button)
        reset_layout.addStretch()
        
        shortcuts_layout.addLayout(reset_layout)
        shortcuts_group.setLayout(shortcuts_layout)
        layout.addWidget(shortcuts_group)
        
        # Drift correction group
        drift_group = QGroupBox("Drift Correction")
        drift_layout = QVBoxLayout()
        drift_layout.setSpacing(8)
        
        # Yaw alpha slider
        yaw_layout = QHBoxLayout()
        yaw_label = QLabel("Yaw Alpha:")
        yaw_label.setMinimumWidth(80)
        self.alpha_yaw_slider = QSlider(Qt.Horizontal)
        self.alpha_yaw_slider.setMinimum(950)  # 0.95
        self.alpha_yaw_slider.setMaximum(999)  # 0.999
        self.alpha_yaw_slider.setValue(int(self.alpha_yaw * 1000))
        self.alpha_yaw_slider.valueChanged.connect(self._on_alpha_yaw_changed)
        self.alpha_yaw_value = QLabel(f"{self.alpha_yaw:.3f}")
        self.alpha_yaw_value.setMinimumWidth(50)
        
        yaw_layout.addWidget(yaw_label)
        yaw_layout.addWidget(self.alpha_yaw_slider)
        yaw_layout.addWidget(self.alpha_yaw_value)
        drift_layout.addLayout(yaw_layout)
        
        # Pitch alpha slider
        pitch_layout = QHBoxLayout()
        pitch_label = QLabel("Pitch Alpha:")
        pitch_label.setMinimumWidth(80)
        self.alpha_pitch_slider = QSlider(Qt.Horizontal)
        self.alpha_pitch_slider.setMinimum(950)  # 0.95
        self.alpha_pitch_slider.setMaximum(999)  # 0.999
        self.alpha_pitch_slider.setValue(int(self.alpha_pitch * 1000))
        self.alpha_pitch_slider.valueChanged.connect(self._on_alpha_pitch_changed)
        self.alpha_pitch_value = QLabel(f"{self.alpha_pitch:.3f}")
        self.alpha_pitch_value.setMinimumWidth(50)
        
        pitch_layout.addWidget(pitch_label)
        pitch_layout.addWidget(self.alpha_pitch_slider)
        pitch_layout.addWidget(self.alpha_pitch_value)
        drift_layout.addLayout(pitch_layout)
        
        # Roll alpha slider
        roll_layout = QHBoxLayout()
        roll_label = QLabel("Roll Alpha:")
        roll_label.setMinimumWidth(80)
        self.alpha_roll_slider = QSlider(Qt.Horizontal)
        self.alpha_roll_slider.setMinimum(950)  # 0.95
        self.alpha_roll_slider.setMaximum(999)  # 0.999
        self.alpha_roll_slider.setValue(int(self.alpha_roll * 1000))
        self.alpha_roll_slider.valueChanged.connect(self._on_alpha_roll_changed)
        self.alpha_roll_value = QLabel(f"{self.alpha_roll:.3f}")
        self.alpha_roll_value.setMinimumWidth(50)
        
        roll_layout.addWidget(roll_label)
        roll_layout.addWidget(self.alpha_roll_slider)
        roll_layout.addWidget(self.alpha_roll_value)
        drift_layout.addLayout(roll_layout)
        
        # Add info label
        info_label = QLabel("Higher values = more gyro dominance, less accelerometer correction")
        info_label.setStyleSheet("color: #666666; font-size: 10px;")
        drift_layout.addWidget(info_label)
        
        drift_group.setLayout(drift_layout)
        layout.addWidget(drift_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_preferences)
        
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        
        button_layout.addStretch()
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.apply_btn)
        
        layout.addLayout(button_layout)
        
        # Add spacer at bottom
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)
        
        self.setLayout(layout)
    
    def load_preferences(self):
        """Load preferences from config and update UI."""
        if THEMES_ENABLED and hasattr(self, 'theme_combo'):
            current_theme = self.prefs_manager.get_theme()
            index = self.theme_combo.findText(current_theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
        
        # Load alpha preferences from config file
        try:
            prefs = self.prefs_manager.load()
            if 'calibration' in prefs:
                cal_prefs = prefs['calibration']
                
                # Load alpha values
                if 'alpha_yaw' in cal_prefs:
                    self.alpha_yaw = float(cal_prefs['alpha_yaw'])
                    self.alpha_yaw_slider.setValue(int(self.alpha_yaw * 1000))
                    self.alpha_yaw_value.setText(f"{self.alpha_yaw:.3f}")
                
                if 'alpha_pitch' in cal_prefs:
                    self.alpha_pitch = float(cal_prefs['alpha_pitch'])
                    self.alpha_pitch_slider.setValue(int(self.alpha_pitch * 1000))
                    self.alpha_pitch_value.setText(f"{self.alpha_pitch:.3f}")
                
                if 'alpha_roll' in cal_prefs:
                    self.alpha_roll = float(cal_prefs['alpha_roll'])
                    self.alpha_roll_slider.setValue(int(self.alpha_roll * 1000))
                    self.alpha_roll_value.setText(f"{self.alpha_roll:.3f}")
        except Exception:
            pass
    
    def _on_theme_changed(self, theme_name):
        """Handle theme selection change."""
        if THEMES_ENABLED:
            # Save preference and emit signals
            self.prefs_manager.set_theme(theme_name)
            self.theme_changed.emit(theme_name)
            self.preferences_changed.emit()  # Notify parent to save all preferences
    
    def _apply_preferences(self):
        """Apply current preference settings."""
        if THEMES_ENABLED and hasattr(self, 'theme_combo'):
            theme_name = self.theme_combo.currentText()
            self.prefs_manager.set_theme(theme_name)
            self.theme_changed.emit(theme_name)
        
        # Visual feedback
        self.apply_btn.setText("Applied!")
        self.apply_btn.setEnabled(False)
        
        # Reset button text after delay
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1500, lambda: (
            self.apply_btn.setText("Apply"),
            self.apply_btn.setEnabled(True)
        ))
    
    def _on_alpha_yaw_changed(self, value):
        """Handle yaw alpha slider change with debouncing."""
        self.alpha_yaw = value / 1000.0
        self.alpha_yaw_value.setText(f"{self.alpha_yaw:.3f}")
        
        # Store pending value for debounced sending
        self._pending_alpha_yaw = self.alpha_yaw
        
        # Restart debounce timer
        self._alpha_yaw_timer.stop()
        self._alpha_yaw_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _on_alpha_pitch_changed(self, value):
        """Handle pitch alpha slider change with debouncing."""
        self.alpha_pitch = value / 1000.0
        self.alpha_pitch_value.setText(f"{self.alpha_pitch:.3f}")
        
        # Store pending value for debounced sending
        self._pending_alpha_pitch = self.alpha_pitch
        
        # Restart debounce timer
        self._alpha_pitch_timer.stop()
        self._alpha_pitch_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _on_alpha_roll_changed(self, value):
        """Handle roll alpha slider change with debouncing."""
        self.alpha_roll = value / 1000.0
        self.alpha_roll_value.setText(f"{self.alpha_roll:.3f}")
        
        # Store pending value for debounced sending
        self._pending_alpha_roll = self.alpha_roll
        
        # Restart debounce timer
        self._alpha_roll_timer.stop()
        self._alpha_roll_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _apply_alpha_yaw(self):
        """Apply yaw alpha value to fusion worker (debounced)."""
        if self._pending_alpha_yaw is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    safe_queue_put(self.calibration_panel.control_queue, 
                                 ('set_alpha_yaw', self._pending_alpha_yaw), timeout=QUEUE_PUT_TIMEOUT)
                self._pending_alpha_yaw = None
            except Exception:
                pass
    
    def _apply_alpha_pitch(self):
        """Apply pitch alpha value to fusion worker (debounced)."""
        if self._pending_alpha_pitch is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    safe_queue_put(self.calibration_panel.control_queue, 
                                 ('set_alpha_pitch', self._pending_alpha_pitch), timeout=QUEUE_PUT_TIMEOUT)
                self._pending_alpha_pitch = None
            except Exception:
                pass
    
    def _apply_alpha_roll(self):
        """Apply roll alpha value to fusion worker (debounced)."""
        if self._pending_alpha_roll is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    safe_queue_put(self.calibration_panel.control_queue, 
                                 ('set_alpha_roll', self._pending_alpha_roll), timeout=QUEUE_PUT_TIMEOUT)
                self._pending_alpha_roll = None
            except Exception:
                pass
    
    def _emit_preferences_changed(self):
        """Emit preferences changed signal (debounced)."""
        self.preferences_changed.emit()
    
    def _trigger_preference_save(self):
        """Trigger a debounced preference save."""
        self._prefs_save_timer.stop()
        self._prefs_save_timer.start(500)  # 500ms delay for preference saving
    
    def _reset_to_defaults(self):
        """Reset preferences to default values."""
        if THEMES_ENABLED and hasattr(self, 'theme_combo'):
            # Reset theme to default
            index = self.theme_combo.findText(DEFAULT_THEME)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
            
            # Save and apply
            self.prefs_manager.set_theme(DEFAULT_THEME)
            self.theme_changed.emit(DEFAULT_THEME)
        
        # Reset alpha values to defaults
        self.alpha_yaw = ALPHA_YAW
        self.alpha_pitch = ALPHA_PITCH
        self.alpha_roll = ALPHA_ROLL
        
        # Update sliders and labels
        self.alpha_yaw_slider.setValue(int(self.alpha_yaw * 1000))
        self.alpha_yaw_value.setText(f"{self.alpha_yaw:.3f}")
        self.alpha_pitch_slider.setValue(int(self.alpha_pitch * 1000))
        self.alpha_pitch_value.setText(f"{self.alpha_pitch:.3f}")
        self.alpha_roll_slider.setValue(int(self.alpha_roll * 1000))
        self.alpha_roll_value.setText(f"{self.alpha_roll:.3f}")
        
        # Update fusion worker with debounced values
        self._pending_alpha_yaw = self.alpha_yaw
        self._pending_alpha_pitch = self.alpha_pitch
        self._pending_alpha_roll = self.alpha_roll
        
        # Apply immediately (no debounce needed for reset)
        self._apply_alpha_yaw()
        self._apply_alpha_pitch()
        self._apply_alpha_roll()
        
        # Visual feedback
        self.reset_btn.setText("Reset!")
        self.reset_btn.setEnabled(False)
        
        # Reset button text after delay
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1500, lambda: (
            self.reset_btn.setText("Reset to Defaults"),
            self.reset_btn.setEnabled(True)
        ))
    
    def _on_set_shortcut(self):
        """Open dialog to capture a keyboard shortcut for reset orientation."""
        dialog = KeyCaptureDialog(self.window(), self.reset_shortcut)  # Use window() for proper theme context
        
        if dialog.exec_() == QDialog.Accepted and dialog.captured_key:
            key = dialog.captured_key
            display_name = dialog.display_name or dialog.captured_key
            
            # Store shortcut
            self.reset_shortcut = key
            
            # Update button text
            if key and key != 'None':
                self.shortcut_button.setText(f"Shortcut: {display_name}")
            else:
                self.shortcut_button.setText("Set Shortcut...")
            
            # Apply to calibration panel immediately (this registers the hotkey)
            if self.calibration_panel:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut(key, display_name))
            
            self.preferences_changed.emit()
    
    def load_shortcut_preferences(self, prefs):
        """Load shortcut preferences from saved config."""
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
                
                self.reset_shortcut = shortcut
                self.shortcut_button.setText(f"Shortcut: {display_name}")
                
                # Apply to calibration panel to register the hotkey
                if self.calibration_panel:
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut(shortcut, display_name))
            except Exception:
                pass
        else:
            self.reset_shortcut = "None"
            self.shortcut_button.setText("Set Shortcut...")
            
            # Ensure calibration panel also has no shortcut
            if self.calibration_panel:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut("None", "None"))
    
    def get_shortcut_preferences(self):
        """Get shortcut preferences for saving."""
        return {
            'reset_shortcut': self.reset_shortcut,
            'alpha_yaw': f"{self.alpha_yaw:.3f}",
            'alpha_pitch': f"{self.alpha_pitch:.3f}",
            'alpha_roll': f"{self.alpha_roll:.3f}"
        }
    
    def connect_calibration_panel(self, calibration_panel):
        """Connect to calibration panel for shortcut updates."""
        self.calibration_panel = calibration_panel
    
    def get_panel_name(self) -> str:
        """Return panel display name."""
        return "Preferences"