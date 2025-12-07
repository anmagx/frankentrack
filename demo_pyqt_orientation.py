#!/usr/bin/env python3
"""
PyQt OrientationPanel Interactive Demo

Demonstrates the PyQt5 OrientationPanel functionality including:
- Euler angle displays (Yaw, Pitch, Roll)
- Position displays (X, Y, Z) with offset tracking
- Drift correction status indicator
- Filter selection (complementary/quaternion) 
- Reset orientation functionality
- Keyboard shortcut support

This shows that PyQt OrientationPanel has identical functionality
to the tkinter version with proper queue communication.
"""

import sys
import os
import queue
import random
import time
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit,
                             QGroupBox, QGridLayout, QFrame)
from PyQt5.QtCore import QTimer

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workers.gui_qt.panels.orientation_panel import OrientationPanelQt


class OrientationDemoApp(QMainWindow):
    """Demo application for PyQt OrientationPanel."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt OrientationPanel Demo")
        self.setGeometry(100, 100, 800, 600)
        
        # Create mock queues for communication
        self.control_queue = queue.Queue()
        
        # Message log
        self.message_log = []
        
        self.setup_ui()
        self.setup_timer()
        
        print("=== PyQt OrientationPanel Migration Demo ===")
        print()
        print("Demo window opened. You can:")
        print("1. Click 'Update Euler Angles' to simulate IMU orientation data")
        print("2. Click 'Update Position' to simulate position/translation data")
        print("3. Click 'Toggle Drift Status' to simulate drift correction state")
        print("4. Click 'Test Reset' to test orientation reset functionality")
        print("5. Click 'Test Shortcut' to set a keyboard shortcut for reset")
        print("6. Select different filters from the dropdown")
        print("7. Click 'Get/Set Preferences' to test preference management")
        print("8. Watch auto-updates with realistic IMU data every 2 seconds")
        print()
        print("This demonstrates that PyQt OrientationPanel has identical functionality")
        print("to the tkinter version with queue communication and full feature parity.")
        print()
    
    def setup_ui(self):
        """Set up the demo UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title = QLabel("PyQt OrientationPanel Demo")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title)
        
        # OrientationPanel
        orientation_frame = QGroupBox("OrientationPanel Test")
        orientation_layout = QVBoxLayout()
        orientation_frame.setLayout(orientation_layout)
        
        # Create OrientationPanel
        self.orientation_panel = OrientationPanelQt(
            orientation_frame, 
            self.control_queue, 
            self.message_callback
        )
        orientation_layout.addWidget(self.orientation_panel)
        
        main_layout.addWidget(orientation_frame)
        
        # Control buttons
        controls_frame = QGroupBox("Demo Controls")
        controls_layout = QGridLayout()
        controls_frame.setLayout(controls_layout)
        
        # Row 1: Data simulation
        controls_layout.addWidget(QPushButton("Update Euler Angles", clicked=self.test_euler), 0, 0)
        controls_layout.addWidget(QPushButton("Update Position", clicked=self.test_position), 0, 1)
        controls_layout.addWidget(QPushButton("Toggle Drift Status", clicked=self.test_drift), 0, 2)
        
        # Row 2: Functionality tests
        controls_layout.addWidget(QPushButton("Test Reset", clicked=self.test_reset), 1, 0)
        controls_layout.addWidget(QPushButton("Test Shortcut", clicked=self.test_shortcut), 1, 1)
        controls_layout.addWidget(QPushButton("Get Preferences", clicked=self.test_get_prefs), 1, 2)
        
        # Row 3: More tests
        controls_layout.addWidget(QPushButton("Set Test Preferences", clicked=self.test_set_prefs), 2, 0)
        controls_layout.addWidget(QPushButton("Reset Position Offsets", clicked=self.test_reset_offsets), 2, 1)
        controls_layout.addWidget(QPushButton("Clear Message Log", clicked=self.clear_log), 2, 2)
        
        main_layout.addWidget(controls_frame)
        
        # Message log
        log_frame = QGroupBox("Message Log")
        log_layout = QVBoxLayout()
        log_frame.setLayout(log_layout)
        
        self.message_text = QTextEdit()
        self.message_text.setMaximumHeight(150)
        self.message_text.setReadOnly(True)
        log_layout.addWidget(self.message_text)
        
        main_layout.addWidget(log_frame)
        
        # Queue monitor
        queue_frame = QGroupBox("Control Queue Monitor")
        queue_layout = QVBoxLayout()
        queue_frame.setLayout(queue_layout)
        
        self.queue_text = QTextEdit()
        self.queue_text.setMaximumHeight(100)
        self.queue_text.setReadOnly(True)
        queue_layout.addWidget(self.queue_text)
        
        main_layout.addWidget(queue_frame)
    
    def setup_timer(self):
        """Set up timer for auto-updates."""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.auto_update)
        self.update_timer.start(2000)  # Update every 2 seconds
    
    def message_callback(self, message):
        """Handle messages from OrientationPanel."""
        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        self.message_log.append(full_message)
        print(f"[DEMO] {message}")
        
        # Update message display
        self.message_text.append(full_message)
        
        # Keep log manageable
        if len(self.message_log) > 50:
            self.message_log = self.message_log[-25:]
            self.message_text.clear()
            for msg in self.message_log:
                self.message_text.append(msg)
    
    def test_euler(self):
        """Test updating Euler angles."""
        yaw = random.uniform(-180, 180)
        pitch = random.uniform(-90, 90)
        roll = random.uniform(-180, 180)
        
        self.orientation_panel.update_euler(yaw, pitch, roll)
        self.message_callback(f"Updated Euler: Yaw={yaw:.1f}\u00b0, Pitch={pitch:.1f}\u00b0, Roll={roll:.1f}\u00b0")
    
    def test_position(self):
        """Test updating position with offsets."""
        x = random.uniform(-5, 5)
        y = random.uniform(-5, 5)
        z = random.uniform(-2, 2)
        
        self.orientation_panel.update_position(x, y, z)
        self.message_callback(f"Updated Position: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    
    def test_drift(self):
        """Test toggling drift correction status."""
        active = random.choice([True, False])
        self.orientation_panel.update_drift_status(active)
        status = "Active" if active else "Inactive"
        self.message_callback(f"Drift correction: {status}")
    
    def test_reset(self):
        """Test orientation reset functionality."""
        self.orientation_panel._on_reset()
        self.message_callback("Orientation reset triggered")
    
    def test_shortcut(self):
        """Test shortcut setting."""
        test_keys = ['F5', 'KP_0', 'r', 'space']
        test_key = random.choice(test_keys)
        
        # Generate display name
        display_map = {
            'F5': 'F5',
            'KP_0': 'Numpad 0', 
            'r': 'R',
            'space': 'Space'
        }
        
        display_name = display_map.get(test_key, test_key)
        self.orientation_panel._set_reset_shortcut(test_key, display_name)
        self.message_callback(f"Set reset shortcut to: {display_name}")
    
    def test_get_prefs(self):
        """Test getting preferences."""
        prefs = self.orientation_panel.get_prefs()
        self.message_callback(f"Current preferences: {prefs}")
    
    def test_set_prefs(self):
        """Test setting preferences."""
        test_prefs = {
            'reset_shortcut': 'F7',
            'filter': random.choice(['complementary', 'quaternion'])
        }
        
        self.orientation_panel.set_prefs(test_prefs)
        self.message_callback(f"Applied test preferences: {test_prefs}")
    
    def test_reset_offsets(self):
        """Test resetting position offsets."""
        self.orientation_panel.reset_position_offsets()
        self.message_callback("Position offsets reset to zero")
    
    def clear_log(self):
        """Clear the message log."""
        self.message_log.clear()
        self.message_text.clear()
        self.message_callback("Message log cleared")
    
    def auto_update(self):
        """Automatically update with realistic IMU data."""
        # Simulate realistic IMU data patterns
        t = time.time()
        
        # Slow drift for yaw, periodic motion for pitch/roll
        yaw = (t * 0.5) % 360 - 180  # Slow rotation
        pitch = 15 * math.sin(t * 0.3)  # Gentle nodding
        roll = 8 * math.cos(t * 0.7)   # Slight tilting
        
        self.orientation_panel.update_euler(yaw, pitch, roll)
        
        # Simulate position with small random walk
        x = 2 * math.sin(t * 0.1) + random.uniform(-0.2, 0.2)
        y = 1.5 * math.cos(t * 0.15) + random.uniform(-0.2, 0.2)
        z = 0.5 * math.sin(t * 0.2) + random.uniform(-0.1, 0.1)
        
        self.orientation_panel.update_position(x, y, z)
        
        # Occasionally toggle drift status
        if random.random() < 0.05:  # 5% chance every update
            drift_active = random.choice([True, False])
            self.orientation_panel.update_drift_status(drift_active)
            status = "enabled" if drift_active else "disabled"
            print(f"[DEMO] Drift correction {status}")
        
        # Monitor control queue
        self.monitor_queue()
    
    def monitor_queue(self):
        """Monitor the control queue for commands."""
        commands = []
        try:
            while not self.control_queue.empty():
                try:
                    cmd = self.control_queue.get_nowait()
                    commands.append(str(cmd))
                except queue.Empty:
                    break
        except Exception as ex:
            commands.append(f"Queue error: {ex}")
        
        if commands:
            for cmd in commands:
                self.queue_text.append(f"[{time.strftime('%H:%M:%S')}] {cmd}")
            
            # Keep queue display manageable
            content = self.queue_text.toPlainText().split('\n')
            if len(content) > 20:
                self.queue_text.clear()
                for line in content[-10:]:
                    if line.strip():
                        self.queue_text.append(line)


def main():
    """Run the OrientationPanel demo."""
    
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt OrientationPanel Demo")
    
    demo = OrientationDemoApp()
    demo.show()
    
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())