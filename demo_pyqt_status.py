"""
Simple demonstration script showing PyQt StatusBar functionality.

This script tests key features of the PyQt StatusBar to verify 
it matches the tkinter version's behavior.
"""

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt5.QtCore import QTimer
import random

from workers.gui_qt.panels.status_bar import StatusBarQt


def main():
    """Simple demonstration of PyQt StatusBar."""
    print("=== PyQt StatusBar Migration Demo ===")
    print()
    
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("PyQt StatusBar Demo")
    window.setGeometry(100, 100, 800, 200)
    
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # Create PyQt StatusBar (same interface as tkinter)
    status_bar = StatusBarQt(central_widget, relief="sunken")
    layout.addWidget(status_bar)
    
    # Create control buttons
    button_layout = QHBoxLayout()
    
    # Update rates button
    update_rates_btn = QPushButton("Update Random Rates")
    def update_rates():
        msg_rate = random.uniform(10, 100)
        send_rate = random.uniform(5, 50) 
        camera_fps = random.uniform(15, 30)
        
        status_bar.update_all(
            msg_rate=msg_rate,
            send_rate=send_rate,
            camera_fps=camera_fps
        )
        
        values = status_bar.get_values()
        print(f"[DEMO] Updated rates: {values}")
    
    update_rates_btn.clicked.connect(update_rates)
    button_layout.addWidget(update_rates_btn)
    
    # Toggle device status button
    toggle_device_btn = QPushButton("Toggle Device Status")
    device_stationary = [True]  # Use list for closure
    def toggle_device():
        device_stationary[0] = not device_stationary[0]
        status_bar.update_device_status(device_stationary[0])
        status = "stationary" if device_stationary[0] else "moving"
        print(f"[DEMO] Device status: {status}")
    
    toggle_device_btn.clicked.connect(toggle_device)
    button_layout.addWidget(toggle_device_btn)
    
    # Reset button
    reset_btn = QPushButton("Reset All")
    def reset_all():
        status_bar.reset()
        values = status_bar.get_values()
        print(f"[DEMO] Reset values: {values}")
    
    reset_btn.clicked.connect(reset_all)
    button_layout.addWidget(reset_btn)
    
    # Test prefs button
    test_prefs_btn = QPushButton("Test Preferences")
    def test_prefs():
        # Test get_prefs
        prefs = status_bar.get_prefs()
        print(f"[DEMO] StatusBar preferences: {prefs}")
        
        # Test set_prefs (should be no-op)
        status_bar.set_prefs({'dummy': 'value'})
        print(f"[DEMO] Preferences test completed")
    
    test_prefs_btn.clicked.connect(test_prefs)
    button_layout.addWidget(test_prefs_btn)
    
    layout.addLayout(button_layout)
    
    # Auto-update timer for demonstration
    auto_timer = QTimer()
    def auto_update():
        if random.choice([True, False]):  # 50% chance to update
            msg_rate = random.uniform(20, 80)
            send_rate = random.uniform(10, 40)
            camera_fps = random.uniform(20, 30)
            status_bar.update_all(msg_rate, send_rate, camera_fps)
            
            # Sometimes update device status too
            if random.random() < 0.2:  # 20% chance
                stationary = random.choice([True, False])
                status_bar.update_device_status(stationary)
    
    auto_timer.timeout.connect(auto_update)
    auto_timer.start(2000)  # Update every 2 seconds
    
    # Show window and start demo
    window.show()
    print("Demo window opened. You can:")
    print("1. Click 'Update Random Rates' to set random performance metrics")
    print("2. Click 'Toggle Device Status' to switch between moving/stationary")
    print("3. Click 'Reset All' to reset all values to zero")
    print("4. Click 'Test Preferences' to test preference methods")
    print("5. Watch auto-updates every 2 seconds")
    print()
    print("This demonstrates that PyQt StatusBar has identical functionality")
    print("to the tkinter version with real-time metric display.")
    print()
    
    # Run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()