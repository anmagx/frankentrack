"""
Preferences panel for frankentrack GUI.

Provides user interface for application settings including theme selection.
"""
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QSpacerItem, QSizePolicy, QDialog, QSlider,
    QSpinBox
)

from workers.gui_qt.managers.preferences_manager import PreferencesManager
from config.config import DEFAULT_THEME, THEMES_ENABLED, ALPHA_YAW, ALPHA_ROLL, ALPHA_PITCH, THRESH_DEBOUNCE_MS, STATIONARY_GYRO_THRESHOLD, STATIONARY_DEBOUNCE_S, DRIFT_SMOOTHING_TIME, DRIFT_TRANSITION_CURVE, GYRO_BIAS_CAL_SAMPLES, QUEUE_PUT_TIMEOUT

# Import KeyCaptureDialog from calibration panel
from .calibration_panel import KeyCaptureDialog
from util.error_utils import (
    safe_queue_put
)


class PreferencesPanel(QWidget):
    """Panel for application preferences and settings."""
    
    # Signal emitted when theme changes
    theme_changed = pyqtSignal(str)  # theme_name
    preferences_changed = pyqtSignal()  # General signal for any preference change
    
    def __init__(self, parent=None, preferences_manager=None, 
                 input_command_queue=None, input_response_queue=None):
        """
        Initialize preferences panel.
        
        Args:
            parent: Parent widget
            preferences_manager: PreferencesManager instance
            input_command_queue: Queue for sending commands to input worker
            input_response_queue: Queue for receiving responses from input worker
        """
        super().__init__(parent)
        self.prefs_manager = preferences_manager or PreferencesManager()
        self.reset_shortcut = "None"
        self.reset_shortcut_display_name = "None"
        self.calibration_panel = None  # Will be set by parent
        
        # Store input worker queues
        self.input_command_queue = input_command_queue
        self.input_response_queue = input_response_queue
        
        # Drift correction alpha values
        self.alpha_pitch = ALPHA_PITCH
        self.alpha_roll = ALPHA_ROLL
        
        # Stationary detection parameters
        self.stationary_gyro_threshold = STATIONARY_GYRO_THRESHOLD
        self.stationary_debounce_s = STATIONARY_DEBOUNCE_S
        
        # Drift correction parameters
        self.drift_smoothing_time = DRIFT_SMOOTHING_TIME
        self.drift_transition_curve = DRIFT_TRANSITION_CURVE
        
        # Gyro calibration parameters
        self.gyro_bias_cal_samples = GYRO_BIAS_CAL_SAMPLES
        
        # Debounce timers for alpha updates
        self._alpha_pitch_timer = QTimer()
        self._alpha_pitch_timer.setSingleShot(True)
        self._alpha_pitch_timer.timeout.connect(self._apply_alpha_pitch)
        self._pending_alpha_pitch = None
        
        self._alpha_roll_timer = QTimer()
        self._alpha_roll_timer.setSingleShot(True)
        self._alpha_roll_timer.timeout.connect(self._apply_alpha_roll)
        self._pending_alpha_roll = None
        
        self._stationary_gyro_timer = QTimer()
        self._stationary_gyro_timer.setSingleShot(True)
        self._stationary_gyro_timer.timeout.connect(self._apply_stationary_gyro)
        self._pending_stationary_gyro = None
        
        self._stationary_debounce_timer = QTimer()
        self._stationary_debounce_timer.setSingleShot(True)
        self._stationary_debounce_timer.timeout.connect(self._apply_stationary_debounce)
        self._pending_stationary_debounce = None
        
        self._drift_smoothing_timer = QTimer()
        self._drift_smoothing_timer.setSingleShot(True)
        self._drift_smoothing_timer.timeout.connect(self._apply_drift_smoothing)
        self._pending_drift_smoothing = None
        
        # Debounce timer for preference saving
        self._prefs_save_timer = QTimer()
        self._prefs_save_timer.setSingleShot(True)
        self._prefs_save_timer.timeout.connect(self._emit_preferences_changed)
        
        self.setup_ui()
    
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
        
        # Drift smoothing time slider
        smoothing_layout = QHBoxLayout()
        smoothing_label = QLabel("Smoothing Time:")
        smoothing_label.setMinimumWidth(80)
        self.drift_smoothing_slider = QSlider(Qt.Horizontal)
        self.drift_smoothing_slider.setMinimum(0)    # 0.0 seconds
        self.drift_smoothing_slider.setMaximum(50)   # 5.0 seconds
        self.drift_smoothing_slider.setValue(int(self.drift_smoothing_time * 10))
        self.drift_smoothing_slider.valueChanged.connect(self._on_drift_smoothing_changed)
        self.drift_smoothing_value = QLabel(f"{self.drift_smoothing_time:.1f} s")
        self.drift_smoothing_value.setMinimumWidth(50)
        
        smoothing_layout.addWidget(smoothing_label)
        smoothing_layout.addWidget(self.drift_smoothing_slider)
        smoothing_layout.addWidget(self.drift_smoothing_value)
        drift_layout.addLayout(smoothing_layout)
        
        # Drift transition curve dropdown
        curve_layout = QHBoxLayout()
        curve_label = QLabel("Transition Curve:")
        curve_label.setMinimumWidth(80)
        self.drift_curve_combo = QComboBox()
        self.drift_curve_combo.addItems(["exponential", "cosine", "linear", "quadratic"])
        self.drift_curve_combo.setCurrentText(self.drift_transition_curve)
        self.drift_curve_combo.currentTextChanged.connect(self._on_drift_curve_changed)
        
        curve_layout.addWidget(curve_label)
        curve_layout.addWidget(self.drift_curve_combo)
        curve_layout.addStretch()
        drift_layout.addLayout(curve_layout)
        
        # Add info label
        info_label = QLabel("Higher alpha = more gyro dominance. Smoothing time controls drift correction speed. Transition curves: exponential (original), cosine (smooth), linear, quadratic (sharp).")
        info_label.setStyleSheet("color: #666666; font-size: 10px;")
        drift_layout.addWidget(info_label)
        
        drift_group.setLayout(drift_layout)
        layout.addWidget(drift_group)
        
        # Stationary detection group
        stationary_group = QGroupBox("Stationary Detection")
        stationary_layout = QVBoxLayout()
        stationary_layout.setSpacing(8)
        
        # Gyro threshold slider (1.0 to 20.0 deg/s)
        gyro_layout = QHBoxLayout()
        gyro_label = QLabel("Gyro Threshold:")
        gyro_label.setMinimumWidth(100)
        self.stationary_gyro_slider = QSlider(Qt.Horizontal)
        self.stationary_gyro_slider.setMinimum(10)  # 1.0 deg/s
        self.stationary_gyro_slider.setMaximum(200)  # 20.0 deg/s
        self.stationary_gyro_slider.setValue(int(self.stationary_gyro_threshold * 10))
        self.stationary_gyro_slider.valueChanged.connect(self._on_stationary_gyro_changed)
        self.stationary_gyro_value = QLabel(f"{self.stationary_gyro_threshold:.1f} °/s")
        self.stationary_gyro_value.setMinimumWidth(60)
        
        gyro_layout.addWidget(gyro_label)
        gyro_layout.addWidget(self.stationary_gyro_slider)
        gyro_layout.addWidget(self.stationary_gyro_value)
        stationary_layout.addLayout(gyro_layout)
        
        # Debounce time slider (0.05 to 1.0 seconds)
        debounce_layout = QHBoxLayout()
        debounce_label = QLabel("Debounce Time:")
        debounce_label.setMinimumWidth(100)
        self.stationary_debounce_slider = QSlider(Qt.Horizontal)
        self.stationary_debounce_slider.setMinimum(5)  # 0.05 seconds
        self.stationary_debounce_slider.setMaximum(100)  # 1.0 seconds
        self.stationary_debounce_slider.setValue(int(self.stationary_debounce_s * 100))
        self.stationary_debounce_slider.valueChanged.connect(self._on_stationary_debounce_changed)
        self.stationary_debounce_value = QLabel(f"{self.stationary_debounce_s:.2f} s")
        self.stationary_debounce_value.setMinimumWidth(60)
        
        debounce_layout.addWidget(debounce_label)
        debounce_layout.addWidget(self.stationary_debounce_slider)
        debounce_layout.addWidget(self.stationary_debounce_value)
        stationary_layout.addLayout(debounce_layout)
        
        # Add info label for stationary detection
        stationary_info_label = QLabel("Controls when the device is considered stationary for drift correction")
        stationary_info_label.setStyleSheet("color: #666666; font-size: 10px;")
        stationary_layout.addWidget(stationary_info_label)
        
        stationary_group.setLayout(stationary_layout)
        layout.addWidget(stationary_group)
        
        # Gyro calibration group
        gyro_group = QGroupBox("Gyro Calibration")
        gyro_layout = QVBoxLayout()
        gyro_layout.setSpacing(8)
        
        # Calibration samples slider (500 to 5000)
        samples_layout = QHBoxLayout()
        samples_label = QLabel("Calibration Samples:")
        samples_label.setMinimumWidth(100)
        self.gyro_samples_slider = QSlider(Qt.Horizontal)
        self.gyro_samples_slider.setMinimum(500)  # 500 samples
        self.gyro_samples_slider.setMaximum(5000)  # 5000 samples
        self.gyro_samples_slider.setValue(self.gyro_bias_cal_samples)
        self.gyro_samples_slider.valueChanged.connect(self._on_gyro_samples_changed)
        self.gyro_samples_value = QLabel(str(self.gyro_bias_cal_samples))
        self.gyro_samples_value.setMinimumWidth(60)
        
        samples_layout.addWidget(samples_label)
        samples_layout.addWidget(self.gyro_samples_slider)
        samples_layout.addWidget(self.gyro_samples_value)
        gyro_layout.addLayout(samples_layout)
        
        # Add info label for gyro calibration
        gyro_info_label = QLabel("Number of samples collected when recalibrating gyro bias. More samples = better accuracy but slower calibration.")
        gyro_info_label.setStyleSheet("color: #666666; font-size: 10px;")
        gyro_layout.addWidget(gyro_info_label)
        
        gyro_group.setLayout(gyro_layout)
        layout.addWidget(gyro_group)
        
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
        """Load all preferences from config file via PreferencesManager, update UI, and sync with fusion worker."""
        # Load all preferences using PreferencesManager
        prefs = self.prefs_manager.load()
        
        # Load theme preferences
        if THEMES_ENABLED and hasattr(self, 'theme_combo'):
            current_theme = self.prefs_manager.get_theme()
            index = self.theme_combo.findText(current_theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
        
        # Extract calibration preferences
        cal_prefs = prefs.get('calibration', {})
        
        # Load and apply all calibration settings
        self._load_alpha_settings(cal_prefs)
        self._load_stationary_settings(cal_prefs)
        self._load_drift_settings(cal_prefs)
        self._load_gyro_settings(cal_prefs)
        self._load_shortcut_settings(cal_prefs)
        
        # Send settings to fusion worker
        self._apply_settings_to_fusion_worker(cal_prefs)
    

    
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
    
    def _on_stationary_gyro_changed(self, value):
        """Handle stationary gyro threshold slider change with debouncing."""
        self.stationary_gyro_threshold = value / 10.0
        self.stationary_gyro_value.setText(f"{self.stationary_gyro_threshold:.1f} °/s")
        
        # Store pending value for debounced sending
        self._pending_stationary_gyro = self.stationary_gyro_threshold
        
        # Restart debounce timer
        self._stationary_gyro_timer.stop()
        self._stationary_gyro_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _on_stationary_debounce_changed(self, value):
        """Handle stationary debounce time slider change with debouncing."""
        self.stationary_debounce_s = value / 100.0
        self.stationary_debounce_value.setText(f"{self.stationary_debounce_s:.2f} s")
        
        # Store pending value for debounced sending
        self._pending_stationary_debounce = self.stationary_debounce_s
        
        # Restart debounce timer
        self._stationary_debounce_timer.stop()
        self._stationary_debounce_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _apply_stationary_gyro(self):
        """Apply stationary gyro threshold to fusion worker (debounced)."""
        if self._pending_stationary_gyro is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    # Note: This would need to be implemented in the fusion worker
                    # For now, we'll store it in preferences
                    pass
                self._pending_stationary_gyro = None
            except Exception:
                pass
    
    def _apply_stationary_debounce(self):
        """Apply stationary debounce time to fusion worker (debounced)."""
        if self._pending_stationary_debounce is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    # Note: This would need to be implemented in the fusion worker
                    # For now, we'll store it in preferences
                    pass
                self._pending_stationary_debounce = None
            except Exception:
                pass
    
    def _on_drift_smoothing_changed(self, value):
        """Handle drift smoothing time slider change with debouncing."""
        self.drift_smoothing_time = value / 10.0
        self.drift_smoothing_value.setText(f"{self.drift_smoothing_time:.1f} s")
        
        # Store pending value for debounced sending
        self._pending_drift_smoothing = self.drift_smoothing_time
        
        # Restart debounce timer
        self._drift_smoothing_timer.stop()
        self._drift_smoothing_timer.start(THRESH_DEBOUNCE_MS)
        
        # Debounced preference save
        self._trigger_preference_save()
    
    def _on_drift_curve_changed(self, curve_type):
        """Handle drift transition curve selection change."""
        self.drift_transition_curve = curve_type
        
        # Send command to fusion worker for live update
        if hasattr(self.calibration_panel, 'control_queue'):
            try:
                control_queue = self.calibration_panel.control_queue
                if control_queue and not control_queue.full():
                    safe_queue_put(control_queue, ('set_drift_curve_type', curve_type), timeout=QUEUE_PUT_TIMEOUT)
                    print(f"[Preferences] Sent drift curve type: {curve_type}")
            except Exception as e:
                print(f"[Preferences] Failed to send drift curve command: {e}")
        
        self._trigger_preference_save()
    
    def _on_gyro_samples_changed(self, value):
        """Handle gyro calibration samples slider change."""
        self.gyro_bias_cal_samples = value
        self.gyro_samples_value.setText(str(value))
        # Note: This affects next recalibration, not current session
        self._trigger_preference_save()
    
    def _apply_drift_smoothing(self):
        """Apply drift smoothing time to fusion worker (debounced)."""
        if self._pending_drift_smoothing is not None and self.calibration_panel:
            try:
                if hasattr(self.calibration_panel, 'control_queue'):
                    from util.error_utils import safe_queue_put
                    from config.config import QUEUE_PUT_TIMEOUT
                    
                    # Send command to fusion worker
                    control_queue = self.calibration_panel.control_queue
                    if control_queue and not control_queue.full():
                        safe_queue_put(control_queue, ('set_drift_smoothing_time', self._pending_drift_smoothing), timeout=QUEUE_PUT_TIMEOUT)
                        
                self._pending_drift_smoothing = None
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
        self.alpha_pitch = ALPHA_PITCH
        self.alpha_roll = ALPHA_ROLL
        
        # Reset stationary detection parameters to defaults
        self.stationary_gyro_threshold = STATIONARY_GYRO_THRESHOLD
        self.stationary_debounce_s = STATIONARY_DEBOUNCE_S
        
        # Reset drift correction parameters to defaults
        self.drift_smoothing_time = DRIFT_SMOOTHING_TIME
        self.drift_transition_curve = DRIFT_TRANSITION_CURVE
        
        # Reset gyro calibration parameters to defaults
        self.gyro_bias_cal_samples = GYRO_BIAS_CAL_SAMPLES
        
        # Update sliders and labels
        self.alpha_pitch_slider.setValue(int(self.alpha_pitch * 1000))
        self.alpha_pitch_value.setText(f"{self.alpha_pitch:.3f}")
        self.alpha_roll_slider.setValue(int(self.alpha_roll * 1000))
        self.alpha_roll_value.setText(f"{self.alpha_roll:.3f}")
        
        # Update stationary detection sliders
        self.stationary_gyro_slider.setValue(int(self.stationary_gyro_threshold * 10))
        self.stationary_gyro_value.setText(f"{self.stationary_gyro_threshold:.1f} °/s")
        self.stationary_debounce_slider.setValue(int(self.stationary_debounce_s * 100))
        self.stationary_debounce_value.setText(f"{self.stationary_debounce_s:.2f} s")
        
        # Update drift correction sliders
        self.drift_smoothing_slider.setValue(int(self.drift_smoothing_time * 10))
        self.drift_smoothing_value.setText(f"{self.drift_smoothing_time:.1f} s")
        
        # Update drift curve dropdown
        index = self.drift_curve_combo.findText(self.drift_transition_curve)
        if index >= 0:
            self.drift_curve_combo.setCurrentIndex(index)
        
        # Update gyro calibration sliders
        self.gyro_samples_slider.setValue(self.gyro_bias_cal_samples)
        self.gyro_samples_value.setText(str(self.gyro_bias_cal_samples))
        
        # Update fusion worker with debounced values
        self._pending_alpha_pitch = self.alpha_pitch
        self._pending_alpha_roll = self.alpha_roll
        self._pending_stationary_gyro = self.stationary_gyro_threshold
        self._pending_stationary_debounce = self.stationary_debounce_s
        self._pending_drift_smoothing = self.drift_smoothing_time
        
        # Apply immediately (no debounce needed for reset)
        self._apply_alpha_pitch()
        self._apply_alpha_roll()
        self._apply_stationary_gyro()
        self._apply_stationary_debounce()
        self._apply_drift_smoothing()
        
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
        # Temporarily clear any existing shortcut monitoring to free up joysticks
        if self.input_command_queue:
            try:
                self.input_command_queue.put(('clear_shortcut',), timeout=0.1)
                print("[Preferences] Cleared existing shortcut for capture")
            except Exception as e:
                print(f"[Preferences] Error clearing shortcut: {e}")
        
        dialog = KeyCaptureDialog(
            self.window(), 
            self.reset_shortcut,
            self.input_command_queue,
            self.input_response_queue
        )  # Use window() for proper theme context
        
        if dialog.exec_() == QDialog.Accepted and dialog.captured_key:
            key = dialog.captured_key
            display_name = dialog.display_name or dialog.captured_key
            
            # Store shortcut and display name
            self.reset_shortcut = key
            self.reset_shortcut_display_name = display_name
            print(f"[Preferences] Captured shortcut: key={key}, display_name={display_name}")
            
            # Update button text
            if key and key != 'None':
                self.shortcut_button.setText(f"Shortcut: {display_name}")
            else:
                self.shortcut_button.setText("Set Shortcut...")
            
            # Stop capture mode and immediately activate the new shortcut
            if self.input_command_queue:
                try:
                    # First stop capture mode (stops both temporary listeners)
                    self.input_command_queue.put(('stop_capture',), timeout=0.1)
                    print(f"[Preferences] Stopped capture mode")
                    # Then set the shortcut (starts appropriate permanent listener)
                    self.input_command_queue.put(('set_shortcut', key, display_name), timeout=0.1)
                    print(f"[Preferences] Sent shortcut to input worker: {key}")
                except Exception as e:
                    print(f"[Preferences] Error sending shortcut to input worker: {e}")
            
            # Update calibration panel's reset button text immediately
            if self.calibration_panel:
                self.calibration_panel._set_reset_shortcut(key, display_name)
            
            # Save to preferences immediately
            self.preferences_changed.emit()
            print(f"[Preferences] Shortcut saved to preferences and activated")
        else:
            # Dialog was cancelled - restore the previous shortcut monitoring
            if self.reset_shortcut and self.reset_shortcut != 'None':
                if self.input_command_queue:
                    try:
                        # Get the display name from the button text or stored value
                        display_name = self.reset_shortcut_display_name if self.reset_shortcut_display_name != 'None' else self.reset_shortcut
                        self.input_command_queue.put(('set_shortcut', self.reset_shortcut, display_name), timeout=0.1)
                        print(f"[Preferences] Restored shortcut monitoring: {self.reset_shortcut}")
                    except Exception as e:
                        print(f"[Preferences] Error restoring shortcut: {e}")
    
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
                    # Check if calibration panel is initializing to prevent duplicate messages
                    if not getattr(self.calibration_panel, '_initializing', False):
                        QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut(shortcut, display_name))
            except Exception:
                pass
        else:
            self.reset_shortcut = "None"
            self.shortcut_button.setText("Set Shortcut...")
            
            # Ensure calibration panel also has no shortcut
            if self.calibration_panel:
                from PyQt5.QtCore import QTimer
                # Check if calibration panel is initializing to prevent duplicate messages
                if not getattr(self.calibration_panel, '_initializing', False):
                    QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut("None", "None"))
        
        # Load and apply other calibration preferences to fusion worker
        # This ensures saved settings are applied at startup, not just when changed in GUI
        if hasattr(self.calibration_panel, 'control_queue') and self.calibration_panel.control_queue:
            try:
                # Apply drift curve setting to fusion worker
                drift_curve = prefs.get('drift_transition_curve', DRIFT_TRANSITION_CURVE)
                safe_queue_put(self.calibration_panel.control_queue, 
                             ('set_drift_curve_type', drift_curve), timeout=QUEUE_PUT_TIMEOUT)
                print(f"[Preferences] Applied startup drift curve: {drift_curve}")
                
                # Apply alpha values to fusion worker
                if 'alpha_pitch' in prefs:
                    alpha_pitch = float(prefs['alpha_pitch'])
                    safe_queue_put(self.calibration_panel.control_queue, 
                                 ('set_alpha_pitch', alpha_pitch), timeout=QUEUE_PUT_TIMEOUT)
                    print(f"[Preferences] Applied startup alpha pitch: {alpha_pitch}")
                
                if 'alpha_roll' in prefs:
                    alpha_roll = float(prefs['alpha_roll'])
                    safe_queue_put(self.calibration_panel.control_queue, 
                                 ('set_alpha_roll', alpha_roll), timeout=QUEUE_PUT_TIMEOUT)
                    print(f"[Preferences] Applied startup alpha roll: {alpha_roll}")
                    
            except Exception as e:
                print(f"[Preferences] Error applying startup settings to fusion worker: {e}")
    
    def _load_alpha_settings(self, cal_prefs):
        """Load alpha filter settings."""
        if 'alpha_pitch' in cal_prefs:
            self.alpha_pitch = float(cal_prefs['alpha_pitch'])
            self.alpha_pitch_slider.setValue(int(self.alpha_pitch * 1000))
            self.alpha_pitch_value.setText(f"{self.alpha_pitch:.3f}")
        
        if 'alpha_roll' in cal_prefs:
            self.alpha_roll = float(cal_prefs['alpha_roll'])
            self.alpha_roll_slider.setValue(int(self.alpha_roll * 1000))
            self.alpha_roll_value.setText(f"{self.alpha_roll:.3f}")
    
    def _load_stationary_settings(self, cal_prefs):
        """Load stationary detection settings."""
        if 'stationary_gyro_threshold' in cal_prefs:
            self.stationary_gyro_threshold = float(cal_prefs['stationary_gyro_threshold'])
            self.stationary_gyro_slider.setValue(int(self.stationary_gyro_threshold * 10))
            self.stationary_gyro_value.setText(f"{self.stationary_gyro_threshold:.1f} °/s")
        
        if 'stationary_debounce_s' in cal_prefs:
            self.stationary_debounce_s = float(cal_prefs['stationary_debounce_s'])
            self.stationary_debounce_slider.setValue(int(self.stationary_debounce_s * 100))
            self.stationary_debounce_value.setText(f"{self.stationary_debounce_s:.2f} s")
    
    def _load_drift_settings(self, cal_prefs):
        """Load drift correction settings."""
        if 'drift_smoothing_time' in cal_prefs:
            self.drift_smoothing_time = float(cal_prefs['drift_smoothing_time'])
            self.drift_smoothing_slider.setValue(int(self.drift_smoothing_time * 10))
            self.drift_smoothing_value.setText(f"{self.drift_smoothing_time:.1f} s")
        
        if 'drift_transition_curve' in cal_prefs:
            self.drift_transition_curve = cal_prefs['drift_transition_curve']
            index = self.drift_curve_combo.findText(self.drift_transition_curve)
            if index >= 0:
                self.drift_curve_combo.setCurrentIndex(index)
    
    def _load_gyro_settings(self, cal_prefs):
        """Load gyro calibration settings."""
        if 'gyro_bias_cal_samples' in cal_prefs:
            self.gyro_bias_cal_samples = int(cal_prefs['gyro_bias_cal_samples'])
            self.gyro_samples_slider.setValue(self.gyro_bias_cal_samples)
            self.gyro_samples_value.setText(str(self.gyro_bias_cal_samples))
    
    def _load_shortcut_settings(self, cal_prefs):
        """Load keyboard shortcut settings."""
        shortcut = cal_prefs.get('reset_shortcut', 'None')
        if shortcut and shortcut != 'None':
            try:
                # Try to get saved display name first
                display_name = cal_prefs.get('reset_shortcut_display_name', shortcut)
                
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
                self.reset_shortcut_display_name = display_name
                self.shortcut_button.setText(f"Shortcut: {display_name}")
                
                # Apply to calibration panel to register the hotkey
                if self.calibration_panel:
                    from PyQt5.QtCore import QTimer
                    # Check if calibration panel is initializing to prevent duplicate messages
                    if not getattr(self.calibration_panel, '_initializing', False):
                        QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut(shortcut, display_name))
            except Exception:
                pass
        else:
            self.reset_shortcut = "None"
            self.reset_shortcut_display_name = "None"
            self.shortcut_button.setText("Set Shortcut...")
            
            # Ensure calibration panel also has no shortcut
            if self.calibration_panel:
                from PyQt5.QtCore import QTimer
                # Check if calibration panel is initializing to prevent duplicate messages
                if not getattr(self.calibration_panel, '_initializing', False):
                    QTimer.singleShot(0, lambda: self.calibration_panel._set_reset_shortcut("None", "None"))
    
    def _apply_settings_to_fusion_worker(self, cal_prefs):
        """Send all calibration settings to fusion worker at startup."""
        if not (hasattr(self.calibration_panel, 'control_queue') and self.calibration_panel.control_queue):
            return
        
        # Prevent duplicate application during startup
        if getattr(self, '_settings_applied', False):
            return
        self._settings_applied = True
        
        try:
            # Apply drift curve setting to fusion worker
            drift_curve = cal_prefs.get('drift_transition_curve', DRIFT_TRANSITION_CURVE)
            safe_queue_put(self.calibration_panel.control_queue, 
                         ('set_drift_curve_type', drift_curve), timeout=QUEUE_PUT_TIMEOUT)
            print(f"[Preferences] Applied startup drift curve: {drift_curve}")
            
            # Apply alpha values to fusion worker
            if 'alpha_pitch' in cal_prefs:
                alpha_pitch = float(cal_prefs['alpha_pitch'])
                safe_queue_put(self.calibration_panel.control_queue, 
                             ('set_alpha_pitch', alpha_pitch), timeout=QUEUE_PUT_TIMEOUT)
                print(f"[Preferences] Applied startup alpha pitch: {alpha_pitch}")
            
            if 'alpha_roll' in cal_prefs:
                alpha_roll = float(cal_prefs['alpha_roll'])
                safe_queue_put(self.calibration_panel.control_queue, 
                             ('set_alpha_roll', alpha_roll), timeout=QUEUE_PUT_TIMEOUT)
                print(f"[Preferences] Applied startup alpha roll: {alpha_roll}")
                
        except Exception as e:
            print(f"[Preferences] Error applying startup settings to fusion worker: {e}")
    
    def get_shortcut_preferences(self):
        """Get shortcut preferences for saving."""
        return {
            'reset_shortcut': self.reset_shortcut,
            'reset_shortcut_display_name': self.reset_shortcut_display_name,
            'alpha_pitch': f"{self.alpha_pitch:.3f}",
            'alpha_roll': f"{self.alpha_roll:.3f}",
            'stationary_gyro_threshold': f"{self.stationary_gyro_threshold:.1f}",
            'stationary_debounce_s': f"{self.stationary_debounce_s:.3f}",
            'drift_smoothing_time': f"{self.drift_smoothing_time:.1f}",
            'drift_transition_curve': self.drift_transition_curve,
            'gyro_bias_cal_samples': str(self.gyro_bias_cal_samples)
        }
    

    
    def connect_calibration_panel(self, calibration_panel):
        """Connect to calibration panel for shortcut updates."""
        self.calibration_panel = calibration_panel
    
    def get_panel_name(self) -> str:
        """Return panel display name."""
        return "Preferences"