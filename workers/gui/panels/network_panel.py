"""
Network Panel for Acceltrack GUI.

Provides UDP network configuration controls:
- IP address entry
- Port number entry
- Enable/Disable UDP transmission
"""
import tkinter as tk
from tkinter import ttk

from config.config import (
    DEFAULT_UDP_IP,
    DEFAULT_UDP_PORT,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put


class NetworkPanel(ttk.LabelFrame):
    """Panel for UDP network settings and control."""
    
    def __init__(self, parent, udp_control_queue, message_callback, padding=6):
        """
        Initialize the Network Panel.
        
        Args:
            parent: Parent tkinter widget
            udp_control_queue: Queue for sending commands to UDP worker
            message_callback: Callable to display messages (e.g., app.append_message)
            padding: Padding for the frame (default: 6)
        """
        super().__init__(parent, text="Network Settings", padding=padding)
        
        self.udp_control_queue = udp_control_queue
        self.message_callback = message_callback
        
        # Network configuration variables
        self.udp_ip_var = tk.StringVar(value=DEFAULT_UDP_IP)
        self.udp_port_var = tk.StringVar(value=str(DEFAULT_UDP_PORT))
        
        # UDP state
        self.udp_enabled = False
        self.udp_btn_text = tk.StringVar(value="Start UDP")
        self.udp_status_var = tk.StringVar(value="UDP Disabled")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the network panel UI."""
        # Main container frame
        net_frm = ttk.Frame(self)
        net_frm.pack(fill="x", expand=True)
        
        # IP Address entry
        ttk.Label(net_frm, text="IP:").pack(side="left", padx=(6, 4))
        self.udp_ip_entry = ttk.Entry(
            net_frm,
            textvariable=self.udp_ip_var,
            width=14
        )
        self.udp_ip_entry.pack(side="left", padx=(0, 8))
        
        # Port entry
        ttk.Label(net_frm, text="Port:").pack(side="left", padx=(6, 4))
        self.udp_port_entry = ttk.Entry(
            net_frm,
            textvariable=self.udp_port_var,
            width=7
        )
        self.udp_port_entry.pack(side="left", padx=(0, 8))
        
        # Start/Stop UDP button
        self.udp_toggle_btn = ttk.Button(
            net_frm,
            textvariable=self.udp_btn_text,
            command=self.toggle_udp
        )
        self.udp_toggle_btn.pack(side="left", padx=(6, 6))
        
        # Status indicator (below controls)
        status_frm = ttk.Frame(self)
        status_frm.pack(fill="x", expand=True, pady=(6, 0))
        
        self.udp_status_label = ttk.Label(
            status_frm,
            textvariable=self.udp_status_var,
            foreground="blue"
        )
        self.udp_status_label.pack(side="left", padx=(6, 6))
    
    def toggle_udp(self):
        """Toggle UDP sending on/off."""
        self.udp_enabled = not self.udp_enabled
        
        if self.udp_enabled:
            self._enable_udp()
        else:
            self._disable_udp()
    
    def _enable_udp(self):
        """Enable UDP transmission."""
        # Update button text
        self.udp_btn_text.set("Stop UDP")
        
        # Get current IP and port
        try:
            ip = str(self.udp_ip_var.get())
            port = int(self.udp_port_var.get())
        except ValueError:
            if self.message_callback:
                self.message_callback("Invalid port number")
            return
        
        # Send set_udp command with IP and port
        if not safe_queue_put(
            self.udp_control_queue,
            ('set_udp', ip, port),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            if self.message_callback:
                self.message_callback("Failed to send UDP configuration")
            return
        
        # Send enable command
        if not safe_queue_put(
            self.udp_control_queue,
            ('udp_enable', True),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            if self.message_callback:
                self.message_callback("Failed to enable UDP")
            return
        
        # Update status
        self.udp_status_var.set(f"UDP Enabled -> {ip}:{port}")
        
        if self.message_callback:
            self.message_callback(f"UDP enabled -> {ip}:{port}")
    
    def _disable_udp(self):
        """Disable UDP transmission."""
        # Update button text
        self.udp_btn_text.set("Start UDP")
        
        # Send disable command
        if not safe_queue_put(
            self.udp_control_queue,
            ('udp_enable', False),
            timeout=QUEUE_PUT_TIMEOUT
        ):
            if self.message_callback:
                self.message_callback("Failed to disable UDP")
            return
        
        # Update status
        self.udp_status_var.set("UDP Disabled")
        
        if self.message_callback:
            self.message_callback("UDP disabled")
    
    def set_udp_config(self, ip, port):
        """
        Set UDP configuration programmatically.
        
        Args:
            ip: IP address string
            port: Port number (int or string)
        """
        try:
            self.udp_ip_var.set(str(ip))
            self.udp_port_var.set(str(port))
            
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
        Get current UDP configuration.
        
        Returns:
            tuple: (ip, port) where ip is string and port is int
        """
        try:
            ip = str(self.udp_ip_var.get())
            port = int(self.udp_port_var.get())
            return (ip, port)
        except ValueError:
            return (DEFAULT_UDP_IP, DEFAULT_UDP_PORT)
    
    def is_udp_enabled(self):
        """
        Check if UDP is currently enabled.
        
        Returns:
            bool: True if UDP is enabled
        """
        return self.udp_enabled
    
    def enable_udp(self):
        """Enable UDP if currently disabled."""
        if not self.udp_enabled:
            self.toggle_udp()
    
    def disable_udp(self):
        """Disable UDP if currently enabled."""
        if self.udp_enabled:
            self.toggle_udp()
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with 'udp_ip' and 'udp_port' keys
        """
        return {
            'udp_ip': self.udp_ip_var.get(),
            'udp_port': self.udp_port_var.get()
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional 'udp_ip' and 'udp_port' keys
        """
        if prefs is None:
            return
        
        if 'udp_ip' in prefs and prefs['udp_ip']:
            self.udp_ip_var.set(prefs['udp_ip'])
        
        if 'udp_port' in prefs and prefs['udp_port']:
            self.udp_port_var.set(prefs['udp_port'])
        
        # Send initial configuration to UDP worker if enabled
        if self.udp_enabled and self.udp_control_queue:
            try:
                ip = str(self.udp_ip_var.get())
                port = int(self.udp_port_var.get())
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
