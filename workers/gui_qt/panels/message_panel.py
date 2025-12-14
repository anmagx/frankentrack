"""
PyQt Message Panel for frankentrack GUI.

PyQt version of MessagePanel with identical functionality to tkinter version.
Provides two text display areas:
1. Serial Monitor - Raw serial data from IMU
2. Messages - Application logs and status messages
"""

from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QTextEdit, QScrollBar, 
                             QGroupBox, QSplitter, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor

from .base_panel import BasePanelQt
from config.config import MAX_TEXT_BUFFER_LINES


class MessagePanelQt(QFrame):
    """PyQt panel for displaying serial monitor and application messages."""
    
    def __init__(self, parent, serial_height=8, message_height=8, 
                 max_serial_lines=200, max_message_lines=100, padding=6):
        """
        Initialize the PyQt Message Panel.
        
        Args:
            parent: Parent PyQt widget
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
        
        # Internal buffers for efficiency (same as tkinter)
        self._serial_buffer = []
        self._message_buffer = []
        
        self.setup_ui()
    
    def setup_ui(self):
        """Build the message panel UI with two sections (mirrors tkinter layout exactly)."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Serial Monitor section (top) - same as tkinter serial_lf
        serial_group = QGroupBox("Serial Monitor")
        serial_layout = QVBoxLayout(serial_group)
        serial_layout.setContentsMargins(self.padding, self.padding, self.padding, self.padding)
        
        # Serial text widget (same functionality as tkinter)
        self.serial_text = QTextEdit()
        self.serial_text.setReadOnly(True)  # Same as tkinter state="disabled"
        self.serial_text.setLineWrapMode(QTextEdit.NoWrap)  # Same as tkinter wrap="none"
        self.serial_text.setMinimumHeight(80)  # Reduced minimum height
        # Allow the serial text to expand vertically when space is available
        self.serial_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Set monospace font for serial data (better readability)
        font = QFont("Courier New", 9)
        font.setFixedPitch(True)
        self.serial_text.setFont(font)
        
        serial_layout.addWidget(self.serial_text)
        main_layout.addWidget(serial_group)
        
        # Messages section (bottom) - same as tkinter messages_lf
        messages_group = QGroupBox("Messages")
        messages_layout = QVBoxLayout(messages_group)
        messages_layout.setContentsMargins(self.padding, self.padding, self.padding, self.padding)
        
        # Message text widget (same functionality as tkinter)
        self.message_text = QTextEdit()
        self.message_text.setReadOnly(True)  # Same as tkinter state="disabled"
        self.message_text.setLineWrapMode(QTextEdit.NoWrap)  # Same as tkinter wrap="none"
        self.message_text.setMinimumHeight(80)  # Reduced minimum height
        # Allow the message text to expand vertically to fill remaining space
        self.message_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Set monospace font for messages too
        self.message_text.setFont(font)
        
        messages_layout.addWidget(self.message_text)
        main_layout.addWidget(messages_group)
        
        # Set stretch factors to match tkinter behavior
        # Serial monitor: expand=False (fixed size)
        # Messages: expand=True (takes remaining space)
        main_layout.setStretchFactor(serial_group, 0)
        main_layout.setStretchFactor(messages_group, 1)
        
        # Allow the message panel to expand vertically to fill available space
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    
    def append_serial(self, line):
        """
        Append a line to the serial monitor buffer (identical to tkinter).
        
        Args:
            line: String to append to serial monitor
        """
        if line is None:
            return
        
        self._serial_buffer.append(str(line))
        
        # Trim buffer if needed (same logic as tkinter)
        if len(self._serial_buffer) > self.max_serial_lines:
            self._serial_buffer = self._serial_buffer[-self.max_serial_lines:]
    
    def append_message(self, message):
        """
        Append a message to the messages buffer (identical to tkinter).
        
        Args:
            message: String to append to messages
        """
        if message is None:
            return
        
        self._message_buffer.append(str(message))
        
        # Trim buffer if needed (same logic as tkinter)
        if len(self._message_buffer) > self.max_message_lines:
            self._message_buffer = self._message_buffer[-self.max_message_lines:]
    
    def update_serial_display(self):
        """
        Update the serial monitor text widget from buffer (identical logic to tkinter).
        
        This should be called periodically (e.g., in poll loop) to refresh
        the display with batched updates for efficiency.
        """
        if not self._serial_buffer:
            return
        
        # Skip expensive updates if widget is not visible
        if not self.isVisible():
            return
        
        try:
            # Clear and update content (same as tkinter logic)
            self.serial_text.clear()
            self.serial_text.setPlainText('\n'.join(self._serial_buffer))
            
            # Scroll to end (same as tkinter see('end'))
            cursor = self.serial_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.serial_text.setTextCursor(cursor)
            self.serial_text.ensureCursorVisible()
        except Exception:
            # Silently fail if widget is destroyed or not ready (same as tkinter)
            pass
    
    def update_message_display(self):
        """
        Update the messages text widget from buffer (identical logic to tkinter).
        
        This should be called periodically (e.g., in poll loop) to refresh
        the display with batched updates for efficiency.
        """
        if not self._message_buffer:
            return
        
        # Skip expensive updates if widget is not visible
        if not self.isVisible():
            return
        
        try:
            # Clear and update content (same as tkinter logic)
            self.message_text.clear()
            self.message_text.setPlainText('\n'.join(self._message_buffer))
            
            # Scroll to end (same as tkinter see('end'))
            cursor = self.message_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.message_text.setTextCursor(cursor)
            self.message_text.ensureCursorVisible()
        except Exception:
            # Silently fail if widget is destroyed or not ready (same as tkinter)
            pass
    
    def update_displays(self):
        """
        Update both serial and message displays (identical to tkinter).
        
        Convenience method to update both text widgets at once.
        Call this from the main poll loop.
        """
        self.update_serial_display()
        self.update_message_display()
    
    def clear_serial(self):
        """Clear the serial monitor buffer and display (identical to tkinter)."""
        self._serial_buffer.clear()
        try:
            self.serial_text.clear()
        except Exception:
            pass
    
    def clear_messages(self):
        """Clear the messages buffer and display (identical to tkinter)."""
        self._message_buffer.clear()
        try:
            self.message_text.clear()
        except Exception:
            pass
    
    def clear_all(self):
        """Clear both serial and message buffers and displays (identical to tkinter)."""
        self.clear_serial()
        self.clear_messages()
    
    def get_serial_buffer(self):
        """
        Get a copy of the current serial buffer (identical to tkinter).
        
        Returns:
            list: Copy of serial buffer lines
        """
        return self._serial_buffer.copy()
    
    def get_message_buffer(self):
        """
        Get a copy of the current message buffer (identical to tkinter).
        
        Returns:
            list: Copy of message buffer lines
        """
        return self._message_buffer.copy()
    
    def get_prefs(self):
        """
        Get current preferences for persistence (identical to tkinter).
        
        Returns:
            dict: Empty dict (no preferences to save for this panel)
        """
        # MessagePanel doesn't have user-configurable preferences
        # Could add things like text size, wrap mode, etc. in the future
        return {}
    
    def set_prefs(self, prefs):
        """
        Apply saved preferences (identical to tkinter).
        
        Args:
            prefs: Dictionary with preferences (currently unused)
        """
        # No preferences to apply for this panel yet
        pass