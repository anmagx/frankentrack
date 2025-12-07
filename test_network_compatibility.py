"""
Test script to verify PyQt NetworkPanel matches tkinter NetworkPanel exactly.
"""

import sys
from PyQt5.QtWidgets import QApplication
import queue

# Test both implementations
from workers.gui.panels.network_panel import NetworkPanel as NetworkPanelTk
from workers.gui_qt.panels.network_panel import NetworkPanelQt

def test_interface_compatibility():
    """Test that both NetworkPanels have identical interfaces."""
    print("=== NetworkPanel Interface Compatibility Test ===")
    
    # Create temporary app for PyQt testing
    app = QApplication(sys.argv)
    
    # Create mock parent widgets and queues
    import tkinter as tk
    tk_root = tk.Tk()
    tk_root.withdraw()  # Hide window
    
    from PyQt5.QtWidgets import QWidget
    qt_parent = QWidget()
    
    # Create mock queues
    tk_queue = queue.Queue()
    qt_queue = queue.Queue()
    
    def mock_callback(msg):
        print(f"[CALLBACK] {msg}")
    
    # Create both network panels
    tk_network = NetworkPanelTk(tk_root, tk_queue, mock_callback)
    qt_network = NetworkPanelQt(qt_parent, qt_queue, mock_callback)
    
    print("✅ Both NetworkPanels created successfully")
    
    # Test method signatures
    methods_to_test = [
        'toggle_udp',
        'set_udp_config',
        'get_udp_config', 
        'is_udp_enabled',
        'enable_udp',
        'disable_udp',
        'get_prefs',
        'set_prefs'
    ]
    
    for method in methods_to_test:
        assert hasattr(tk_network, method), f"tkinter NetworkPanel missing {method}"
        assert hasattr(qt_network, method), f"PyQt NetworkPanel missing {method}"
        print(f"✅ Both have method: {method}")
    
    # Test functionality equivalence
    print("\n=== Functionality Test ===")
    
    # Test get_udp_config - should return same default
    tk_config = tk_network.get_udp_config()
    qt_config = qt_network.get_udp_config()
    
    assert tk_config == qt_config, f"Default configs differ: {tk_config} vs {qt_config}"
    print(f"✅ Default config identical: {tk_config}")
    
    # Test set_udp_config
    test_ip = "192.168.1.100"
    test_port = 5000
    
    tk_network.set_udp_config(test_ip, test_port)
    qt_network.set_udp_config(test_ip, test_port)
    
    tk_config_new = tk_network.get_udp_config()
    qt_config_new = qt_network.get_udp_config()
    
    assert tk_config_new == qt_config_new, f"Set configs differ: {tk_config_new} vs {qt_config_new}"
    assert tk_config_new == (test_ip, test_port), f"Set config incorrect: {tk_config_new}"
    print(f"✅ set_udp_config works identically: {tk_config_new}")
    
    # Test is_udp_enabled - should start disabled
    tk_enabled = tk_network.is_udp_enabled()
    qt_enabled = qt_network.is_udp_enabled()
    
    assert tk_enabled == qt_enabled == False, "Both should start with UDP disabled"
    print("✅ Both start with UDP disabled")
    
    # Test enable_udp
    tk_network.enable_udp()
    qt_network.enable_udp()
    
    tk_enabled_after = tk_network.is_udp_enabled()
    qt_enabled_after = qt_network.is_udp_enabled()
    
    assert tk_enabled_after == qt_enabled_after == True, "Both should be enabled after enable_udp()"
    print("✅ enable_udp() works identically")
    
    # Test disable_udp
    tk_network.disable_udp()
    qt_network.disable_udp()
    
    tk_disabled_after = tk_network.is_udp_enabled()
    qt_disabled_after = qt_network.is_udp_enabled()
    
    assert tk_disabled_after == qt_disabled_after == False, "Both should be disabled after disable_udp()"
    print("✅ disable_udp() works identically")
    
    # Test preferences
    tk_prefs = tk_network.get_prefs()
    qt_prefs = qt_network.get_prefs()
    
    assert isinstance(tk_prefs, dict), "tkinter get_prefs should return dict"
    assert isinstance(qt_prefs, dict), "PyQt get_prefs should return dict"
    assert set(tk_prefs.keys()) == set(qt_prefs.keys()), "Both should have same pref keys"
    expected_keys = {'udp_ip', 'udp_port'}
    assert set(tk_prefs.keys()) == expected_keys, f"Expected keys {expected_keys}, got {set(tk_prefs.keys())}"
    
    print(f"✅ get_prefs identical structure: {list(tk_prefs.keys())}")
    
    # Test set_prefs
    test_prefs = {
        'udp_ip': '10.0.0.1',
        'udp_port': '9999'
    }
    
    tk_network.set_prefs(test_prefs)
    qt_network.set_prefs(test_prefs)
    
    tk_prefs_after = tk_network.get_prefs()
    qt_prefs_after = qt_network.get_prefs()
    
    assert tk_prefs_after['udp_ip'] == qt_prefs_after['udp_ip'] == '10.0.0.1'
    assert tk_prefs_after['udp_port'] == qt_prefs_after['udp_port'] == '9999'
    
    print("✅ set_prefs works identically")
    
    # Test queue communication
    print("\n=== Queue Communication Test ===")
    
    # Clear queues first
    while not tk_queue.empty():
        tk_queue.get_nowait()
    while not qt_queue.empty():
        qt_queue.get_nowait()
    
    # Test toggle functionality with queue monitoring
    tk_network.toggle_udp()  # Should enable
    qt_network.toggle_udp()  # Should enable
    
    # Check queues have same commands
    tk_commands = []
    while not tk_queue.empty():
        tk_commands.append(tk_queue.get_nowait())
    
    qt_commands = []
    while not qt_queue.empty():
        qt_commands.append(qt_queue.get_nowait())
    
    assert len(tk_commands) == len(qt_commands), f"Different command counts: {len(tk_commands)} vs {len(qt_commands)}"
    assert tk_commands == qt_commands, f"Different commands: {tk_commands} vs {qt_commands}"
    
    print(f"✅ Queue commands identical: {tk_commands}")
    
    # Cleanup
    tk_root.destroy()
    app.quit()
    
    print("\n🎉 ALL TESTS PASSED - PyQt NetworkPanel is 100% compatible!")
    return True

if __name__ == "__main__":
    test_interface_compatibility()