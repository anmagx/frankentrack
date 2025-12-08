"""
Theme manager for frankentrack GUI.

Handles loading and applying light/dark themes to the PyQt5 application.
"""
import os
from PyQt5.QtWidgets import QApplication


class ThemeManager:
    """Manages application themes and styling."""
    
    def __init__(self, app=None):
        """
        Initialize the theme manager.
        
        Args:
            app: QApplication instance
        """
        self.app = app or QApplication.instance()
        self.current_theme = 'light'
        
        # Calculate path to themes directory
        current_dir = os.path.dirname(__file__)  # workers/gui_qt/
        workers_dir = os.path.dirname(current_dir)  # workers/
        project_root = os.path.dirname(workers_dir)  # frankentrack/
        self.themes_dir = os.path.join(project_root, 'themes')
        
    def load_theme(self, theme_name):
        """
        Load and apply a theme.
        
        Args:
            theme_name: Theme name ('light' or 'dark')
        """
        if theme_name not in ['light', 'dark']:
            print(f"[ThemeManager] Unknown theme: {theme_name}, defaulting to light")
            theme_name = 'light'
        
        theme_file = os.path.join(self.themes_dir, f"{theme_name}.qss")
        
        try:
            if os.path.exists(theme_file):
                with open(theme_file, 'r', encoding='utf-8') as f:
                    stylesheet = f.read()
                
                if self.app:
                    self.app.setStyleSheet(stylesheet)
                    self.current_theme = theme_name
                    print(f"[ThemeManager] Applied {theme_name} theme")
                else:
                    print(f"[ThemeManager] No QApplication instance available")
            else:
                print(f"[ThemeManager] Theme file not found: {theme_file}")
                
        except Exception as e:
            print(f"[ThemeManager] Error loading theme {theme_name}: {e}")
    
    def get_current_theme(self):
        """
        Get the currently active theme name.
        
        Returns:
            str: Current theme name
        """
        return self.current_theme
    
    def toggle_theme(self):
        """Toggle between light and dark themes."""
        new_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.load_theme(new_theme)
        return new_theme
    
    def get_available_themes(self):
        """
        Get list of available theme names.
        
        Returns:
            list: Available theme names
        """
        return ['light', 'dark']