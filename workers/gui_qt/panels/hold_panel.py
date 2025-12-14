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
        
        # Animation state tracking (scrolling highlight)
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._on_blink_timer)
        self._scroll_index = 0
        self._is_scrolling = False  # Track if animation is active
        self._direction = 1
        self._base_text = "- HOLD STILL & UPRIGHT -"
        self._highlight_width = 5
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the hold still panel UI."""
        # Main layout - horizontal to center the text
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)  # Small padding
        main_layout.setSpacing(0)
        
        # Add stretch before text to center it
        main_layout.addStretch()
        
        # HOLD STILL label (we'll render per-character HTML for animation)
        self.hold_still_label = QLabel(self._base_text)
        self.hold_still_label.setAlignment(Qt.AlignCenter)
        
        # Style the text
        font = self.hold_still_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)  # Larger text for top-level visibility
        self.hold_still_label.setFont(font)
        
        # Initially subtle (static gray text)
        self._set_normal_style()
        
        main_layout.addWidget(self.hold_still_label)
        
        # Add stretch after text to center it
        main_layout.addStretch()
        
        # Set fixed height for consistent layout
        self.setFixedHeight(30)
        
    def _set_normal_style(self):
        """Set normal (non-blinking) style."""
        # When not animating we can use a simple stylesheet
        self.hold_still_label.setStyleSheet("color: #666666;")  # Subtle gray
        
    def _set_yellow_style(self):
        """Set yellow (blinking) style."""
        self.hold_still_label.setStyleSheet("color: #FFD700; font-weight: bold;")  # Bright gold/yellow
        
    def _on_blink_timer(self):
        """Handle timer ticks and advance the scrolling highlight (bounce side-to-side)."""
        if not self._is_scrolling:
            return

        n = len(self._base_text)
        width = min(self._highlight_width, n)
        # If text is too short for movement, just render highlight once
        if n <= width:
            self._scroll_index = 0
            self._update_scrolling_text()
            return

        max_index = n - width
        # Move and bounce at edges
        self._scroll_index += self._direction
        if self._scroll_index >= max_index:
            self._scroll_index = max_index
            self._direction = -1
        elif self._scroll_index <= 0:
            self._scroll_index = 0
            self._direction = 1

        self._update_scrolling_text()

    def _escape_char(self, ch: str) -> str:
        if ch == ' ':
            return '&nbsp;'
        if ch == '&':
            return '&amp;'
        if ch == '<':
            return '&lt;'
        if ch == '>':
            return '&gt;'
        return ch

    def _update_scrolling_text(self):
        """Render the label text as HTML with a single-character highlight that scrolls."""
        parts = []
        highlight_color = '#FFD700'
        normal_color = '#666666'
        n = len(self._base_text)
        width = min(self._highlight_width, n)
        # Build per-character spans so spacing and ampersands are preserved
        start = self._scroll_index
        end = start + width
        for i, ch in enumerate(self._base_text):
            esc = self._escape_char(ch)
            if start <= i < end:
                parts.append(f"<span style=\"color: {highlight_color}; font-weight: bold;\">{esc}</span>")
            else:
                parts.append(f"<span style=\"color: {normal_color};\">{esc}</span>")

        # Use rich text; QLabel will render it. Keep font set via setFont.
        html = ''.join(parts)
        self.hold_still_label.setText(html)
    
    def start_blinking(self):
        """Start the scrolling-color animation (keeps old API name)."""
        if self._is_scrolling:
            return  # Already running

        self._is_scrolling = True
        self._scroll_index = 0
        self._direction = 1
        # Faster update and 5-char wide highlight
        self._blink_timer.start(15)  # advance every 15ms
        # Immediately render current state
        self._update_scrolling_text()
        
    def stop_blinking(self):
        """Stop the scrolling-color animation and reset to normal text."""
        if not self._is_scrolling:
            return

        self._is_scrolling = False
        self._blink_timer.stop()
        self._scroll_index = 0
        # Reset to simple plain text to avoid leftover HTML styling
        self.hold_still_label.setText(self._base_text)
        self._set_normal_style()
        
    def is_blinking(self):
        """Return whether the panel is currently blinking."""
        return self._is_scrolling