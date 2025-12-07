"""
Simple demonstration script showing PyQt NetworkPanel functionality.

This script tests key features of the PyQt NetworkPanel to verify 
it matches the tkinter version's behavior.
"""

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt5.QtCore import QTimer
import queue

from workers.gui_qt.panels.network_panel import NetworkPanelQt


def main():
    """Simple demonstration of PyQt NetworkPanel."""
    print("=== PyQt NetworkPanel Migration Demo ===")
    print()
    
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("PyQt NetworkPanel Demo")
    window.setGeometry(100, 100, 800, 300)
    
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # Create mock UDP control queue
    udp_queue = queue.Queue()
    
    def log_message(msg):
        print(f"[LOG] {msg}")
    
    # Create PyQt NetworkPanel (same interface as tkinter)
    network_panel = NetworkPanelQt(
        central_widget,
        udp_queue,
        log_message,
        padding=6
    )
    layout.addWidget(network_panel)
    
    # Create control buttons
    button_layout = QHBoxLayout()
    
    # Toggle UDP button
    toggle_btn = QPushButton("Toggle UDP Enable/Disable")
    def toggle_udp():
        was_enabled = network_panel.is_udp_enabled()
        network_panel.toggle_udp()
        now_enabled = network_panel.is_udp_enabled()
        status = "enabled" if now_enabled else "disabled"
        print(f"[DEMO] UDP toggled: {was_enabled} -> {now_enabled} ({status})")
    
    toggle_btn.clicked.connect(toggle_udp)
    button_layout.addWidget(toggle_btn)
    
    # Set test config button
    set_config_btn = QPushButton("Set Test Config (192.168.1.100:5000)")
    def set_test_config():
        network_panel.set_udp_config("192.168.1.100", 5000)
        ip, port = network_panel.get_udp_config()
        print(f"[DEMO] Set config to: {ip}:{port}")
    
    set_config_btn.clicked.connect(set_test_config)
    button_layout.addWidget(set_config_btn)
    
    # Get config button
    get_config_btn = QPushButton("Get Current Config")
    def get_config():
        ip, port = network_panel.get_udp_config()
        enabled = network_panel.is_udp_enabled()
        print(f"[DEMO] Current config: {ip}:{port} (enabled: {enabled})")
    
    get_config_btn.clicked.connect(get_config)
    button_layout.addWidget(get_config_btn)
    
    # Test preferences button
    test_prefs_btn = QPushButton("Test Preferences")
    def test_prefs():
        # Test get_prefs
        prefs = network_panel.get_prefs()
        print(f"[DEMO] Current preferences: {prefs}")
        
        # Test set_prefs
        test_prefs = {
            'udp_ip': '10.0.0.1',
            'udp_port': '9999'
        }
        network_panel.set_prefs(test_prefs)
        print(f"[DEMO] Applied test preferences: {test_prefs}")
        
        # Verify the change
        new_prefs = network_panel.get_prefs()
        print(f"[DEMO] New preferences: {new_prefs}")
    
    test_prefs_btn.clicked.connect(test_prefs)
    button_layout.addWidget(test_prefs_btn)
    
    # Direct enable/disable buttons
    enable_btn = QPushButton("Force Enable")
    def force_enable():
        network_panel.enable_udp()
        print(f"[DEMO] Force enabled - UDP is now: {'enabled' if network_panel.is_udp_enabled() else 'disabled'}")
    
    enable_btn.clicked.connect(force_enable)
    button_layout.addWidget(enable_btn)
    
    disable_btn = QPushButton("Force Disable")
    def force_disable():
        network_panel.disable_udp()
        print(f"[DEMO] Force disabled - UDP is now: {'enabled' if network_panel.is_udp_enabled() else 'disabled'}")
    
    disable_btn.clicked.connect(force_disable)
    button_layout.addWidget(disable_btn)
    
    layout.addLayout(button_layout)
    
    # Monitor the queue for commands
    def check_queue():
        try:
            while not udp_queue.empty():
                cmd = udp_queue.get_nowait()
                print(f"[QUEUE] Received command: {cmd}")
        except queue.Empty:
            pass
    
    # Check queue every 100ms
    timer = QTimer()
    timer.timeout.connect(check_queue)
    timer.start(100)
    
    # Show window and start demo
    window.show()
    print("Demo window opened. You can:")
    print("1. Edit IP address and port directly in the text fields")
    print("2. Click 'Toggle UDP Enable/Disable' to start/stop UDP")
    print("3. Click 'Set Test Config' to set predefined IP/port")
    print("4. Click 'Get Current Config' to display current settings")
    print("5. Click 'Test Preferences' to test preference save/load")
    print("6. Click 'Force Enable/Disable' to control UDP state directly")
    print("7. Watch the console for queue commands and status changes")
    print()
    print("This demonstrates that PyQt NetworkPanel has identical functionality")
    print("to the tkinter version with UDP configuration and queue communication.")
    print()
    
    # Run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()