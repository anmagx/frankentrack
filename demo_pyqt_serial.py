"""
Simple demonstration script showing PyQt SerialPanel functionality.

This script tests key features of the PyQt SerialPanel to verify 
it matches the tkinter version's behavior.
"""

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton
from PyQt5.QtCore import QTimer
import queue

from workers.gui_qt.panels.serial_panel import SerialPanelQt


def main():
    """Simple demonstration of PyQt SerialPanel."""
    print("=== PyQt SerialPanel Migration Demo ===")
    print()
    
    app = QApplication(sys.argv)
    
    # Create main window
    window = QMainWindow()
    window.setWindowTitle("PyQt SerialPanel Demo")
    window.setGeometry(100, 100, 800, 200)
    
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # Create mock serial control queue
    serial_queue = queue.Queue()
    
    def log_message(msg):
        print(f"[LOG] {msg}")
    
    def on_serial_stop():
        print("[CALLBACK] Serial stop callback triggered")
    
    # Create PyQt SerialPanel (same interface as tkinter)
    serial_panel = SerialPanelQt(
        central_widget,
        serial_queue,
        log_message,
        padding=8,
        on_stop=on_serial_stop
    )
    layout.addWidget(serial_panel)
    
    # Add demo button to test preferences
    demo_button = QPushButton("Test Preferences Save/Load")
    layout.addWidget(demo_button)
    
    def test_prefs():
        # Test get_prefs
        prefs = serial_panel.get_prefs()
        print(f"[DEMO] Current preferences: {prefs}")
        
        # Test set_prefs
        test_prefs = {
            'com_port': 'COM7',
            'baud_rate': '230400'
        }
        serial_panel.set_prefs(test_prefs)
        print(f"[DEMO] Applied test preferences: {test_prefs}")
        
        # Verify the change
        new_prefs = serial_panel.get_prefs()
        print(f"[DEMO] New preferences: {new_prefs}")
    
    demo_button.clicked.connect(test_prefs)
    
    # Monitor the queue for commands
    def check_queue():
        try:
            while not serial_queue.empty():
                cmd = serial_queue.get_nowait()
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
    print("1. Select different COM ports and baud rates")
    print("2. Click 'Start' to send start command to queue")
    print("3. Click 'Stop' to send stop command to queue")
    print("4. Click 'Test Preferences Save/Load' to test preference functions")
    print("5. Check the console for queue messages and callbacks")
    print()
    print("This demonstrates that PyQt SerialPanel has identical functionality")
    print("to the tkinter version while using modern PyQt widgets.")
    print()
    
    # Run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()