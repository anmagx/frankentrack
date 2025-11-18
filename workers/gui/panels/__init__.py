"""
GUI panels package for Acceltrack.

Contains refactored UI panel components for better maintainability.
Each panel is self-contained and can be tested independently.
"""

from workers.gui.panels.serial_panel import SerialPanel
from workers.gui.panels.message_panel import MessagePanel
from workers.gui.panels.orientation_panel import OrientationPanel
from workers.gui.panels.status_bar import StatusBar
from workers.gui.panels.network_panel import NetworkPanel
from workers.gui.panels.camera_panel import CameraPanel

__all__ = ['SerialPanel', 'MessagePanel', 'OrientationPanel', 'StatusBar', 'NetworkPanel', 'CameraPanel']
