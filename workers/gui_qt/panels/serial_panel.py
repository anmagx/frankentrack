"""
PyQt Serial Panel for frankentrack GUI.

PyQt version of SerialPanel with identical functionality to tkinter version.
Provides controls for serial port selection, baud rate configuration,
and start/stop functionality.
"""

from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton, 
                             QFrame, QGridLayout, QSizePolicy)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

from .base_panel import BasePanelQt
from config.config import (
    DEFAULT_SERIAL_PORT,
    DEFAULT_SERIAL_BAUD,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put


class SerialPanelQt(BasePanelQt):
    """PyQt version of SerialPanel."""
    
    def __init__(self, parent, serial_control_queue, message_callback, padding=8, on_stop=None):
        """
        Initialize the PyQt Serial Panel.
        
        Args:
            parent: Parent PyQt widget
            serial_control_queue: Queue for sending commands to serial worker
            message_callback: Callable to display messages
            padding: Padding for the frame (default: 8)
            on_stop: Optional callback invoked when serial is stopped
        """
        self.serial_control_queue = serial_control_queue
        self.on_stop = on_stop
        self.padding = padding
        
        # State tracking (same as tkinter version)
        self._port_value = DEFAULT_SERIAL_PORT
        self._baud_value = str(DEFAULT_SERIAL_BAUD)
        self._is_running = False
        self._connection_status = "stopped"  # stopped, starting, connected, error
        self._fusion_processing = False  # Track if fusion worker is actively processing
        
        # Timer for data activity timeout
        self._data_activity_timer = QTimer()
        self._data_activity_timer.timeout.connect(self._on_data_timeout)
        self._data_activity_timer.setSingleShot(True)
        self._last_data_time = 0
        
        super().__init__(parent, "Serial Reader", message_callback=message_callback)
        
    def setup_ui(self):
        """Setup the serial panel UI (mirrors tkinter layout exactly)."""
        # Main layout with minimal padding
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 1, 4, 1)  # Match calibration panel horizontal padding
        main_layout.setSpacing(2)  # Minimal spacing
        
        # Serial controls frame (same pattern as network panel)
        controls_frame = QFrame()
        layout = QGridLayout(controls_frame)
        layout.setContentsMargins(6, 0, 6, 0)  # Match calibration frame horizontal padding
        layout.setSpacing(2)  # Minimal spacing
        
        # Serial Port selection (same as tkinter)
        port_label = QLabel("Port:")
        layout.addWidget(port_label, 0, 0)
        
        self.port_combo = QComboBox()
        ports = [f"COM{i}" for i in range(100)]  # Same as tkinter
        self.port_combo.addItems(ports)
        self.port_combo.setCurrentText(self._port_value)
        self.port_combo.setMaximumWidth(100)  # Reduced from 80
        self.port_combo.currentTextChanged.connect(self._on_port_changed)
        layout.addWidget(self.port_combo, 0, 1)
        
        # Baud Rate selection (same as tkinter)  
        baud_label = QLabel("Baud:")
        layout.addWidget(baud_label, 0, 2)
        
        self.baud_combo = QComboBox()
        baud_rates = ["9600", "19200", "38400", "57600", "115200", "230400", "250000", "500000", "1000000"]
        self.baud_combo.addItems(baud_rates)
        self.baud_combo.setCurrentText(self._baud_value)
        self.baud_combo.setMaximumWidth(90)  # Increased to accommodate all baud rates
        self.baud_combo.currentTextChanged.connect(self._on_baud_changed)
        layout.addWidget(self.baud_combo, 0, 3)
        
        # Add stretch to push status and button to the right
        layout.setColumnStretch(4, 1)
        
        # Status label (right-aligned before button)
        self.status_label = QLabel("Stopped")
        self.status_label.setProperty("status", "disabled")
        layout.addWidget(self.status_label, 0, 5)
        
        # Start/Stop button (rightmost)
        self.toggle_button = QPushButton("Start")
        self.toggle_button.setMaximumWidth(60)  # Reduced from 80
        self.toggle_button.clicked.connect(self.toggle)
        layout.addWidget(self.toggle_button, 0, 6)
        
        main_layout.addWidget(controls_frame)
    
    def _on_port_changed(self, port):
        """Handle port selection change."""
        self._port_value = port
    
    def _on_baud_changed(self, baud):
        """Handle baud rate selection change.""" 
        self._baud_value = baud
        
    def toggle(self):
        """Toggle serial port start/stop (same logic as tkinter)."""
        if not self._is_running:
            self._start_serial()
        else:
            self._stop_serial()
    
    def _start_serial(self):
        """Start serial communication (same logic as tkinter)."""
        port = self.port_combo.currentText()
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            baud = DEFAULT_SERIAL_BAUD
        
        # Send start command to serial worker (identical to tkinter)
        if not safe_queue_put(
            self.serial_control_queue, 
            ('start', port, baud), 
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.log_message("Failed to request serial start")
            return
        
        # Update UI state - show starting status
        self._is_running = True
        self._connection_status = "starting"
        self.toggle_button.setText("Stop")
        
        # Disable port and baud selection while connection is active
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        
        self.status_label.setText(f"Starting {port} @ {baud}...")
        self.status_label.setProperty("status", "warning")
        self.status_label.style().polish(self.status_label)
        self.log_message(f"Start requested on {port} @ {baud}")
    
    def _stop_serial(self):
        """Stop serial communication (same logic as tkinter)."""
        # Send stop command to serial worker (identical to tkinter)
        if not safe_queue_put(
            self.serial_control_queue, 
            ('stop',), 
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.log_message("Failed to request serial stop")
            return
        
        # Update UI state (same as tkinter)
        self._is_running = False
        self._connection_status = "stopped"
        self.toggle_button.setText("Start")
        
        # Re-enable port and baud selection when stopped
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        
        self.status_label.setText("Stopped")
        self.status_label.setProperty("status", "disabled")
        self.status_label.style().polish(self.status_label)
        self._data_activity_timer.stop()
        self.log_message("Stop requested")
        
        # Perform optional global stop actions (identical to tkinter)
        try:
            if callable(self.on_stop):
                self.on_stop()
        except Exception:
            try:
                self.log_message("on_stop handler raised an exception")
            except Exception:
                pass
    
    def get_prefs(self):
        """
        Get current preferences for persistence (identical to tkinter).
        
        Returns:
            dict: Dictionary with 'com_port' and 'baud_rate' keys
        """
        return {
            'com_port': self.port_combo.currentText(),
            'baud_rate': self.baud_combo.currentText()
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences (identical logic to tkinter).
        
        Args:
            prefs: Dictionary with optional 'com_port' and 'baud_rate' keys
        """
        if prefs is None:
            return
        
        if 'com_port' in prefs and prefs['com_port']:
            port = prefs['com_port']
            # Ensure the port is in the combo box
            if self.port_combo.findText(port) == -1:
                self.port_combo.addItem(port)
            self.port_combo.setCurrentText(port)
            self._port_value = port
        
        if 'baud_rate' in prefs and prefs['baud_rate']:
            baud = prefs['baud_rate']
            self.baud_combo.setCurrentText(str(baud))
            self._baud_value = str(baud)
    
    def update_connection_status(self, status: str):
        """Update connection status from serial worker."""
        if not self._is_running:
            return
            
        self._connection_status = status
        port = self.port_combo.currentText()
        baud = self.baud_combo.currentText()
        
        if status == "connected":
            self.status_label.setText(f"Waiting for data...")
            self.status_label.setProperty("status", "warning")  # Orange until fusion is active
            self.status_label.style().polish(self.status_label)
        elif status == "error":
            # Re-enable port and baud selection on error so user can try different settings
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
            
            self.status_label.setText(f"Error on {port} @ {baud}")
            self.status_label.setProperty("status", "error")
            self.status_label.style().polish(self.status_label)
            self._data_activity_timer.stop()
    
    def update_data_activity(self):
        """Called when data is received - indicates active connection."""
        if not self._is_running or self._connection_status != "connected":
            return
            
        import time
        self._last_data_time = time.time()
        
        # Only show green when both connected AND fusion is processing
        if self._fusion_processing:
            port = self.port_combo.currentText()
            baud = self.baud_combo.currentText()
            self.status_label.setText(f"Running on {port} @ {baud}")
            self.status_label.setProperty("status", "enabled")
            self.status_label.style().polish(self.status_label)
        
        # Reset timeout timer (5 seconds without data = back to waiting)
        self._data_activity_timer.start(5000)
    
    def _on_data_timeout(self):
        """Called when no data received for timeout period."""
        if not self._is_running or self._connection_status != "connected":
            return
            
        # Back to waiting when no recent data
        self.status_label.setText(f"Waiting for data...")
        self.status_label.setProperty("status", "warning")
        self.status_label.style().polish(self.status_label)
    
    def update_fusion_status(self, is_active):
        """Update fusion processing status from statusQueue."""
        self._fusion_processing = is_active
        
        # Update display immediately when fusion status changes
        if self._is_running and self._connection_status == "connected":
            if is_active:
                # Fusion is now processing - show "Running" status
                port = self.port_combo.currentText()
                baud = self.baud_combo.currentText()
                self.status_label.setText(f"Running on {port} @ {baud}")
                self.status_label.setProperty("status", "enabled")
            else:
                # Fusion stopped processing
                self.status_label.setText(f"Waiting for data...")
                self.status_label.setProperty("status", "warning")
            self.status_label.style().polish(self.status_label)