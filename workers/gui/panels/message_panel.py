"""
Message Panel for Acceltrack GUI.

Provides two text display areas:
1. Serial Monitor - Raw serial data from IMU
2. Messages - Application logs and status messages
"""
import tkinter as tk
from tkinter import ttk

from config.config import MAX_TEXT_BUFFER_LINES


class MessagePanel(ttk.Frame):
    """Panel for displaying serial monitor and application messages."""
    
    def __init__(self, parent, serial_height=8, message_height=8, 
                 max_serial_lines=200, max_message_lines=100, padding=6):
        """
        Initialize the Message Panel.
        
        Args:
            parent: Parent tkinter widget
            serial_height: Height of serial monitor text widget (default: 8)
            message_height: Height of messages text widget (default: 8)
            max_serial_lines: Maximum lines to keep in serial buffer (default: 200)
            max_message_lines: Maximum lines to keep in message buffer (default: 100)
            padding: Padding for frames (default: 6)
        """
        super().__init__(parent)
        
        self.serial_height = serial_height
        self.message_height = message_height
        self.max_serial_lines = max_serial_lines
        self.max_message_lines = max_message_lines
        self.padding = padding
        
        # Internal buffers for efficiency
        self._serial_buffer = []
        self._message_buffer = []
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the message panel UI with two sections."""
        # Serial Monitor section (top)
        serial_lf = ttk.LabelFrame(self, text="Serial Monitor", padding=self.padding)
        serial_lf.pack(fill="both", expand=False, padx=0, pady=(0, 8))
        
        serial_frame = ttk.Frame(serial_lf)
        serial_frame.pack(fill="both", expand=True)
        
        # Serial text widget with scrollbar
        self.serial_text = tk.Text(
            serial_frame, 
            wrap="none", 
            height=self.serial_height, 
            state="disabled"
        )
        serial_vsb = ttk.Scrollbar(
            serial_frame, 
            orient="vertical", 
            command=self.serial_text.yview
        )
        self.serial_text.configure(yscrollcommand=serial_vsb.set)
        self.serial_text.pack(side="left", fill="both", expand=True)
        serial_vsb.pack(side="right", fill="y")
        
        # Messages section (bottom)
        messages_lf = ttk.LabelFrame(self, text="Messages", padding=self.padding)
        messages_lf.pack(fill="both", expand=True, padx=0, pady=(0, 0))
        
        message_frame = ttk.Frame(messages_lf)
        message_frame.pack(fill="both", expand=True)
        
        # Message text widget with scrollbar
        self.message_text = tk.Text(
            message_frame, 
            wrap="none", 
            height=self.message_height, 
            state="disabled"
        )
        message_vsb = ttk.Scrollbar(
            message_frame, 
            orient="vertical", 
            command=self.message_text.yview
        )
        self.message_text.configure(yscrollcommand=message_vsb.set)
        self.message_text.pack(side="left", fill="both", expand=True)
        message_vsb.pack(side="right", fill="y")
    
    def append_serial(self, line):
        """
        Append a line to the serial monitor buffer.
        
        Args:
            line: String to append to serial monitor
        """
        if line is None:
            return
        
        self._serial_buffer.append(str(line))
        
        # Trim buffer if needed
        if len(self._serial_buffer) > self.max_serial_lines:
            self._serial_buffer = self._serial_buffer[-self.max_serial_lines:]
    
    def append_message(self, message):
        """
        Append a message to the messages buffer.
        
        Args:
            message: String to append to messages
        """
        if message is None:
            return
        
        self._message_buffer.append(str(message))
        
        # Trim buffer if needed
        if len(self._message_buffer) > self.max_message_lines:
            self._message_buffer = self._message_buffer[-self.max_message_lines:]
    
    def update_serial_display(self):
        """
        Update the serial monitor text widget from buffer.
        
        This should be called periodically (e.g., in poll loop) to refresh
        the display with batched updates for efficiency.
        """
        if not self._serial_buffer:
            return
        
        try:
            self.serial_text.configure(state="normal")
            self.serial_text.delete('1.0', 'end')
            self.serial_text.insert('end', '\n'.join(self._serial_buffer) + '\n')
            self.serial_text.see('end')
            self.serial_text.configure(state="disabled")
        except Exception:
            # Silently fail if widget is destroyed or not ready
            pass
    
    def update_message_display(self):
        """
        Update the messages text widget from buffer.
        
        This should be called periodically (e.g., in poll loop) to refresh
        the display with batched updates for efficiency.
        """
        if not self._message_buffer:
            return
        
        try:
            self.message_text.configure(state="normal")
            self.message_text.delete('1.0', 'end')
            self.message_text.insert('end', '\n'.join(self._message_buffer) + '\n')
            self.message_text.see('end')
            self.message_text.configure(state="disabled")
        except Exception:
            # Silently fail if widget is destroyed or not ready
            pass
    
    def update_displays(self):
        """
        Update both serial and message displays.
        
        Convenience method to update both text widgets at once.
        Call this from the main poll loop.
        """
        self.update_serial_display()
        self.update_message_display()
    
    def clear_serial(self):
        """Clear the serial monitor buffer and display."""
        self._serial_buffer.clear()
        try:
            self.serial_text.configure(state="normal")
            self.serial_text.delete('1.0', 'end')
            self.serial_text.configure(state="disabled")
        except Exception:
            pass
    
    def clear_messages(self):
        """Clear the messages buffer and display."""
        self._message_buffer.clear()
        try:
            self.message_text.configure(state="normal")
            self.message_text.delete('1.0', 'end')
            self.message_text.configure(state="disabled")
        except Exception:
            pass
    
    def clear_all(self):
        """Clear both serial and message buffers and displays."""
        self.clear_serial()
        self.clear_messages()
    
    def get_serial_buffer(self):
        """
        Get a copy of the current serial buffer.
        
        Returns:
            list: Copy of serial buffer lines
        """
        return self._serial_buffer.copy()
    
    def get_message_buffer(self):
        """
        Get a copy of the current message buffer.
        
        Returns:
            list: Copy of message buffer lines
        """
        return self._message_buffer.copy()
    
    def get_prefs(self):
        """
        Get current preferences for persistence.
        
        Returns:
            dict: Empty dict (no preferences to save for this panel)
        """
        # MessagePanel doesn't have user-configurable preferences
        # Could add things like text size, wrap mode, etc. in the future
        return {}
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences.
        
        Args:
            prefs: Dictionary with preferences (currently unused)
        """
        # No preferences to apply for this panel yet
        pass
