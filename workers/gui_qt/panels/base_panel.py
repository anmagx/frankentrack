"""Base classes for PyQt panels to maintain consistency."""

from PyQt5.QtWidgets import QGroupBox, QFrame, QWidget
from PyQt5.QtCore import pyqtSignal, QObject
from abc import ABC, abstractmethod


class BasePanelQt(QGroupBox):
    """Base class for all PyQt panels (equivalent to ttk.LabelFrame)."""
    
    # Common signals for all panels
    message_signal = pyqtSignal(str)  # For logging messages
    
    def __init__(self, parent, title="", **kwargs):
        super().__init__(title, parent)
        self.message_callback = kwargs.get('message_callback', None)
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the panel UI (override in subclasses)."""
        pass
        
    def get_prefs(self):
        """Get panel preferences for saving (override in subclasses)."""
        return {}
        
    def set_prefs(self, prefs):
        """Apply saved preferences (override in subclasses)."""
        pass
        
    def log_message(self, msg):
        """Helper to log messages via callback or signal."""
        if self.message_callback:
            self.message_callback(msg)
        else:
            self.message_signal.emit(msg)