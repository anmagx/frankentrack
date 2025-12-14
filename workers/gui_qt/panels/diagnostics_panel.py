"""
PyQt5 Diagnostics Panel for frankentrack GUI.

Real-time plotting panel for Yaw, Pitch, and Roll angles with enable/disable toggle.
"""
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QCheckBox, 
                             QLabel, QWidget, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer
import collections
import time

# Lazy import matplotlib - only load when actually needed
_matplotlib_loaded = False
_MATPLOTLIB_AVAILABLE = None

def _check_matplotlib():
    """Check if matplotlib is available (lazy load)."""
    global _matplotlib_loaded, _MATPLOTLIB_AVAILABLE
    if not _matplotlib_loaded:
        _matplotlib_loaded = True
        try:
            import matplotlib.pyplot as plt
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            _MATPLOTLIB_AVAILABLE = True
        except ImportError:
            _MATPLOTLIB_AVAILABLE = False
    return _MATPLOTLIB_AVAILABLE


class DiagnosticsPanelQt(QGroupBox):
    """PyQt5 Panel for real-time diagnostics plotting of orientation data."""
    
    def __init__(self, parent=None, control_queue=None, message_callback=None, padding=6):
        """
        Initialize the Diagnostics Panel.
        
        Args:
            parent: Parent PyQt5 widget
            control_queue: Not used (display-only panel)
            message_callback: Callback for logging messages 
            padding: Padding for the frame (default: 6)
        """
        super().__init__("Diagnostics", parent)
        
        self.message_callback = message_callback
        
        # Data storage
        self.max_data_points = 1000  # Keep last 1000 data points
        self.data_yaw = collections.deque(maxlen=self.max_data_points)
        self.data_pitch = collections.deque(maxlen=self.max_data_points)
        self.data_roll = collections.deque(maxlen=self.max_data_points)
        self.data_times = collections.deque(maxlen=self.max_data_points)
        
        # UI components
        self.enable_checkbox = None
        self.canvas = None
        self.figure = None
        self.ax_yaw = None
        self.ax_pitch = None 
        self.ax_roll = None
        self.lines = {'yaw': None, 'pitch': None, 'roll': None}
        
        # Update timer for plot refreshing
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self._update_plots)
        self.plot_timer.setInterval(100)  # Update plots every 100ms
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the diagnostics panel UI."""
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(4, 2, 4, 2)
        self.setLayout(main_layout)

        # Enable checkbox
        self._build_enable_control(main_layout)
        
        # Plotting area
        self._build_plot_area(main_layout)
    
    def _build_enable_control(self, parent_layout):
        """Build the enable diagnostics checkbox."""
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(6, 0, 6, 0)
        
        self.enable_checkbox = QCheckBox("Enable Diagnose Mode")
        self.enable_checkbox.setChecked(False)
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        control_layout.addWidget(self.enable_checkbox)
        
        control_layout.addStretch()  # Push checkbox to left
        
        parent_layout.addLayout(control_layout)
    
    def _build_plot_area(self, parent_layout):
        """Build the plotting area with three subplots."""
        if not _check_matplotlib():
            # Show error message if matplotlib not available
            error_label = QLabel("Matplotlib not available. Install with: pip install matplotlib")
            error_label.setStyleSheet("color: red; font-weight: bold;")
            error_label.setAlignment(Qt.AlignCenter)
            parent_layout.addWidget(error_label)
            return
        
        # Import matplotlib components now that we need them
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        
        # Create matplotlib figure with responsive layout handling
        self.figure = Figure(figsize=(4, 2))  # Reduced from (8, 6) for narrower window
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumSize(300, 200)  # Set reasonable minimum size
        
        # Create three subplots (stacked vertically) with better spacing
        self.ax_yaw = self.figure.add_subplot(3, 1, 1)
        self.ax_pitch = self.figure.add_subplot(3, 1, 2)
        self.ax_roll = self.figure.add_subplot(3, 1, 3)
        
        # Adjust subplot spacing
        self.figure.subplots_adjust(hspace=0.4, left=0.15, right=0.95, top=0.95, bottom=0.15)
        
        # Configure subplots
        self._setup_subplot(self.ax_yaw, "Yaw (°)", "blue")
        self._setup_subplot(self.ax_pitch, "Pitch (°)", "green") 
        self._setup_subplot(self.ax_roll, "Roll (°)", "red")
        
        # Initialize empty line plots
        self.lines['yaw'], = self.ax_yaw.plot([], [], 'b-', linewidth=1.5)
        self.lines['pitch'], = self.ax_pitch.plot([], [], 'g-', linewidth=1.5)
        self.lines['roll'], = self.ax_roll.plot([], [], 'r-', linewidth=1.5)
        
        parent_layout.addWidget(self.canvas)
        
        # Initially hide the plots
        self.canvas.setVisible(False)
    
    def _setup_subplot(self, ax, ylabel, color):
        """Setup individual subplot configuration."""
        ax.set_ylabel(ylabel, color=color)
        ax.tick_params(axis='y', labelcolor=color)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-180, 180)  # Set fixed range for angles
        
        # Set up time axis with proper limits to avoid too many ticks
        ax.set_xlabel("Time")
        ax.tick_params(axis='x', rotation=45)  # Rotate time labels
    
    def _on_enable_changed(self, state):
        """Handle enable checkbox state change."""
        enabled = (state == Qt.Checked)
        
        if enabled:
            self._start_diagnostics()
        else:
            self._stop_diagnostics()
        
        if self.message_callback:
            status = "enabled" if enabled else "disabled"
            self.message_callback(f"Diagnostics mode {status}")
    
    def _start_diagnostics(self):
        """Start diagnostics mode - show plots and start updating."""
        if _MATPLOTLIB_AVAILABLE and self.canvas:
            self.canvas.setVisible(True)
            self.plot_timer.start()
            self._clear_data()  # Clear old data when starting
    
    def _stop_diagnostics(self):
        """Stop diagnostics mode - hide plots and stop updating.""" 
        if _MATPLOTLIB_AVAILABLE and self.canvas:
            self.plot_timer.stop()
            self.canvas.setVisible(False)
    
    def _clear_data(self):
        """Clear all stored data."""
        self.data_yaw.clear()
        self.data_pitch.clear()
        self.data_roll.clear()
        self.data_times.clear()
    
    def _update_plots(self):
        """Update the matplotlib plots with current data."""
        if not _MATPLOTLIB_AVAILABLE or not self.canvas or not self.is_enabled():
            return
        
        if len(self.data_times) < 2:
            return  # Need at least 2 points to plot
        
        # Use simple sequential indices for time axis
        times_list = list(self.data_times)
        yaw_list = list(self.data_yaw)
        pitch_list = list(self.data_pitch)
        roll_list = list(self.data_roll)
        
        # Update line data
        self.lines['yaw'].set_data(times_list, yaw_list)
        self.lines['pitch'].set_data(times_list, pitch_list)
        self.lines['roll'].set_data(times_list, roll_list)
        
        # Adjust x-axis to show recent data
        if times_list:
            x_min = max(0, times_list[-1] - 600)  # Show last 600 data points
            x_max = times_list[-1]
            
            for ax in [self.ax_yaw, self.ax_pitch, self.ax_roll]:
                ax.set_xlim(x_min, x_max)
        
        # Refresh canvas
        try:
            self.canvas.draw_idle()
        except Exception:
            pass  # Ignore drawing errors during rapid updates
    
    def is_enabled(self):
        """Check if diagnostics mode is enabled."""
        return self.enable_checkbox and self.enable_checkbox.isChecked()
    
    def update_euler(self, yaw, pitch, roll):
        """
        Update orientation data and plots (if enabled).
        
        Args:
            yaw: Yaw angle in degrees
            pitch: Pitch angle in degrees
            roll: Roll angle in degrees
        """
        if not self.is_enabled():
            return
        
        # Add new data point with sequential index instead of time
        # This avoids matplotlib date formatting issues
        current_index = len(self.data_times)
        
        self.data_times.append(current_index)
        self.data_yaw.append(float(yaw))
        self.data_pitch.append(float(pitch))
        self.data_roll.append(float(roll))
        
        # Note: Actual plot update happens in timer callback for performance
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with current preferences
        """
        return {
            'enabled': False,  # Always start disabled for performance
            'max_data_points': self.max_data_points
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with preference keys
        """
        if not prefs:
            return
        
        # Apply enabled state - default to False for performance
        if 'enabled' in prefs:
            try:
                enabled = bool(prefs['enabled'])
                # Ensure diagnostics start disabled for performance optimization
                self.enable_checkbox.setChecked(False)  # Always start disabled
            except Exception:
                self.enable_checkbox.setChecked(False)
        
        # Apply max data points
        if 'max_data_points' in prefs:
            try:
                max_points = int(prefs['max_data_points'])
                if max_points > 0:
                    self.max_data_points = max_points
                    # Recreate deques with new size
                    self._recreate_deques()
            except Exception:
                pass
    
    def _recreate_deques(self):
        """Recreate data deques with new max size."""
        old_times = list(self.data_times)
        old_yaw = list(self.data_yaw)
        old_pitch = list(self.data_pitch)
        old_roll = list(self.data_roll)
        
        self.data_times = collections.deque(old_times, maxlen=self.max_data_points)
        self.data_yaw = collections.deque(old_yaw, maxlen=self.max_data_points)
        self.data_pitch = collections.deque(old_pitch, maxlen=self.max_data_points)
        self.data_roll = collections.deque(old_roll, maxlen=self.max_data_points)