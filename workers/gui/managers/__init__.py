"""
GUI managers package for frankentrack.

Contains utility classes for GUI operations:
- PreferencesManager: Centralized preference persistence
- camera_enumerator: (Deprecated - functionality moved to CameraPanel)
- queue_manager: (Deprecated - functionality in gui_wrk_v2.py)
"""

from workers.gui.managers.preferences_manager import PreferencesManager

__all__ = ['PreferencesManager']
