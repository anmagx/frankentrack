"""
PyQt Serial Panel for frankentrack GUI.

PyQt version of SerialPanel with identical functionality to tkinter version.
Provides controls for serial port selection, baud rate configuration,
and start/stop functionality.
"""

from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QComboBox, QPushButton, 
                             QFrame, QGridLayout, QSizePolicy)
from PyQt5.QtCore import pyqtSignal, QTimer
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
        
        super().__init__(parent, "Serial Reader", message_callback=message_callback)
        
    def setup_ui(self):
        """Setup the serial panel UI (mirrors tkinter layout exactly)."""
        # Create main layout
        layout = QGridLayout(self)
        layout.setContentsMargins(self.padding, self.padding, self.padding, self.padding)
        layout.setSpacing(6)
        
        # Serial Port selection (same as tkinter)
        port_label = QLabel("Serial Port:")
        layout.addWidget(port_label, 0, 0)
        
        self.port_combo = QComboBox()
        ports = [f"COM{i}" for i in range(100)]  # Same as tkinter
        self.port_combo.addItems(ports)
        self.port_combo.setCurrentText(self._port_value)
        self.port_combo.setMaximumWidth(80)
        self.port_combo.currentTextChanged.connect(self._on_port_changed)
        layout.addWidget(self.port_combo, 0, 1)
        
        # Baud Rate selection (same as tkinter)  
        baud_label = QLabel("Baud Rate:")
        layout.addWidget(baud_label, 0, 2)
        
        self.baud_combo = QComboBox()
        baud_rates = ["9600", "19200", "38400", "57600", "115200", "230400", "250000"]
        self.baud_combo.addItems(baud_rates)
        self.baud_combo.setCurrentText(self._baud_value)
        self.baud_combo.setMaximumWidth(80)
        self.baud_combo.currentTextChanged.connect(self._on_baud_changed)
        layout.addWidget(self.baud_combo, 0, 3)
        
        # Start/Stop button (same as tkinter)
        self.toggle_button = QPushButton("Start")
        self.toggle_button.setMaximumWidth(80)
        self.toggle_button.clicked.connect(self.toggle)
        layout.addWidget(self.toggle_button, 0, 4)
        
        # Status label (same as tkinter)
        self.status_label = QLabel("Stopped")
        self.status_label.setStyleSheet("color: blue;")
        layout.addWidget(self.status_label, 0, 5)
        
        # Set column stretch to match tkinter layout
        layout.setColumnStretch(5, 1)  # Status label gets remaining space
    
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
        
        # Update UI state (same as tkinter)
        self._is_running = True
        self.toggle_button.setText("Stop")
        self.status_label.setText(f"Running on {port} @ {baud}")
        self.status_label.setStyleSheet("color: green;")
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
        self.toggle_button.setText("Start")
        self.status_label.setText("Stopped")
        self.status_label.setStyleSheet("color: blue;")
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