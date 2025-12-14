"""
Hold Still Panel for frankentrack GUI.

A dedicated panel for displaying the "HOLD STILL" indicator at the top of the application.
Shows blinking yellow text during sensor initialization and data waiting phases.
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont


class HoldPanelQt(QWidget):
    """Panel for displaying HOLD STILL indicator at the top of the application."""
    
    def __init__(self, parent=None):
        """
        Initialize the Hold Still Panel.
        
        Args:
            parent: Parent PyQt widget
        """
        super().__init__(parent)
        
        # Blinking state tracking
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._on_blink_timer)
        self._blink_state = False  # Track blink state (False=normal, True=yellow)
        self._is_blinking = False  # Track if we should be blinking
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the hold still panel UI."""
        # Main layout - horizontal to center the text
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)  # Small padding
        main_layout.setSpacing(0)
        
        # Add stretch before text to center it
        main_layout.addStretch()
        
        # HOLD STILL label
        self.hold_still_label = QLabel("- HOLD STILL & UPRIGHT -")
        self.hold_still_label.setAlignment(Qt.AlignCenter)
        
        # Style the text
        font = self.hold_still_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)  # Larger text for top-level visibility
        self.hold_still_label.setFont(font)
        
        # Initially hidden/subtle
        self._set_normal_style()
        
        main_layout.addWidget(self.hold_still_label)
        
        # Add stretch after text to center it
        main_layout.addStretch()
        
        # Set fixed height for consistent layout
        self.setFixedHeight(30)
        
    def _set_normal_style(self):
        """Set normal (non-blinking) style."""
        self.hold_still_label.setStyleSheet("color: #666666;")  # Subtle gray
        
    def _set_yellow_style(self):
        """Set yellow (blinking) style."""
        self.hold_still_label.setStyleSheet("color: #FFD700; font-weight: bold;")  # Bright gold/yellow
        
    def _on_blink_timer(self):
        """Handle blinking timer for HOLD STILL text."""
        if not self._is_blinking:
            return
            
        self._blink_state = not self._blink_state
        if self._blink_state:
            self._set_yellow_style()
        else:
            self._set_normal_style()
    
    def start_blinking(self):
        """Start blinking animation for HOLD STILL text."""
        if self._is_blinking:
            return  # Already blinking
            
        self._is_blinking = True
        self._blink_timer.start(250)  # Blink every 500ms
        self._blink_state = False
        
    def stop_blinking(self):
        """Stop blinking animation and reset to normal color."""
        if not self._is_blinking:
            return  # Already stopped
            
        self._is_blinking = False
        self._blink_timer.stop()
        self._blink_state = False
        self._set_normal_style()
        
    def is_blinking(self):
        """Return whether the panel is currently blinking."""
        return self._is_blinking