"""Helper to set window icons consistently across GUI dialogs.

Places the project's `img/icon.ico` on Tk windows when available.

Usage:
    from workers.gui.managers.icon_helper import set_window_icon
    set_window_icon(toplevel_window)
"""
import os


def set_window_icon(win) -> bool:
    """Set the application icon for a Tk `Toplevel` or `Tk` window.

    Tries multiple approaches for broad Tk/Tkinter compatibility:
    1. `iconbitmap(icon.ico)` (works on many Windows builds)
    2. `wm_iconphoto(False, PhotoImage)` using Pillow to load the icon

    The function is best-effort and will not raise on failure.

    Returns True if at least one method succeeded.
    """
    success = False
    try:
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

        # Prefer ico for iconbitmap; prefer png for PhotoImage when available
        photo_path = png_path or ico_path

        # Get the top-level root window for consistent icon application
        try:
            root = win.winfo_toplevel()
        except Exception:
            root = win

        # 1) Try iconbitmap on root using .ico (works for many Win/Tk builds)
        if ico_path:
            try:
                root.iconbitmap(ico_path)
                success = True
            except Exception:
                pass

        # 2) Try wm_iconphoto using Pillow -> ImageTk.PhotoImage
        if photo_path:
            try:
                from PIL import Image, ImageTk
                img = Image.open(photo_path)
                photo = ImageTk.PhotoImage(img)
                try:
                    # Use root to ensure taskbar/class icon updates
                    root.wm_iconphoto(False, photo)
                    # keep reference to avoid GC
                    try:
                        root._icon_photo = photo
                    except Exception:
                        pass
                    success = True
                except Exception:
                    pass
            except Exception:
                # Pillow not available or failed to load image
                pass

        return success
    except Exception:
        return False
