#!/usr/bin/env python3
"""
PyQt CalibrationPanel Interactive Demo

Demonstrates the PyQt5 CalibrationPanel functionality including:
- Drift correction angle slider with quantized values (0.0-25.0°)
- Real-time drift angle display with 0.1° precision
- Gyro calibration status indicator with color changes
- Recalibrate Gyro Bias button with queue communication
- Debounced slider updates to prevent queue flooding
- Preference save/load functionality

This shows that PyQt CalibrationPanel has identical functionality
to the tkinter version with proper slider behavior and queue communication.
"""

import sys
import os
import queue
import random
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit,
                             QGroupBox, QGridLayout, QFrame, QSlider)
from PyQt5.QtCore import QTimer, Qt

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workers.gui_qt.panels.calibration_panel import CalibrationPanelQt


class CalibrationDemoApp(QMainWindow):
    """Demo application for PyQt CalibrationPanel."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt CalibrationPanel Demo")
        self.setGeometry(100, 100, 900, 700)
        
        # Create mock queue for communication
        self.control_queue = queue.Queue()
        
        # Message log
        self.message_log = []
        
        self.setup_ui()
        self.setup_timer()
        
        print("=== PyQt CalibrationPanel Migration Demo ===")
        print()
        print("Demo window opened. You can:")
        print("1. Move the 'Drift Correction Angle' slider to test quantized values")
        print("2. Click 'Test Random Drift Angle' to set programmatic values")
        print("3. Click 'Toggle Calibration Status' to test status indicator colors")
        print("4. Click 'Test Recalibrate' to trigger gyro bias recalibration")
        print("5. Click 'Get/Set Preferences' to test preference management")
        print("6. Click 'Test Slider Boundaries' to test 0.0-25.0° range limits")
        print("7. Watch auto-updates with simulated calibration state changes")
        print("8. Monitor the Control Queue to see debounced slider updates")
        print()
        print("This demonstrates that PyQt CalibrationPanel has identical functionality")
        print("to the tkinter version with proper slider quantization and debouncing.")
        print()
    
    def setup_ui(self):
        """Set up the demo UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title = QLabel("PyQt CalibrationPanel Demo")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title)
        
        # CalibrationPanel
        calibration_frame = QGroupBox("CalibrationPanel Test")
        calibration_layout = QVBoxLayout()
        calibration_frame.setLayout(calibration_layout)
        
        # Create CalibrationPanel
        self.calibration_panel = CalibrationPanelQt(
            calibration_frame, 
            self.control_queue, 
            self.message_callback
        )
        calibration_layout.addWidget(self.calibration_panel)
        
        main_layout.addWidget(calibration_frame)
        
        # Control buttons
        controls_frame = QGroupBox("Demo Controls")
        controls_layout = QGridLayout()
        controls_frame.setLayout(controls_layout)
        
        # Row 1: Basic functionality tests
        controls_layout.addWidget(QPushButton("Test Random Drift Angle", clicked=self.test_drift_angle), 0, 0)
        controls_layout.addWidget(QPushButton("Toggle Calibration Status", clicked=self.test_calibration_status), 0, 1)
        controls_layout.addWidget(QPushButton("Test Recalibrate", clicked=self.test_recalibrate), 0, 2)
        
        # Row 2: Advanced tests
        controls_layout.addWidget(QPushButton("Get Preferences", clicked=self.test_get_prefs), 1, 0)
        controls_layout.addWidget(QPushButton("Set Test Preferences", clicked=self.test_set_prefs), 1, 1)
        controls_layout.addWidget(QPushButton("Test Slider Boundaries", clicked=self.test_boundaries), 1, 2)
        
        # Row 3: Utility
        controls_layout.addWidget(QPushButton("Clear Message Log", clicked=self.clear_log), 2, 0)
        controls_layout.addWidget(QPushButton("Show Current Values", clicked=self.show_current_values), 2, 1)
        controls_layout.addWidget(QPushButton("Simulate Calibration Cycle", clicked=self.simulate_calibration), 2, 2)
        
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
        
        # Control queue monitor
        queue_frame = QGroupBox("Control Queue Monitor (Debounced Updates)")
        queue_layout = QVBoxLayout()
        queue_frame.setLayout(queue_layout)
        
        self.queue_text = QTextEdit()
        self.queue_text.setMaximumHeight(120)
        self.queue_text.setReadOnly(True)
        queue_layout.addWidget(self.queue_text)
        
        main_layout.addWidget(queue_frame)
    
    def setup_timer(self):
        """Set up timer for auto-updates."""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.auto_update)
        self.update_timer.start(3000)  # Update every 3 seconds
    
    def message_callback(self, message):
        """Handle messages from CalibrationPanel."""
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
    
    def test_drift_angle(self):
        """Test setting random drift angles."""
        test_angles = [0.0, 2.5, 5.0, 7.3, 12.5, 15.8, 20.0, 25.0]
        angle = random.choice(test_angles)
        
        self.calibration_panel.set_drift_angle(angle)
        actual_angle = self.calibration_panel.get_drift_angle()
        
        self.message_callback(f"Set drift angle to {angle:.1f}°, got {actual_angle:.1f}°")
    
    def test_calibration_status(self):
        """Test toggling calibration status."""
        calibrated = random.choice([True, False])
        self.calibration_panel.update_calibration_status(calibrated)
        
        status = "Calibrated" if calibrated else "Not calibrated"
        color = "blue" if calibrated else "red"
        self.message_callback(f"Gyro status: {status} (color: {color})")
    
    def test_recalibrate(self):
        """Test recalibrate button."""
        self.calibration_panel._on_recalibrate()
        self.message_callback("Recalibrate gyro bias button triggered")
    
    def test_get_prefs(self):
        """Test getting preferences."""
        prefs = self.calibration_panel.get_prefs()
        self.message_callback(f"Current preferences: {prefs}")
    
    def test_set_prefs(self):
        """Test setting preferences."""
        test_angles = ['5.0', '10.5', '15.0', '22.3']
        test_angle = random.choice(test_angles)
        
        test_prefs = {
            'drift_angle': test_angle
        }
        
        self.calibration_panel.set_prefs(test_prefs)
        self.message_callback(f"Applied test preferences: {test_prefs}")
    
    def test_boundaries(self):
        """Test slider boundary values and clamping."""
        test_values = [-5.0, 0.0, 12.5, 25.0, 30.0, 50.0]
        
        for value in test_values:
            self.calibration_panel.set_drift_angle(value)
            actual = self.calibration_panel.get_drift_angle()
            expected = max(0.0, min(25.0, value))
            
            if actual == expected:
                result = "✓"
            else:
                result = "✗"
            
            self.message_callback(f"{result} Boundary test: {value:.1f}° → {actual:.1f}° (expected {expected:.1f}°)")
    
    def clear_log(self):
        """Clear the message log."""
        self.message_log.clear()
        self.message_text.clear()
        self.message_callback("Message log cleared")
    
    def show_current_values(self):
        """Show current drift angle and calibration status."""
        angle = self.calibration_panel.get_drift_angle()
        prefs = self.calibration_panel.get_prefs()
        
        self.message_callback(f"Current drift angle: {angle:.1f}°")
        self.message_callback(f"Current preferences: {prefs}")
    
    def simulate_calibration(self):
        """Simulate a full calibration cycle."""
        self.message_callback("Starting calibration simulation...")
        
        # Start as not calibrated
        self.calibration_panel.update_calibration_status(False)
        self.message_callback("Step 1: Gyro not calibrated (red)")
        
        # Simulate calibration in progress (you could add this state if needed)
        QTimer.singleShot(1000, lambda: self.message_callback("Step 2: Calibration in progress..."))
        
        # Complete calibration
        QTimer.singleShot(2000, lambda: self.calibration_panel.update_calibration_status(True))
        QTimer.singleShot(2000, lambda: self.message_callback("Step 3: Gyro calibrated (blue)"))
    
    def auto_update(self):
        """Automatically update with random calibration changes."""
        try:
            # Occasionally change calibration status
            if random.random() < 0.3:  # 30% chance
                calibrated = random.choice([True, False])
                self.calibration_panel.update_calibration_status(calibrated)
                status = "calibrated" if calibrated else "not calibrated"
                print(f"[DEMO] Auto-update: Gyro {status}")
            
            # Occasionally adjust drift angle slightly
            if random.random() < 0.2:  # 20% chance
                current_angle = self.calibration_panel.get_drift_angle()
                # Small random adjustment
                adjustment = random.uniform(-1.0, 1.0)
                new_angle = max(0.0, min(25.0, current_angle + adjustment))
                self.calibration_panel.set_drift_angle(new_angle)
                print(f"[DEMO] Auto-update: Drift angle adjusted to {new_angle:.1f}°")
            
            # Monitor control queue
            self.monitor_queue()
            
        except Exception as ex:
            self.message_callback(f"Auto-update error: {ex}")
    
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
            if len(content) > 15:
                self.queue_text.clear()
                for line in content[-8:]:
                    if line.strip():
                        self.queue_text.append(line)


def main():
    """Run the CalibrationPanel demo."""
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt CalibrationPanel Demo")
    
    demo = CalibrationDemoApp()
    demo.show()
    
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())