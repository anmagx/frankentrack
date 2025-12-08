"""Helper to set window icons consistently across GUI dialogs.

Places the project's `img/icon.ico` on PyQt5 windows when available.

Usage:
    from workers.gui_qt.managers.icon_helper import set_window_icon
    set_window_icon(qt_window)
"""
import os


def set_window_icon(win) -> bool:
    """Set the application icon for a PyQt5 window.

    Args:
        win: PyQt5 QWidget or QMainWindow to set icon for
        
    Returns:
        True if icon was set successfully, False otherwise
    """
    try:
        from PyQt5.QtGui import QIcon
        
        # Robustly search upwards from this file for the project's img/icon.ico
        start_dir = os.path.dirname(__file__)
        ico_path = None
        png_path = None
        for _ in range(6):
            candidate_ico = os.path.join(start_dir, 'img', 'icon.ico')
            candidate_png = os.path.join(start_dir, 'img', 'icon.png')
            if os.path.exists(candidate_ico):
                ico_path = candidate_ico
                break
            if os.path.exists(candidate_png) and png_path is None:
                png_path = candidate_png
            # move up one level
            parent = os.path.dirname(start_dir)
            if not parent or parent == start_dir:
                break
            start_dir = parent

        # Use ico or png, whichever we found
        icon_path = ico_path or png_path
        
        if icon_path:
            icon = QIcon(icon_path)
            if not icon.isNull():
                win.setWindowIcon(icon)
                return True
                
    except Exception:
        pass
    
    return False