"""
Serial Reader Panel for Acceltrack GUI.

Provides controls for serial port selection, baud rate configuration,
and start/stop functionality.
"""
import tkinter as tk
from tkinter import ttk

from config.config import (
    DEFAULT_SERIAL_PORT,
    DEFAULT_SERIAL_BAUD,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put


class SerialPanel(ttk.LabelFrame):
    """Panel for serial port configuration and control."""
    
    def __init__(self, parent, serial_control_queue, message_callback, padding=8):
        """
        Initialize the Serial Panel.
        
        Args:
            parent: Parent tkinter widget
            serial_control_queue: Queue for sending commands to serial worker
            message_callback: Callable to display messages (e.g., app.append_message)
            padding: Padding for the frame (default: 8)
        """
        super().__init__(parent, text="Serial Reader", padding=padding)
        
        self.serial_control_queue = serial_control_queue
        self.message_callback = message_callback
        
        # State variables
        self.port_var = tk.StringVar(value=DEFAULT_SERIAL_PORT)
        self.baud_var = tk.StringVar(value=str(DEFAULT_SERIAL_BAUD))
        self.btn_text = tk.StringVar(value="Start")
        self.status_var = tk.StringVar(value="Stopped")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the serial panel UI."""
        # Main container frame
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)
        
        # Serial Port selection
        ttk.Label(frm, text="Serial Port:").grid(
            row=0, column=0, sticky="w", padx=(2, 6), pady=6
        )
        ports = [f"COM{i}" for i in range(100)]
        self.port_cb = ttk.Combobox(
            frm, 
            textvariable=self.port_var, 
            values=ports, 
            state="readonly", 
            width=8
        )
        self.port_cb.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=6)
        
        # Baud Rate selection
        ttk.Label(frm, text="Baud Rate:").grid(
            row=0, column=2, sticky="w", padx=(2, 6), pady=6
        )
        baud_rates = ["9600", "19200", "38400", "57600", "115200", "230400", "250000"]
        self.baud_cb = ttk.Combobox(
            frm, 
            textvariable=self.baud_var, 
            values=baud_rates, 
            state="readonly", 
            width=8
        )
        self.baud_cb.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=6)
        
        # Start/Stop button
        self.start_btn = ttk.Button(
            frm, 
            textvariable=self.btn_text, 
            command=self.toggle, 
            width=10
        )
        self.start_btn.grid(row=0, column=4, sticky="w", padx=(0, 12), pady=6)
        
        # Status label
        self.status_label = ttk.Label(
            frm, 
            textvariable=self.status_var, 
            foreground="blue"
        )
        self.status_label.grid(row=0, column=5, sticky="w", padx=(0, 6), pady=6)
    
    def toggle(self):
        """Toggle serial port start/stop."""
        if self.btn_text.get() == "Start":
            self._start_serial()
        else:
            self._stop_serial()
    
    def _start_serial(self):
        """Start serial communication."""
        port = self.port_var.get()
        baud = int(self.baud_var.get())
        
        # Send start command to serial worker
        if not safe_queue_put(
            self.serial_control_queue, 
            ('start', port, baud), 
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.message_callback("Failed to request serial start")
            return
        
        # Update UI state
        self.btn_text.set("Stop")
        self.status_var.set(f"Running on {port} @ {baud}")
        self.message_callback(f"Start requested on {port} @ {baud}")
    
    def _stop_serial(self):
        """Stop serial communication."""
        # Send stop command to serial worker
        if not safe_queue_put(
            self.serial_control_queue, 
            ('stop',), 
            timeout=QUEUE_PUT_TIMEOUT
        ):
            self.message_callback("Failed to request serial stop")
            return
        
        # Update UI state
        self.btn_text.set("Start")
        self.status_var.set("Stopped")
        self.message_callback("Stop requested")
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Dictionary with 'com_port' and 'baud_rate' keys
        """
        return {
            'com_port': self.port_var.get(),
            'baud_rate': self.baud_var.get()
        }
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with optional 'com_port' and 'baud_rate' keys
        """
        if prefs is None:
            return
        
        if 'com_port' in prefs and prefs['com_port']:
            self.port_var.set(prefs['com_port'])
        
        if 'baud_rate' in prefs and prefs['baud_rate']:
            self.baud_var.set(prefs['baud_rate'])
