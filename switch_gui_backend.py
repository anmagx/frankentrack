"""
GUI Backend Switcher for frankentrack

This utility allows you to easily switch between the tkinter and PyQt5 GUI backends
without manually editing configuration files.

Usage:
    python switch_gui_backend.py pyqt      # Switch to PyQt5 tabbed interface
    python switch_gui_backend.py tkinter   # Switch to original tkinter interface  
    python switch_gui_backend.py           # Show current backend
"""

import sys
import os


def get_current_backend():
    """Get the currently configured GUI backend."""
    try:
        # Import the config module to read current setting
        import config.config as cfg
        return cfg.GUI_BACKEND
    except Exception as e:
        print(f"Error reading config: {e}")
        return None


def set_backend(backend):
    """Set the GUI backend by modifying config.py."""
    backend = backend.lower()
    
    if backend not in ['tkinter', 'pyqt']:
        print(f"Error: Invalid backend '{backend}'. Must be 'tkinter' or 'pyqt'")
        return False
    
    config_file = 'config/config.py'
    
    if not os.path.exists(config_file):
        print(f"Error: Config file '{config_file}' not found")
        return False
    
    try:
        # Read the current config file
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find and update the GUI_BACKEND line
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith('GUI_BACKEND =') and not line.strip().startswith('#'):
                lines[i] = f"GUI_BACKEND = '{backend}'\n"
                updated = True
                break
        
        if not updated:
            print("Error: Could not find GUI_BACKEND setting in config file")
            return False
        
        # Write back the modified config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"✓ GUI backend set to: {backend}")
        
        # Display what this means
        if backend == 'pyqt':
            print("  → PyQt5 tabbed interface will be used")
            print("  → Orientation Tracking tab: Serial, Message, Calibration, Orientation, Network")
            print("  → Position Tracking tab: Camera")
            print("  → Message panel can be collapsed/expanded")
        else:
            print("  → Original tkinter interface will be used")
            print("  → Full panel layout in single window")
        
        print("\nRestart frankentrack for changes to take effect.")
        return True
        
    except Exception as e:
        print(f"Error updating config: {e}")
        return False


def main():
    """Main function for the GUI backend switcher."""
    if len(sys.argv) < 2:
        # Show current backend
        current = get_current_backend()
        if current:
            print(f"Current GUI backend: {current}")
            if current == 'pyqt':
                print("  → Using PyQt5 tabbed interface")
            else:
                print("  → Using tkinter interface")
        print("\nUsage:")
        print("  python switch_gui_backend.py pyqt      # Switch to PyQt5 tabbed")
        print("  python switch_gui_backend.py tkinter   # Switch to tkinter")
        return
    
    backend = sys.argv[1]
    success = set_backend(backend)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()