"""
Simple demonstration script showing PyQt MessagePanel functionality.

This script tests key features of the PyQt MessagePanel to verify 
it matches the tkinter version's behavior.
"""

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt5.QtCore import QTimer
import time
import random

from workers.gui_qt.panels.message_panel import MessagePanelQt


def main():
    """Simple demonstration of PyQt MessagePanel."""
    print("=== PyQt MessagePanel Migration Demo ===")
    print()
    
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("PyQt MessagePanel Demo")
    window.setGeometry(100, 100, 900, 600)
    
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # Create PyQt MessagePanel (same interface as tkinter)
    message_panel = MessagePanelQt(
        central_widget,
        serial_height=8,
        message_height=8,
        max_serial_lines=200,
        max_message_lines=100,
        padding=6
    )
    layout.addWidget(message_panel)
    
    # Create control buttons
    button_layout = QHBoxLayout()
    
    # Add serial data button
    add_serial_btn = QPushButton("Add Serial Data")
    def add_serial():
        timestamp = time.time()
        yaw = random.uniform(-180, 180)
        pitch = random.uniform(-90, 90) 
        roll = random.uniform(-180, 180)
        serial_line = f"RAW: yaw={yaw:.2f}, pitch={pitch:.2f}, roll={roll:.2f}, t={timestamp:.3f}"
        message_panel.append_serial(serial_line)
        print(f"[DEMO] Added serial: {serial_line}")
    
    add_serial_btn.clicked.connect(add_serial)
    button_layout.addWidget(add_serial_btn)
    
    # Add message button  
    add_message_btn = QPushButton("Add Message")
    message_counter = [0]  # Use list for closure
    def add_message():
        message_counter[0] += 1
        timestamp = time.strftime('%H:%M:%S')
        message = f"[{timestamp}] Test message #{message_counter[0]} from PyQt demo"
        message_panel.append_message(message)
        print(f"[DEMO] Added message: {message}")
    
    add_message_btn.clicked.connect(add_message)
    button_layout.addWidget(add_message_btn)
    
    # Update displays button
    update_btn = QPushButton("Update Displays")
    def update_displays():
        message_panel.update_displays()
        serial_count = len(message_panel.get_serial_buffer())
        message_count = len(message_panel.get_message_buffer())
        print(f"[DEMO] Updated displays - Serial: {serial_count} lines, Messages: {message_count} lines")
    
    update_btn.clicked.connect(update_displays)
    button_layout.addWidget(update_btn)
    
    # Clear serial button
    clear_serial_btn = QPushButton("Clear Serial")
    def clear_serial():
        message_panel.clear_serial()
        message_panel.update_displays()
        print("[DEMO] Cleared serial buffer")
    
    clear_serial_btn.clicked.connect(clear_serial)
    button_layout.addWidget(clear_serial_btn)
    
    # Clear messages button
    clear_messages_btn = QPushButton("Clear Messages")
    def clear_messages():
        message_panel.clear_messages()
        message_panel.update_displays()
        print("[DEMO] Cleared message buffer")
    
    clear_messages_btn.clicked.connect(clear_messages)
    button_layout.addWidget(clear_messages_btn)
    
    # Clear all button
    clear_all_btn = QPushButton("Clear All")
    def clear_all():
        message_panel.clear_all()
        serial_count = len(message_panel.get_serial_buffer())
        message_count = len(message_panel.get_message_buffer())
        print(f"[DEMO] Cleared all - Serial: {serial_count}, Messages: {message_count}")
    
    clear_all_btn.clicked.connect(clear_all)
    button_layout.addWidget(clear_all_btn)
    
    # Get buffers button
    get_buffers_btn = QPushButton("Get Buffers Info")
    def get_buffers():
        serial_buffer = message_panel.get_serial_buffer()
        message_buffer = message_panel.get_message_buffer()
        
        print(f"[DEMO] Serial buffer: {len(serial_buffer)} lines")
        print(f"[DEMO] Message buffer: {len(message_buffer)} lines")
        
        if serial_buffer:
            print(f"[DEMO] Last serial: {serial_buffer[-1]}")
        if message_buffer:
            print(f"[DEMO] Last message: {message_buffer[-1]}")
    
    get_buffers_btn.clicked.connect(get_buffers)
    button_layout.addWidget(get_buffers_btn)
    
    # Test prefs button
    test_prefs_btn = QPushButton("Test Preferences")
    def test_prefs():
        # Test get_prefs
        prefs = message_panel.get_prefs()
        print(f"[DEMO] MessagePanel preferences: {prefs}")
        
        # Test set_prefs (should be no-op)
        message_panel.set_prefs({'dummy': 'value'})
        print(f"[DEMO] Preferences test completed")
    
    test_prefs_btn.clicked.connect(test_prefs)
    button_layout.addWidget(test_prefs_btn)
    
    layout.addLayout(button_layout)
    
    # Auto-add data timer for demonstration
    auto_timer = QTimer()
    def auto_add_data():
        if random.choice([True, False]):  # 50% chance to add serial
            add_serial()
        
        if random.random() < 0.3:  # 30% chance to add message
            add_message()
        
        # Always update displays
        message_panel.update_displays()
    
    auto_timer.timeout.connect(auto_add_data)
    auto_timer.start(1500)  # Add data every 1.5 seconds
    
    # Add initial data
    message_panel.append_message("[SYSTEM] MessagePanel demo started")
    message_panel.append_serial("INIT: System ready")
    message_panel.update_displays()
    
    # Show window and start demo
    window.show()
    print("Demo window opened. You can:")
    print("1. Click 'Add Serial Data' to add IMU serial data lines")
    print("2. Click 'Add Message' to add application messages")  
    print("3. Click 'Update Displays' to refresh both text areas")
    print("4. Click 'Clear Serial/Messages/All' to clear buffers")
    print("5. Click 'Get Buffers Info' to see buffer statistics")
    print("6. Click 'Test Preferences' to test preference methods")
    print("7. Watch auto-updates every 1.5 seconds")
    print()
    print("This demonstrates that PyQt MessagePanel has identical functionality")
    print("to the tkinter version with dual text areas and buffer management.")
    print()
    
    # Run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()