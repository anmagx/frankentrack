"""
PyQt GUI package for frankentrack.

PyQt5/6 implementation of the GUI with same queue-based architecture as tkinter version.
Maintains identical interface for worker communication.
"""
from . import panels
from . import helpers
from . import managers
from .managers.theme_manager import ThemeManager

__all__ = ['panels', 'helpers', 'managers', 'ThemeManager']