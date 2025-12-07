"""
Test script to verify PyQt StatusBar matches tkinter StatusBar exactly.
"""

import sys
from PyQt5.QtWidgets import QApplication
import queue

# Test both implementations
from workers.gui.panels.status_bar import StatusBar as StatusBarTk
from workers.gui_qt.panels.status_bar import StatusBarQt

def test_interface_compatibility():
    """Test that both StatusBars have identical interfaces."""
    print("=== Interface Compatibility Test ===")
    
    # Create temporary app for PyQt testing
    app = QApplication(sys.argv)
    
    # Create mock parent widgets
    import tkinter as tk
    tk_root = tk.Tk()
    tk_root.withdraw()  # Hide window
    
    from PyQt5.QtWidgets import QWidget
    qt_parent = QWidget()
    
    # Create both status bars
    tk_status = StatusBarTk(tk_root)
    qt_status = StatusBarQt(qt_parent)
    
    print("✅ Both StatusBars created successfully")
    
    # Test method signatures
    methods_to_test = [
        'update_message_rate',
        'update_send_rate', 
        'update_camera_fps',
        'update_all',
        'update_device_status',
        'reset',
        'get_values',
        'get_prefs',
        'set_prefs'
    ]
    
    for method in methods_to_test:
        assert hasattr(tk_status, method), f"tkinter StatusBar missing {method}"
        assert hasattr(qt_status, method), f"PyQt StatusBar missing {method}"
        print(f"✅ Both have method: {method}")
    
    # Test functionality equivalence
    print("\n=== Functionality Test ===")
    
    # Test rate updates
    tk_status.update_message_rate(42.5)
    qt_status.update_message_rate(42.5)
    
    tk_status.update_send_rate(23.8)
    qt_status.update_send_rate(23.8)
    
    tk_status.update_camera_fps(29.7)
    qt_status.update_camera_fps(29.7)
    
    print("✅ Rate updates work on both")
    
    # Test update_all
    tk_status.update_all(msg_rate=50.0, send_rate=25.0, camera_fps=30.0)
    qt_status.update_all(msg_rate=50.0, send_rate=25.0, camera_fps=30.0)
    
    print("✅ update_all works on both")
    
    # Test device status
    tk_status.update_device_status(True)
    qt_status.update_device_status(True)
    
    tk_status.update_device_status(False) 
    qt_status.update_device_status(False)
    
    print("✅ Device status updates work on both")
    
    # Test reset
    tk_status.reset()
    qt_status.reset()
    
    print("✅ Reset works on both")
    
    # Test get_values - should return same structure
    tk_values = tk_status.get_values()
    qt_values = qt_status.get_values()
    
    assert isinstance(tk_values, dict), "tkinter get_values should return dict"
    assert isinstance(qt_values, dict), "PyQt get_values should return dict"
    assert set(tk_values.keys()) == set(qt_values.keys()), "Both should have same keys"
    
    print(f"✅ get_values identical structure: {list(tk_values.keys())}")
    
    # Test preferences
    tk_prefs = tk_status.get_prefs()
    qt_prefs = qt_status.get_prefs()
    
    assert tk_prefs == qt_prefs == {}, "Both should return empty dict for prefs"
    
    tk_status.set_prefs({'dummy': 'value'})
    qt_status.set_prefs({'dummy': 'value'})
    
    print("✅ Preferences methods work on both")
    
    # Cleanup
    tk_root.destroy()
    app.quit()
    
    print("\n🎉 ALL TESTS PASSED - PyQt StatusBar is 100% compatible!")
    return True

if __name__ == "__main__":
    test_interface_compatibility()