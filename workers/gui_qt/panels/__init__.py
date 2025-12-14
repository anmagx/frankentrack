"""
PyQt panels package for frankentrack.

Contains PyQt implementations of GUI panels with same interfaces as tkinter versions.
"""

# Panel imports for the GUI
from .about_panel import AboutPanel
from .calibration_panel import CalibrationPanelQt
from .diagnostics_panel import DiagnosticsPanelQt
from .hold_panel import HoldPanelQt
from .message_panel import MessagePanelQt
from .network_panel import NetworkPanelQt
from .orientation_panel import OrientationPanelQt
from .preferences_panel import PreferencesPanel
from .serial_panel import SerialPanelQt
from .status_bar import StatusBarQt

__all__ = [
    'AboutPanel',
    'CalibrationPanelQt',
    'DiagnosticsPanelQt',
    'HoldPanelQt',
    'MessagePanelQt',
    'NetworkPanelQt',
    'OrientationPanelQt',
    'PreferencesPanel',
    'SerialPanelQt',
    'StatusBarQt'
]