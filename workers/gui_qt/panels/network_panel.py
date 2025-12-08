"""
PyQt Network Panel for frankentrack GUI.

PyQt version of NetworkPanel with identical functionality to tkinter version.
Provides UDP network configuration controls:
- IP address entry
- Port number entry
- Enable/Disable UDP transmission
"""

from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QFrame, QGridLayout)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QValidator, QIntValidator

from .base_panel import BasePanelQt
from config.config import (
    DEFAULT_UDP_IP,
    DEFAULT_UDP_PORT,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put


class NetworkPanelQt(BasePanelQt):
    """PyQt version of NetworkPanel for UDP network settings and control."""
    
    def __init__(self, parent, udp_control_queue, message_callback, padding=6):
        """
        Initialize the PyQt Network Panel.
        
        Args:
            parent: Parent PyQt widget
            udp_control_queue: Queue for sending commands to UDP worker
            message_callback: Callable to display messages
            padding: Padding for the frame (default: 6)
        """
        self.udp_control_queue = udp_control_queue
        self.padding = padding
        
        # Network configuration values (same as tkinter version)
        self._udp_ip = DEFAULT_UDP_IP
        self._udp_port = str(DEFAULT_UDP_PORT)
        
        # UDP state (same as tkinter version)
        self.udp_enabled = False
        self._udp_btn_text = "Start UDP"
        self._udp_status_text = "UDP Disabled"
        
        super().__init__(parent, "Network Settings", message_callback=message_callback)
    
    def setup_ui(self):
        """Build the network panel UI (mirrors tkinter layout exactly)."""
        # Main layout with minimal padding
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 1, 4, 1)  # Match calibration panel horizontal padding
        main_layout.setSpacing(2)  # Minimal spacing
        
        # Network controls frame (same as tkinter net_frm)
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(6, 0, 6, 0)  # Match calibration frame horizontal padding
        controls_layout.setSpacing(4)  # Slightly reduced spacing
        
        # IP Address entry (same as tkinter)
        ip_label = QLabel("IP:")
        controls_layout.addWidget(ip_label)
        
        self.udp_ip_entry = QLineEdit()
        self.udp_ip_entry.setText(self._udp_ip)
        self.udp_ip_entry.setMaximumWidth(100)  # Reduced from 110
        self.udp_ip_entry.textChanged.connect(self._on_ip_changed)
        controls_layout.addWidget(self.udp_ip_entry)
        
        # Port entry (same as tkinter)
        port_label = QLabel("Port:")
        controls_layout.addWidget(port_label)
        
        self.udp_port_entry = QLineEdit()
        self.udp_port_entry.setText(self._udp_port)
        self.udp_port_entry.setMaximumWidth(55)  # Reduced from 60
        self.udp_port_entry.setValidator(QIntValidator(1, 65535))  # Valid port range
        self.udp_port_entry.textChanged.connect(self._on_port_changed)
        controls_layout.addWidget(self.udp_port_entry)
        
        # Add stretch to push status and button to the right
        controls_layout.addStretch()
        
        # Status indicator (right-aligned before button)
        self.udp_status_label = QLabel(self._udp_status_text)
        self.udp_status_label.setObjectName("statusLabel")
        self.udp_status_label.setProperty("status", "disabled")
        controls_layout.addWidget(self.udp_status_label)
        
        # Start/Stop UDP button (rightmost)
        self.udp_toggle_btn = QPushButton(self._udp_btn_text)
        self.udp_toggle_btn.setMaximumWidth(80)
        self.udp_toggle_btn.clicked.connect(self.toggle_udp)
        controls_layout.addWidget(self.udp_toggle_btn)
        
        main_layout.addWidget(controls_frame)
    
    def _on_ip_changed(self, text):
        """Handle IP address entry change."""
        self._udp_ip = text
    
    def _on_port_changed(self, text):
        """Handle port entry change."""
        self._udp_port = text
    
    def toggle_udp(self):
        """Toggle UDP sending on/off (identical to tkinter)."""
        self.udp_enabled = not self.udp_enabled
        
        if self.udp_enabled:
            self._enable_udp()
        else:
            self._disable_udp()
    
    def _enable_udp(self):
        """Enable UDP transmission (identical logic to tkinter)."""
        # Update button text
        self._udp_btn_text = "Stop UDP"
        self.udp_toggle_btn.setText(self._udp_btn_text)
        
        # Get current IP and port
        try:
            ip = str(self.udp_ip_entry.text())
            port = int(self.udp_port_entry.text())
        except ValueError:
            self.log_message("Invalid port number")
            return
        
        # Send set_udp command with IP and port (identical to tkinter)
        if not safe_queue_put(
            self.udp_control_queue,
            ('set_udp', ip, port),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.log_message("Failed to send UDP configuration")
            return
        
        # Send enable command (identical to tkinter)
        if not safe_queue_put(
            self.udp_control_queue,
            ('udp_enable', True),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.log_message("Failed to enable UDP")
            return
        
        # Update status (same as tkinter)
        self._udp_status_text = f"UDP Enabled -> {ip}:{port}"
        self.udp_status_label.setText(self._udp_status_text)
        self.udp_status_label.setProperty("status", "enabled")
        self.udp_status_label.style().polish(self.udp_status_label)  # Force style refresh
        
        self.log_message(f"UDP enabled -> {ip}:{port}")
    
    def _disable_udp(self):
        """Disable UDP transmission (identical logic to tkinter)."""
        # Update button text
        self._udp_btn_text = "Start UDP"
        self.udp_toggle_btn.setText(self._udp_btn_text)
        
        # Send disable command (identical to tkinter)
        if not safe_queue_put(
            self.udp_control_queue,
            ('udp_enable', False),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.log_message("Failed to disable UDP")
            return
        
        # Update status (same as tkinter)
        self._udp_status_text = "UDP Disabled"
        self.udp_status_label.setText(self._udp_status_text)
        self.udp_status_label.setProperty("status", "disabled")
        self.udp_status_label.style().polish(self.udp_status_label)  # Force style refresh
        
        self.log_message("UDP disabled")
    
    def set_udp_config(self, ip, port):
        """
        Set UDP configuration programmatically (identical to tkinter).
        
        Args:
            ip: IP address string
            port: Port number (int or string)
        """
        try:
            self._udp_ip = str(ip)
            self._udp_port = str(port)
            self.udp_ip_entry.setText(self._udp_ip)
            self.udp_port_entry.setText(self._udp_port)
            
            # If UDP is currently enabled, send new config
            if self.udp_enabled:
                safe_queue_put(
                    self.udp_control_queue,
                    ('set_udp', str(ip), int(port)),
                    timeout=QUEUE_PUT_TIMEOUT
                )
        except Exception:
            pass
    
    def get_udp_config(self):
        """
        Get current UDP configuration (identical to tkinter).
        
        Returns:
            tuple: (ip, port) where ip is string and port is int
        """
        try:
            ip = str(self.udp_ip_entry.text())
            port = int(self.udp_port_entry.text())
            return (ip, port)
        except ValueError:
            return (DEFAULT_UDP_IP, DEFAULT_UDP_PORT)
    
    def is_udp_enabled(self):
        """
        Check if UDP is currently enabled (identical to tkinter).
        
        Returns:
            bool: True if UDP is enabled
        """
        return self.udp_enabled
    
    def enable_udp(self):
        """Enable UDP if currently disabled (identical to tkinter)."""
        if not self.udp_enabled:
            self.toggle_udp()
    
    def disable_udp(self):
        """Disable UDP if currently enabled (identical to tkinter)."""
        if self.udp_enabled:
            self.toggle_udp()
    
    def get_prefs(self):
        """
        Get current preferences for persistence (identical to tkinter).
        
        Returns:
            dict: Dictionary with 'udp_ip' and 'udp_port' keys
        """
        return {
            'udp_ip': self.udp_ip_entry.text(),
            'udp_port': self.udp_port_entry.text()
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences (identical logic to tkinter).
        
        Args:
            prefs: Dictionary with optional 'udp_ip' and 'udp_port' keys
        """
        if prefs is None:
            return
        
        if 'udp_ip' in prefs and prefs['udp_ip']:
            self._udp_ip = prefs['udp_ip']
            self.udp_ip_entry.setText(self._udp_ip)
        
        if 'udp_port' in prefs and prefs['udp_port']:
            self._udp_port = prefs['udp_port']
            self.udp_port_entry.setText(self._udp_port)
        
        # Send initial configuration to UDP worker if enabled (identical to tkinter)
        if self.udp_enabled and self.udp_control_queue:
            try:
                ip = str(self.udp_ip_entry.text())
                port = int(self.udp_port_entry.text())
                safe_queue_put(
                    self.udp_control_queue,
                    ('set_udp', ip, port),
                    timeout=QUEUE_PUT_TIMEOUT
                )
                safe_queue_put(
                    self.udp_control_queue,
                    ('udp_enable', True),
                    timeout=QUEUE_PUT_TIMEOUT
                )
            except Exception:
                pass