"""
PyQt Camera Panel Demo

Interactive demonstration of the CameraPanelQt implementation showcasing:
- Camera preview toggle and image display
- Camera enumeration in background thread
- Backend selection (OpenCV vs pseyepy)
- FPS and resolution parameter controls
- Options dialog for threshold/exposure/gain
- Position tracking toggle with control state management
- Preference save/load functionality

Usage:
    python demo_pyqt_camera.py
"""

import sys
import queue
import time
import random
import threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFrame, QSizePolicy
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from workers.gui_qt.panels.camera_panel import CameraPanelQt
from util.error_utils import safe_queue_put


class CameraDemoApp(QMainWindow):
    """Demo application for CameraPanelQt testing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("frankentrack - PyQt CameraPanel Demo")
        self.setGeometry(100, 100, 800, 700)
        
        # Create mock queues for testing
        self.camera_control_queue = queue.Queue()
        self.message_queue = queue.Queue()
        
        # Auto-test flags
        self.auto_test_running = False
        self.test_timer = QTimer()
        self.test_timer.timeout.connect(self.auto_test_cycle)
        
        self.setup_ui()
        self.setup_queue_monitoring()
        
        # Start with some test data
        QTimer.singleShot(1000, self.initialize_demo)
        
    def setup_ui(self):
        """Setup the demo UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(8)
        
        # Title
        title = QLabel("CameraPanel PyQt Demo")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(title)
        
        # Camera panel
        self.camera_panel = CameraPanelQt(
            self.camera_control_queue,
            self.message_queue
        )
        layout.addWidget(self.camera_panel)
        
        # Demo controls
        self.setup_demo_controls(layout)
        
        # Queue monitor
        self.setup_queue_monitor(layout)
    
    def setup_demo_controls(self, layout):
        """Setup demo control buttons."""
        controls_frame = QFrame()
        controls_layout = QVBoxLayout(controls_frame)
        
        # Row 1: Basic controls
        row1 = QFrame()
        row1_layout = QHBoxLayout(row1)
        
        self.toggle_preview_btn = QPushButton("Toggle Preview")
        self.toggle_preview_btn.clicked.connect(self.test_preview_toggle)
        row1_layout.addWidget(self.toggle_preview_btn)
        
        self.toggle_tracking_btn = QPushButton("Toggle Tracking")
        self.toggle_tracking_btn.clicked.connect(self.test_tracking_toggle)
        row1_layout.addWidget(self.toggle_tracking_btn)
        
        self.enumerate_btn = QPushButton("Enumerate Cameras")
        self.enumerate_btn.clicked.connect(self.test_enumerate)
        row1_layout.addWidget(self.enumerate_btn)
        
        self.options_btn = QPushButton("Open Options")
        self.options_btn.clicked.connect(self.test_options_dialog)
        row1_layout.addWidget(self.options_btn)
        
        row1_layout.addStretch()
        controls_layout.addWidget(row1)
        
        # Row 2: Parameter controls
        row2 = QFrame()
        row2_layout = QHBoxLayout(row2)
        
        self.test_params_btn = QPushButton("Test Parameters")
        self.test_params_btn.clicked.connect(self.test_parameters)
        row2_layout.addWidget(self.test_params_btn)
        
        self.test_backend_btn = QPushButton("Test Backend")
        self.test_backend_btn.clicked.connect(self.test_backend_switch)
        row2_layout.addWidget(self.test_backend_btn)
        
        self.test_prefs_btn = QPushButton("Test Preferences")
        self.test_prefs_btn.clicked.connect(self.test_preferences)
        row2_layout.addWidget(self.test_prefs_btn)
        
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        row2_layout.addWidget(self.clear_log_btn)
        
        row2_layout.addStretch()
        controls_layout.addWidget(row2)
        
        # Row 3: Auto-test controls
        row3 = QFrame()
        row3_layout = QHBoxLayout(row3)
        
        self.auto_test_btn = QPushButton("Start Auto-Test")
        self.auto_test_btn.clicked.connect(self.toggle_auto_test)
        row3_layout.addWidget(self.auto_test_btn)
        
        self.simulate_cameras_btn = QPushButton("Simulate Cameras")
        self.simulate_cameras_btn.clicked.connect(self.simulate_camera_detection)
        row3_layout.addWidget(self.simulate_cameras_btn)
        
        self.simulate_image_btn = QPushButton("Simulate Image")
        self.simulate_image_btn.clicked.connect(self.simulate_image_update)
        row3_layout.addWidget(self.simulate_image_btn)
        
        row3_layout.addStretch()
        controls_layout.addWidget(row3)
        
        layout.addWidget(controls_frame)
    
    def setup_queue_monitor(self, layout):
        """Setup queue monitoring display."""
        monitor_frame = QFrame()
        monitor_frame.setFrameStyle(QFrame.Box)
        monitor_layout = QVBoxLayout(monitor_frame)
        
        monitor_layout.addWidget(QLabel("Queue Activity & Demo Log:"))
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)
        self.log_text.setReadOnly(True)
        font = QFont("Courier", 9)
        self.log_text.setFont(font)
        monitor_layout.addWidget(self.log_text)
        
        layout.addWidget(monitor_frame)
    
    def setup_queue_monitoring(self):
        """Setup queue monitoring timer."""
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.monitor_queues)
        self.monitor_timer.start(100)  # Check every 100ms
    
    def monitor_queues(self):
        """Monitor queue activity and display messages."""
        # Monitor camera control queue
        while not self.camera_control_queue.empty():
            try:
                cmd = self.camera_control_queue.get_nowait()
                self.log(f"Camera Control: {cmd}")
            except queue.Empty:
                break
        
        # Monitor message queue
        while not self.message_queue.empty():
            try:
                msg = self.message_queue.get_nowait()
                self.log(f"Message: {msg}")
            except queue.Empty:
                break
    
    def log(self, message):
        """Add a message to the log display."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Clear the log display."""
        self.log_text.clear()
        self.log("Log cleared")
    
    def initialize_demo(self):
        """Initialize the demo with some test data."""
        self.log("CameraPanel Demo initialized")
        self.log("Use buttons to test different features:")
        self.log("- Toggle Preview: Enable/disable camera preview")
        self.log("- Toggle Tracking: Start/stop position tracking")  
        self.log("- Enumerate Cameras: Test camera detection")
        self.log("- Open Options: Test threshold/exposure/gain dialog")
        self.log("- Auto-Test: Automated feature cycling")
        
        # Set some initial camera list
        initial_cameras = ["Camera 0", "Camera 1", "Camera 3"]
        self.camera_panel.set_cameras(initial_cameras)
        self.log(f"Set initial cameras: {initial_cameras}")
    
    def test_preview_toggle(self):
        """Test preview toggle functionality."""
        self.log("Testing preview toggle...")
        self.camera_panel.toggle_preview()
        enabled = self.camera_panel.preview_enabled
        button_text = self.camera_panel.preview_btn.text()
        self.log(f"Preview: enabled={enabled}, button='{button_text}'")
    
    def test_tracking_toggle(self):
        """Test position tracking toggle."""
        self.log("Testing position tracking toggle...")
        self.camera_panel.toggle_position_tracking()
        enabled = self.camera_panel.pos_track_enabled
        button_text = self.camera_panel.pos_btn.text()
        self.log(f"Tracking: enabled={enabled}, button='{button_text}'")
        
        # Check control state
        if enabled:
            camera_enabled = self.camera_panel.camera_cb.isEnabled()
            fps_enabled = self.camera_panel.fps_cb.isEnabled()
            self.log(f"Controls disabled during tracking: camera={not camera_enabled}, fps={not fps_enabled}")
    
    def test_enumerate(self):
        """Test camera enumeration (simulated)."""
        self.log("Testing camera enumeration...")
        self.camera_panel._on_enumerate_clicked()
        self.log("Enumeration started (this simulates the real enumeration process)")
    
    def test_options_dialog(self):
        """Test opening the options dialog."""
        self.log("Testing options dialog...")
        try:
            self.camera_panel._open_options_dialog()
            self.log("Options dialog opened successfully")
        except Exception as e:
            self.log(f"Options dialog test: {e}")
    
    def test_parameters(self):
        """Test FPS and resolution parameter changes."""
        self.log("Testing camera parameters...")
        
        # Test FPS changes
        fps_options = ['30', '60', '90']
        for fps in fps_options:
            self.camera_panel.fps_cb.setCurrentText(fps)
            current = self.camera_panel.fps_cb.currentText()
            self.log(f"FPS set to: {current}")
        
        # Test resolution changes
        res_options = ['640x480', '1280x720', '1920x1080']
        for res in res_options:
            self.camera_panel.res_cb.setCurrentText(res)
            current = self.camera_panel.res_cb.currentText()
            self.log(f"Resolution set to: {current}")
    
    def test_backend_switch(self):
        """Test backend switching."""
        self.log("Testing backend switching...")
        
        # Get current backend
        current = self.camera_panel.backend_cb.currentText()
        self.log(f"Current backend: {current}")
        
        # Switch to other backend
        if "openCV" in current:
            self.camera_panel.backend_cb.setCurrentText('pseyepy (PS3Eye)')
            new_backend = self.camera_panel.backend_cb.currentText()
            self.log(f"Switched to: {new_backend}")
        else:
            self.camera_panel.backend_cb.setCurrentText('openCV')
            new_backend = self.camera_panel.backend_cb.currentText()
            self.log(f"Switched to: {new_backend}")
    
    def test_preferences(self):
        """Test preference save/load functionality."""
        self.log("Testing preferences...")
        
        # Get current preferences
        prefs = self.camera_panel.get_prefs()
        self.log(f"Current prefs keys: {list(prefs.keys())}")
        
        # Test setting new preferences
        test_prefs = {
            'camera': 'Camera 2',
            'fps': '60',
            'resolution': '1280x720',
            'thresh': '128',
            'exposure': '100',
            'gain': '32',
            'backend': 'pseyepy (PS3Eye)',
            'cameras': 'Camera 0,Camera 1,Camera 2',
            'cameras_opencv': 'Camera 0,Camera 1',
            'cameras_pseyepy': 'Camera 0'
        }
        
        self.camera_panel.set_prefs(test_prefs)
        self.log("Applied test preferences")
        
        # Verify applied preferences
        new_prefs = self.camera_panel.get_prefs()
        self.log(f"New camera: {new_prefs.get('camera')}")
        self.log(f"New backend: {new_prefs.get('backend')}")
    
    def simulate_camera_detection(self):
        """Simulate camera enumeration results."""
        self.log("Simulating camera detection...")
        
        # Simulate different camera scenarios
        scenarios = [
            ["Camera 0"],
            ["Camera 0", "Camera 1"],
            ["Camera 0", "Camera 1", "Camera 2", "Camera 5"],
            ["Camera 0", "Camera 3", "Camera 7", "Camera 9"]
        ]
        
        cameras = random.choice(scenarios)
        self.camera_panel.set_cameras(cameras)
        self.log(f"Simulated cameras found: {cameras}")
        
        # Update the cached lists for demonstration
        backend = self.camera_panel.backend_cb.currentText()
        backend_key = 'pseyepy' if 'pseyepy' in backend.lower() else 'openCV'
        self.camera_panel._cached_cameras[backend_key] = list(cameras)
        self.log(f"Updated {backend_key} cache: {cameras}")
    
    def simulate_image_update(self):
        """Simulate image preview update (would normally come from camera worker)."""
        self.log("Image preview simulation...")
        self.log("Note: Real image updates require JPEG data from camera worker")
        self.log("Preview display is ready to handle update_preview(jpeg_data) calls")
        
        # Test preview state display
        if self.camera_panel.preview_enabled:
            self.log("Preview is enabled - ready for image data")
        else:
            self.log("Preview is disabled - enable preview to see images")
    
    def toggle_auto_test(self):
        """Toggle automatic testing cycle."""
        if self.auto_test_running:
            self.test_timer.stop()
            self.auto_test_running = False
            self.auto_test_btn.setText("Start Auto-Test")
            self.log("Auto-test stopped")
        else:
            self.test_timer.start(3000)  # Every 3 seconds
            self.auto_test_running = True
            self.auto_test_btn.setText("Stop Auto-Test")
            self.log("Auto-test started (3-second cycles)")
    
    def auto_test_cycle(self):
        """Automatic test cycle that rotates through different features."""
        if not self.auto_test_running:
            return
        
        test_actions = [
            ("Toggle Preview", self.test_preview_toggle),
            ("Test Parameters", self.test_parameters),
            ("Switch Backend", self.test_backend_switch),
            ("Simulate Cameras", self.simulate_camera_detection),
            ("Toggle Tracking", self.test_tracking_toggle),
            ("Test Preferences", self.test_preferences)
        ]
        
        action_name, action_func = random.choice(test_actions)
        self.log(f"Auto-test: {action_name}")
        action_func()


def main():
    """Run the CameraPanel demo."""
    print("Starting PyQt CameraPanel Demo...")
    print("This demonstrates the CameraPanelQt implementation with:")
    print("- Camera preview toggle and image display")
    print("- Camera enumeration simulation")  
    print("- Backend selection (OpenCV vs pseyepy)")
    print("- Parameter controls (FPS, resolution)")
    print("- Options dialog for threshold/exposure/gain")
    print("- Position tracking with control state management")
    print("- Preference save/load functionality")
    print("- Queue monitoring for worker communication")
    print()
    
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("frankentrack CameraPanel Demo")
    app.setOrganizationName("frankentrack")
    
    demo = CameraDemoApp()
    demo.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()