"""
PyQt test harness for GUI components (mirrors tkinter test_panels.py).

This allows testing PyQt panel implementations in isolation without affecting
the production gui_wrk.py or gui_wrk_qt.py.

Usage:
    python -m workers.gui_qt.test_panels_qt
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QTextEdit, QFrame, QSizePolicy)
from PyQt5.QtCore import QTimer, pyqtSlot
from PyQt5.QtGui import QFont
import queue
import time

from workers.gui_qt.panels.serial_panel import SerialPanelQt
from workers.gui_qt.panels.status_bar import StatusBarQt
from workers.gui_qt.panels.network_panel import NetworkPanelQt
from workers.gui_qt.panels.message_panel import MessagePanelQt
from workers.gui_qt.panels.orientation_panel import OrientationPanelQt
from workers.gui_qt.panels.calibration_panel import CalibrationPanelQt
from workers.gui_qt.panels.diagnostics_panel import DiagnosticsPanelQt


class TestAppQt(QMainWindow):
    """PyQt test application (mirrors tkinter TestApp)."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("frankentrack - PyQt Panel Test Harness")
        self.setGeometry(100, 100, 900, 700)
        
        # Create mock queues for testing (same as tkinter version)
        self.serial_control_queue = queue.Queue()
        self.fusion_control_queue = queue.Queue()
        self.udp_control_queue = queue.Queue()
        self.message_queue = queue.Queue()
        
        self.setup_ui()
        self.setup_test_panels()
        
        # Start queue monitoring (same as tkinter version)
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.monitor_queues)
        self.queue_timer.start(100)  # Check every 100ms
        
        # Auto-generate test data after startup
        QTimer.singleShot(1000, self.generate_test_data)
        
    def setup_ui(self):
        """Setup the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Panel selector (same as tkinter version)
        selector_frame = QFrame()
        selector_layout = QHBoxLayout(selector_frame)
        
        selector_layout.addWidget(QLabel("Panel Under Test:"))
        
        self.panel_selector = QComboBox()
        self.panel_selector.addItems(["SerialPanel", "StatusBar", "NetworkPanel", "MessagePanel", "OrientationPanel", "CalibrationPanel", "DiagnosticsPanel", "All"])
        self.panel_selector.currentTextChanged.connect(self.on_panel_changed)
        selector_layout.addWidget(self.panel_selector)
        
        selector_layout.addStretch()  # Push everything left
        
        layout.addWidget(selector_frame)
        
        # Test log area (same as tkinter version)
        log_frame = QFrame()
        log_frame.setFrameStyle(QFrame.Box)
        log_layout = QVBoxLayout(log_frame)
        
        log_layout.addWidget(QLabel("Test Log:"))
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        font = QFont("Courier", 9)
        self.log_text.setFont(font)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_frame)
        
        # Panel container (same concept as tkinter version)
        self.panel_container = QFrame()
        self.panel_container.setFrameStyle(QFrame.Box)
        self.panel_layout = QVBoxLayout(self.panel_container)
        
        layout.addWidget(self.panel_container)
        
        # Control buttons
        self.setup_controls()
    
    def setup_controls(self):
        """Setup test control buttons."""
        controls_frame = QFrame()
        controls_layout = QVBoxLayout(controls_frame)
        
        # SerialPanel controls
        serial_row = QFrame()
        serial_layout = QHBoxLayout(serial_row)
        
        serial_layout.addWidget(QLabel("SerialPanel:"))
        
        get_prefs_btn = QPushButton("Test Get Prefs")
        get_prefs_btn.clicked.connect(self.test_get_prefs)
        serial_layout.addWidget(get_prefs_btn)
        
        set_prefs_btn = QPushButton("Test Set Prefs")
        set_prefs_btn.clicked.connect(self.test_set_prefs)
        serial_layout.addWidget(set_prefs_btn)
        
        show_queue_btn = QPushButton("Show Queue")
        show_queue_btn.clicked.connect(self.show_queue_contents)
        serial_layout.addWidget(show_queue_btn)
        
        serial_layout.addStretch()
        controls_layout.addWidget(serial_row)
        
        # StatusBar controls
        status_row = QFrame()
        status_layout = QHBoxLayout(status_row)
        
        status_layout.addWidget(QLabel("StatusBar:"))
        
        update_rates_btn = QPushButton("Update Rates")
        update_rates_btn.clicked.connect(self.test_update_rates)
        status_layout.addWidget(update_rates_btn)
        
        update_device_btn = QPushButton("Toggle Device Status")
        update_device_btn.clicked.connect(self.test_device_status)
        status_layout.addWidget(update_device_btn)
        
        reset_status_btn = QPushButton("Reset StatusBar")
        reset_status_btn.clicked.connect(self.test_reset_status)
        status_layout.addWidget(reset_status_btn)
        
        status_layout.addStretch()
        controls_layout.addWidget(status_row)
        
        # NetworkPanel controls
        network_row = QFrame()
        network_layout = QHBoxLayout(network_row)
        
        network_layout.addWidget(QLabel("NetworkPanel:"))
        
        toggle_udp_btn = QPushButton("Toggle UDP")
        toggle_udp_btn.clicked.connect(self.test_toggle_udp)
        network_layout.addWidget(toggle_udp_btn)
        
        set_config_btn = QPushButton("Set Test Config")
        set_config_btn.clicked.connect(self.test_set_udp_config)
        network_layout.addWidget(set_config_btn)
        
        get_config_btn = QPushButton("Get Config")
        get_config_btn.clicked.connect(self.test_get_udp_config)
        network_layout.addWidget(get_config_btn)
        
        network_prefs_btn = QPushButton("Test Network Prefs")
        network_prefs_btn.clicked.connect(self.test_network_prefs)
        network_layout.addWidget(network_prefs_btn)
        
        network_layout.addStretch()
        controls_layout.addWidget(network_row)
        
        # MessagePanel controls
        message_row = QFrame()
        message_layout = QHBoxLayout(message_row)
        
        message_layout.addWidget(QLabel("MessagePanel:"))
        
        add_serial_btn = QPushButton("Add Serial Data")
        add_serial_btn.clicked.connect(self.test_add_serial)
        message_layout.addWidget(add_serial_btn)
        
        add_message_btn = QPushButton("Add Message")
        add_message_btn.clicked.connect(self.test_add_message)
        message_layout.addWidget(add_message_btn)
        
        update_displays_btn = QPushButton("Update Displays")
        update_displays_btn.clicked.connect(self.test_update_displays)
        message_layout.addWidget(update_displays_btn)
        
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self.test_clear_all)
        message_layout.addWidget(clear_all_btn)
        
        get_buffers_btn = QPushButton("Get Buffers")
        get_buffers_btn.clicked.connect(self.test_get_buffers)
        message_layout.addWidget(get_buffers_btn)
        
        message_layout.addStretch()
        controls_layout.addWidget(message_row)
        
        # DiagnosticsPanel controls
        diagnostics_row = QFrame()
        diagnostics_layout = QHBoxLayout(diagnostics_row)
        
        diagnostics_layout.addWidget(QLabel("DiagnosticsPanel:"))
        
        toggle_diag_btn = QPushButton("Toggle Mode")
        toggle_diag_btn.clicked.connect(self.test_diagnostics_toggle)
        diagnostics_layout.addWidget(toggle_diag_btn)
        
        update_diag_btn = QPushButton("Update Data")
        update_diag_btn.clicked.connect(self.test_diagnostics_data_update)
        diagnostics_layout.addWidget(update_diag_btn)
        
        clear_diag_btn = QPushButton("Clear Data")
        clear_diag_btn.clicked.connect(self.test_diagnostics_clear_data)
        diagnostics_layout.addWidget(clear_diag_btn)
        
        diag_prefs_btn = QPushButton("Test Prefs")
        diag_prefs_btn.clicked.connect(self.test_diagnostics_prefs)
        diagnostics_layout.addWidget(diag_prefs_btn)
        
        diagnostics_layout.addStretch()
        controls_layout.addWidget(diagnostics_row)
        
        # General controls
        general_row = QFrame()
        general_layout = QHBoxLayout(general_row)
        
        general_layout.addWidget(QLabel("General:"))
        
        clear_log_btn = QPushButton("Clear Test Log")
        clear_log_btn.clicked.connect(self.clear_log)
        general_layout.addWidget(clear_log_btn)
        
        generate_data_btn = QPushButton("Generate Test Data")
        generate_data_btn.clicked.connect(self.generate_test_data)
        general_layout.addWidget(generate_data_btn)
        
        general_layout.addStretch()
        controls_layout.addWidget(general_row)
        
        self.centralWidget().layout().addWidget(controls_frame)
    
    def setup_test_panels(self):
        """Setup the panels being tested."""
        # Create SerialPanel (same interface as tkinter version)
        self.serial_panel = SerialPanelQt(
            self.panel_container,
            self.serial_control_queue,
            self.log_message,
            padding=8,
            on_stop=self.on_serial_stop
        )
        
        # Create StatusBar (same interface as tkinter version)
        self.status_bar = StatusBarQt(
            self.panel_container,
            relief="sunken"
        )
        
        # Create NetworkPanel (same interface as tkinter version)
        self.network_panel = NetworkPanelQt(
            self.panel_container,
            self.udp_control_queue,
            self.log_message,
            padding=6
        )
        
        # Create MessagePanel (same interface as tkinter version)
        self.message_panel = MessagePanelQt(
            self.panel_container,
            serial_height=8,
            message_height=8,
            max_serial_lines=200,
            max_message_lines=100,
            padding=6
        )
        
        # Create OrientationPanel (same interface as tkinter version)
        self.orientation_panel = OrientationPanelQt(
            self.panel_container,
            self.fusion_control_queue,
            self.log_message,
            padding=6
        )
        
        # Create CalibrationPanel (same interface as tkinter version)
        self.calibration_panel = CalibrationPanelQt(
            self.panel_container,
            self.fusion_control_queue,
            self.log_message,
            padding=6
        )
        
        # Create DiagnosticsPanel
        self.diagnostics_panel = DiagnosticsPanelQt(
            self.panel_container,
            None,  # No control queue for diagnostics panel
            self.log_message,
            padding=6
        )
        
        # Show SerialPanel by default
        self.show_panel("SerialPanel")
    
    def show_panel(self, panel_name):
        """Show the selected panel."""
        # Clear current layout
        while self.panel_layout.count():
            child = self.panel_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Show selected panel(s)
        if panel_name == "SerialPanel":
            self.panel_layout.addWidget(self.serial_panel)
        elif panel_name == "StatusBar":
            self.panel_layout.addWidget(self.status_bar)
        elif panel_name == "NetworkPanel":
            self.panel_layout.addWidget(self.network_panel)
        elif panel_name == "MessagePanel":
            self.panel_layout.addWidget(self.message_panel)
        elif panel_name == "OrientationPanel":
            self.panel_layout.addWidget(self.orientation_panel)
        elif panel_name == "CalibrationPanel":
            self.panel_layout.addWidget(self.calibration_panel)
        elif panel_name == "DiagnosticsPanel":
            self.panel_layout.addWidget(self.diagnostics_panel)
        elif panel_name == "All":
            self.panel_layout.addWidget(self.serial_panel)
            self.panel_layout.addWidget(self.status_bar)
            self.panel_layout.addWidget(self.network_panel)
            self.panel_layout.addWidget(self.message_panel)
            self.panel_layout.addWidget(self.orientation_panel)
            self.panel_layout.addWidget(self.calibration_panel)
            self.panel_layout.addWidget(self.diagnostics_panel)
        
        self.panel_layout.addStretch()  # Push panels to top
    
    @pyqtSlot(str)
    def on_panel_changed(self, panel_name):
        """Handle panel selection change."""
        self.show_panel(panel_name)
        self.log_message(f"Switched to: {panel_name}")
    
    def log_message(self, msg):
        """Append a message to the test log display."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
    
    def clear_log(self):
        """Clear the test log display."""
        self.log_text.clear()
    
    def test_get_prefs(self):
        """Test getting preferences from SerialPanel."""
        prefs = self.serial_panel.get_prefs()
        self.log_message(f"SerialPanel Get Prefs: {prefs}")
    
    def test_set_prefs(self):
        """Test setting preferences on SerialPanel."""
        test_prefs = {
            'com_port': 'COM3',
            'baud_rate': '115200'
        }
        self.serial_panel.set_prefs(test_prefs)
        self.log_message(f"SerialPanel Set Prefs: {test_prefs}")
    
    def show_queue_contents(self):
        """Display contents of the serial control queue."""
        contents = []
        temp_queue = queue.Queue()
        
        # Drain queue
        while not self.serial_control_queue.empty():
            try:
                item = self.serial_control_queue.get_nowait()
                contents.append(item)
                temp_queue.put(item)
            except queue.Empty:
                break
        
        # Restore queue
        while not temp_queue.empty():
            try:
                self.serial_control_queue.put(temp_queue.get_nowait())
            except queue.Empty:
                break
        
        if contents:
            self.log_message(f"Queue Contents ({len(contents)} items):")
            for i, item in enumerate(contents, 1):
                self.log_message(f"  {i}. {item}")
        else:
            self.log_message("Queue is empty")
    
    def generate_test_data(self):
        """Generate test data."""
        self.log_message(f"Test data generated at {time.strftime('%H:%M:%S')}")
        self.log_message("PyQt SerialPanel ready for testing")
        self.log_message("PyQt StatusBar ready for testing")
        self.log_message("PyQt NetworkPanel ready for testing")
        self.log_message("PyQt MessagePanel ready for testing")
        self.log_message("PyQt DiagnosticsPanel ready for testing")
        
        # Add some initial data to MessagePanel for demo
        self.message_panel.append_serial("SERIAL: yaw=0.0, pitch=0.0, roll=0.0")
        self.message_panel.append_message("System initialized")
        self.message_panel.update_displays()
        
        # Add some test data to diagnostics panel
        try:
            # Enable diagnostics and add a few data points
            self.diagnostics_panel.enable_checkbox.setChecked(True)
            import random
            for i in range(5):
                yaw = random.uniform(-30, 30)
                pitch = random.uniform(-15, 15) 
                roll = random.uniform(-20, 20)
                self.diagnostics_panel.update_euler(yaw, pitch, roll)
        except Exception as ex:
            self.log_message(f"Error generating diagnostics test data: {ex}")
    
    def on_serial_stop(self):
        """Handle serial stop callback (same as tkinter version)."""
        self.log_message("Serial stopped: on_stop callback triggered")
    
    def test_update_rates(self):
        """Test updating StatusBar rates."""
        import random
        msg_rate = random.uniform(10, 100)
        send_rate = random.uniform(5, 50)
        camera_fps = random.uniform(15, 30)
        
        self.status_bar.update_all(
            msg_rate=msg_rate,
            send_rate=send_rate,
            camera_fps=camera_fps
        )
        
        values = self.status_bar.get_values()
        self.log_message(f"StatusBar Updated - Rates: {values}")
    
    def test_device_status(self):
        """Test toggling device status."""
        # Toggle between stationary and moving
        if not hasattr(self, '_device_stationary'):
            self._device_stationary = True
        
        self._device_stationary = not self._device_stationary
        self.status_bar.update_device_status(self._device_stationary)
        
        status = "stationary" if self._device_stationary else "moving"
        self.log_message(f"StatusBar Device Status: {status}")
    
    def test_reset_status(self):
        """Test resetting StatusBar to zero."""
        self.status_bar.reset()
        values = self.status_bar.get_values()
        self.log_message(f"StatusBar Reset - Values: {values}")
    
    def test_toggle_udp(self):
        """Test toggling UDP on/off."""
        was_enabled = self.network_panel.is_udp_enabled()
        self.network_panel.toggle_udp()
        now_enabled = self.network_panel.is_udp_enabled()
        
        status = "enabled" if now_enabled else "disabled"
        self.log_message(f"NetworkPanel UDP toggled: {was_enabled} -> {now_enabled} ({status})")
    
    def test_set_udp_config(self):
        """Test setting UDP configuration."""
        test_ip = "192.168.1.100"
        test_port = 5000
        
        self.network_panel.set_udp_config(test_ip, test_port)
        ip, port = self.network_panel.get_udp_config()
        
        self.log_message(f"NetworkPanel Set Config: {test_ip}:{test_port} -> {ip}:{port}")
    
    def test_get_udp_config(self):
        """Test getting UDP configuration."""
        ip, port = self.network_panel.get_udp_config()
        enabled = self.network_panel.is_udp_enabled()
        
        self.log_message(f"NetworkPanel Config: {ip}:{port} (enabled: {enabled})")
    
    def test_network_prefs(self):
        """Test NetworkPanel preferences save/load."""
        # Get current prefs
        prefs = self.network_panel.get_prefs()
        self.log_message(f"NetworkPanel Get Prefs: {prefs}")
        
        # Set test prefs
        test_prefs = {
            'udp_ip': '10.0.0.1',
            'udp_port': '9999'
        }
        self.network_panel.set_prefs(test_prefs)
        self.log_message(f"NetworkPanel Set Prefs: {test_prefs}")
        
        # Verify the change
        new_prefs = self.network_panel.get_prefs()
        self.log_message(f"NetworkPanel New Prefs: {new_prefs}")
    
    def test_add_serial(self):
        """Test adding serial data to MessagePanel."""
        import time
        serial_data = f"RAW_DATA: yaw={time.time():.2f}, pitch=12.5, roll=-3.8"
        self.message_panel.append_serial(serial_data)
        self.log_message(f"MessagePanel Added serial: {serial_data}")
    
    def test_add_message(self):
        """Test adding message to MessagePanel."""
        import time
        message = f"[{time.strftime('%H:%M:%S')}] Test message from PyQt test harness"
        self.message_panel.append_message(message)
        self.log_message(f"MessagePanel Added message: {message}")
    
    def test_update_displays(self):
        """Test updating MessagePanel displays."""
        self.message_panel.update_displays()
        serial_count = len(self.message_panel.get_serial_buffer())
        message_count = len(self.message_panel.get_message_buffer())
        self.log_message(f"MessagePanel Updated displays - Serial: {serial_count}, Messages: {message_count}")
    
    def test_clear_all(self):
        """Test clearing all MessagePanel buffers."""
        self.message_panel.clear_all()
        serial_count = len(self.message_panel.get_serial_buffer())
        message_count = len(self.message_panel.get_message_buffer())
        self.log_message(f"MessagePanel Cleared all - Serial: {serial_count}, Messages: {message_count}")
    
    def test_get_buffers(self):
        """Test getting MessagePanel buffer contents."""
        serial_buffer = self.message_panel.get_serial_buffer()
        message_buffer = self.message_panel.get_message_buffer()
        
        self.log_message(f"MessagePanel Serial buffer ({len(serial_buffer)} lines):")
        for i, line in enumerate(serial_buffer[-3:], 1):  # Show last 3 lines
            self.log_message(f"  {i}. {line}")
        
        self.log_message(f"MessagePanel Message buffer ({len(message_buffer)} lines):")
        for i, line in enumerate(message_buffer[-3:], 1):  # Show last 3 lines
            self.log_message(f"  {i}. {line}")
    
    @pyqtSlot()
    def monitor_queues(self):
        """Monitor queues for new commands (for testing)."""
        # Monitor serial control queue
        try:
            while not self.serial_control_queue.empty():
                try:
                    cmd = self.serial_control_queue.get_nowait()
                    self.log_message(f"[SERIAL QUEUE] {cmd}")
                except queue.Empty:
                    break
        except Exception:
            pass
        
        # Monitor UDP control queue
        try:
            while not self.udp_control_queue.empty():
                try:
                    cmd = self.udp_control_queue.get_nowait()
                    self.log_message(f"[UDP QUEUE] {cmd}")
                except queue.Empty:
                    break
        except Exception:
            pass
    
    # OrientationPanel Tests
    def test_update_euler(self):
        """Test updating Euler angles in OrientationPanel."""
        try:
            import random
            yaw = random.uniform(-180, 180)
            pitch = random.uniform(-90, 90)
            roll = random.uniform(-180, 180)
            
            self.orientation_panel.update_euler(yaw, pitch, roll)
            self.log_message(f"Updated Euler: Yaw={yaw:.1f}, Pitch={pitch:.1f}, Roll={roll:.1f}")
        except Exception as ex:
            self.log_message(f"Error testing update euler: {ex}")
    
    def test_update_position(self):
        """Test updating position in OrientationPanel."""
        try:
            import random
            x = random.uniform(-5, 5)
            y = random.uniform(-5, 5) 
            z = random.uniform(-2, 2)
            
            self.orientation_panel.update_position(x, y, z)
            self.log_message(f"Updated Position: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
        except Exception as ex:
            self.log_message(f"Error testing update position: {ex}")
    
    def test_drift_status(self):
        """Test toggling drift status in OrientationPanel."""
        try:
            import random
            active = random.choice([True, False])
            
            self.orientation_panel.update_drift_status(active)
            status = "Active" if active else "Inactive"
            self.log_message(f"Drift correction status: {status}")
        except Exception as ex:
            self.log_message(f"Error testing drift status: {ex}")
    
    def test_orientation_reset(self):
        """Test orientation reset functionality."""
        try:
            self.orientation_panel._on_reset()
            self.log_message("Orientation reset triggered")
        except Exception as ex:
            self.log_message(f"Error testing orientation reset: {ex}")
    
    def test_orientation_prefs(self):
        """Test preferences get/set for OrientationPanel."""
        try:
            # Get current preferences
            current_prefs = self.orientation_panel.get_prefs()
            self.log_message(f"Current prefs: {current_prefs}")
            
            # Test setting preferences
            test_prefs = {
                'reset_shortcut': 'F5',
                'filter': 'quaternion'
            }
            self.orientation_panel.set_prefs(test_prefs)
            
            # Verify preferences were applied
            new_prefs = self.orientation_panel.get_prefs()
            self.log_message(f"New prefs: {new_prefs}")
            
        except Exception as ex:
            self.log_message(f"Error testing orientation preferences: {ex}")
    
    # CalibrationPanel Tests
    def test_drift_angle_slider(self):
        """Test drift angle slider in CalibrationPanel."""
        try:
            import random
            # Test various drift angles
            test_angles = [0.0, 5.5, 12.3, 20.0, 25.0]
            test_angle = random.choice(test_angles)
            
            self.calibration_panel.set_drift_angle(test_angle)
            current_angle = self.calibration_panel.get_drift_angle()
            
            self.log_message(f"Set drift angle to {test_angle:.1f}°, got {current_angle:.1f}°")
        except Exception as ex:
            self.log_message(f"Error testing drift angle slider: {ex}")
    
    def test_calibration_status(self):
        """Test calibration status indicator."""
        try:
            import random
            calibrated = random.choice([True, False])
            
            self.calibration_panel.update_calibration_status(calibrated)
            status = "Calibrated" if calibrated else "Not calibrated"
            self.log_message(f"Gyro calibration status: {status}")
        except Exception as ex:
            self.log_message(f"Error testing calibration status: {ex}")
    
    def test_recalibrate_button(self):
        """Test recalibrate gyro bias button."""
        try:
            self.calibration_panel._on_recalibrate()
            self.log_message("Recalibrate gyro bias button triggered")
        except Exception as ex:
            self.log_message(f"Error testing recalibrate button: {ex}")
    
    def test_calibration_prefs(self):
        """Test preferences get/set for CalibrationPanel."""
        try:
            # Get current preferences
            current_prefs = self.calibration_panel.get_prefs()
            self.log_message(f"Current calibration prefs: {current_prefs}")
            
            # Test setting preferences
            test_prefs = {
                'drift_angle': '15.5'
            }
            self.calibration_panel.set_prefs(test_prefs)
            
            # Verify preferences were applied
            new_prefs = self.calibration_panel.get_prefs()
            self.log_message(f"New calibration prefs: {new_prefs}")
            
        except Exception as ex:
            self.log_message(f"Error testing calibration preferences: {ex}")
    
    def test_drift_angle_range(self):
        """Test drift angle slider boundary values."""
        try:
            # Test boundary values
            test_values = [-5.0, 0.0, 12.5, 25.0, 30.0]  # Include out-of-range values
            
            for value in test_values:
                self.calibration_panel.set_drift_angle(value)
                actual = self.calibration_panel.get_drift_angle()
                clamped = max(0.0, min(25.0, value))
                self.log_message(f"Drift angle: set {value:.1f}°, got {actual:.1f}°, expected {clamped:.1f}°")
                
        except Exception as ex:
            self.log_message(f"Error testing drift angle range: {ex}")
    
    # DiagnosticsPanel Tests
    def test_diagnostics_toggle(self):
        """Test CameraPanel preview toggle."""
        try:
            self.log_message("Testing camera preview toggle...")
            
            # Test preview toggle
            self.camera_panel.toggle_preview()
            enabled = self.camera_panel.preview_enabled
            text = self.camera_panel.preview_btn.text()
            self.log_message(f"Preview toggled: enabled={enabled}, button='{text}'")
            
            # Toggle back
            self.camera_panel.toggle_preview()
            enabled = self.camera_panel.preview_enabled
            text = self.camera_panel.preview_btn.text()
            self.log_message(f"Preview toggled back: enabled={enabled}, button='{text}'")
            
        except Exception as ex:
            self.log_message(f"Error testing camera preview: {ex}")
    
    def test_camera_selection(self):
        """Test CameraPanel camera selection."""
        try:
            self.log_message("Testing camera selection...")
            
            # Test camera selection
            cameras = [self.camera_panel.camera_cb.itemText(i) for i in range(self.camera_panel.camera_cb.count())]
            self.log_message(f"Available cameras: {cameras}")
            
            if len(cameras) > 1:
                self.camera_panel.camera_cb.setCurrentIndex(1)
                selected = self.camera_panel.camera_cb.currentText()
                self.log_message(f"Selected camera: {selected}")
            
            # Test set_cameras method
            test_cameras = ["Camera 0", "Camera 5", "Camera 9"]
            self.camera_panel.set_cameras(test_cameras)
            new_cameras = [self.camera_panel.camera_cb.itemText(i) for i in range(self.camera_panel.camera_cb.count())]
            self.log_message(f"Set cameras to: {new_cameras}")
            
        except Exception as ex:
            self.log_message(f"Error testing camera selection: {ex}")
    
    def test_camera_params(self):
        """Test CameraPanel FPS and resolution controls."""
        try:
            self.log_message("Testing camera parameters...")
            
            # Test FPS selection
            self.camera_panel.fps_cb.setCurrentText('60')
            fps = self.camera_panel.fps_cb.currentText()
            self.log_message(f"FPS set to: {fps}")
            
            # Test resolution selection
            self.camera_panel.res_cb.setCurrentText('1280x720')
            res = self.camera_panel.res_cb.currentText()
            self.log_message(f"Resolution set to: {res}")
            
            # Test parameter change notification
            self.camera_panel._on_cam_params_changed()
            self.log_message("Camera parameters updated")
            
        except Exception as ex:
            self.log_message(f"Error testing camera parameters: {ex}")
    
    def test_camera_backend(self):
        """Test CameraPanel backend selection."""
        try:
            self.log_message("Testing camera backend selection...")
            
            # Test backend selection
            backends = [self.camera_panel.backend_cb.itemText(i) for i in range(self.camera_panel.backend_cb.count())]
            self.log_message(f"Available backends: {backends}")
            
            # Switch to pseyepy backend if available
            if len(backends) > 1:
                self.camera_panel.backend_cb.setCurrentText(backends[1])
                backend = self.camera_panel.backend_cb.currentText()
                self.log_message(f"Backend switched to: {backend}")
                
                # Switch back to openCV
                self.camera_panel.backend_cb.setCurrentText(backends[0])
                backend = self.camera_panel.backend_cb.currentText()
                self.log_message(f"Backend switched back to: {backend}")
            
        except Exception as ex:
            self.log_message(f"Error testing camera backend: {ex}")
    
    def test_camera_options(self):
        """Test CameraPanel options dialog and variables."""
        try:
            self.log_message("Testing camera options...")
            
            # Test that options button exists and is enabled
            enabled = self.camera_panel.options_btn.isEnabled()
            text = self.camera_panel.options_btn.text()
            self.log_message(f"Options button: '{text}', enabled={enabled}")
            
            # Test current threshold/exposure/gain values
            self.log_message(f"Current threshold: {self.camera_panel.thresh_var}")
            self.log_message(f"Current exposure: {self.camera_panel.exposure_var}")
            self.log_message(f"Current gain: {self.camera_panel.gain_var}")
            
            # Test setting values directly
            self.camera_panel.thresh_var = 128
            self.camera_panel.exposure_var = 100
            self.camera_panel.gain_var = 32
            self.log_message(f"Set threshold to: {self.camera_panel.thresh_var}")
            self.log_message(f"Set exposure to: {self.camera_panel.exposure_var}")
            self.log_message(f"Set gain to: {self.camera_panel.gain_var}")
            
        except Exception as ex:
            self.log_message(f"Error testing camera options: {ex}")
    
    def test_position_tracking(self):
        """Test CameraPanel position tracking toggle."""
        try:
            self.log_message("Testing position tracking...")
            
            # Test position tracking toggle
            self.camera_panel.toggle_position_tracking()
            enabled = self.camera_panel.pos_track_enabled
            text = self.camera_panel.pos_btn.text()
            self.log_message(f"Position tracking: enabled={enabled}, button='{text}'")
            
            # Test that controls are disabled during tracking
            if enabled:
                camera_enabled = self.camera_panel.camera_cb.isEnabled()
                fps_enabled = self.camera_panel.fps_cb.isEnabled()
                backend_enabled = self.camera_panel.backend_cb.isEnabled()
                self.log_message(f"Controls disabled: camera={not camera_enabled}, fps={not fps_enabled}, backend={not backend_enabled}")
            
            # Toggle back
            self.camera_panel.toggle_position_tracking()
            enabled = self.camera_panel.pos_track_enabled
            text = self.camera_panel.pos_btn.text()
            self.log_message(f"Position tracking stopped: enabled={enabled}, button='{text}'")
            
            # Test that controls are re-enabled
            camera_enabled = self.camera_panel.camera_cb.isEnabled()
            fps_enabled = self.camera_panel.fps_cb.isEnabled()
            self.log_message(f"Controls re-enabled: camera={camera_enabled}, fps={fps_enabled}")
            
        except Exception as ex:
            self.log_message(f"Error testing position tracking: {ex}")
    
    def test_camera_preferences(self):
        """Test CameraPanel preferences save/load."""
        try:
            self.log_message("Testing camera preferences...")
            
            # Get current preferences
            prefs = self.camera_panel.get_prefs()
            self.log_message(f"Camera preferences keys: {list(prefs.keys())}")
            
            # Test that essential keys are present
            required_keys = ['camera', 'fps', 'resolution', 'thresh', 'backend']
            for key in required_keys:
                if key in prefs:
                    self.log_message(f"✓ {key}: {prefs[key]}")
                else:
                    self.log_message(f"✗ Missing key: {key}")
            
            # Test setting preferences
            test_prefs = {
                'camera': 'Camera 2',
                'fps': '60',
                'resolution': '1280x720',
                'thresh': '150',
                'exposure': '120',
                'gain': '25',
                'backend': 'pseyepy (PS3Eye)',
                'cameras': 'Camera 0,Camera 1,Camera 2',
                'cameras_opencv': 'Camera 0,Camera 1',
                'cameras_pseyepy': 'Camera 0'
            }
            self.camera_panel.set_prefs(test_prefs)
            
            # Verify preferences were applied
            new_prefs = self.camera_panel.get_prefs()
            self.log_message(f"Applied test preferences - backend: {new_prefs.get('backend')}")
            
        except Exception as ex:
            self.log_message(f"Error testing camera preferences: {ex}")
    
    def test_camera_image_display(self):
        """Test CameraPanel image display functionality."""
        try:
            self.log_message("Testing camera image display...")
            
            # Test preview disabled state
            self.camera_panel._draw_preview_disabled()
            self.log_message("Preview disabled display updated")
            
            # Test that preview label is properly configured
            preview_size = self.camera_panel.preview_label.size()
            self.log_message(f"Preview label size: {preview_size.width()}x{preview_size.height()}")
            
            # Test image handling (with mock data - real JPEG would come from camera worker)
            self.log_message("Image update functionality available (requires JPEG data from camera worker)")
            
        except Exception as ex:
            self.log_message(f"Error testing camera image display: {ex}")
    
    # DiagnosticsPanel Tests
    def test_diagnostics_toggle(self):
        """Test diagnostics enable/disable toggle."""
        try:
            # Toggle diagnostics mode
            current_state = self.diagnostics_panel.is_enabled()
            self.diagnostics_panel.enable_checkbox.setChecked(not current_state)
            new_state = self.diagnostics_panel.is_enabled()
            
            status = "enabled" if new_state else "disabled"
            self.log_message(f"Diagnostics mode toggled: {current_state} -> {new_state} ({status})")
        except Exception as ex:
            self.log_message(f"Error testing diagnostics toggle: {ex}")
    
    def test_diagnostics_data_update(self):
        """Test updating diagnostics with orientation data."""
        try:
            import random
            
            # Generate random orientation data
            yaw = random.uniform(-180, 180)
            pitch = random.uniform(-90, 90)
            roll = random.uniform(-180, 180)
            
            # Enable diagnostics first
            self.diagnostics_panel.enable_checkbox.setChecked(True)
            
            # Send data update
            self.diagnostics_panel.update_euler(yaw, pitch, roll)
            
            self.log_message(f"Diagnostics data update: Yaw={yaw:.1f}, Pitch={pitch:.1f}, Roll={roll:.1f}")
            
            # Check data storage
            data_points = len(self.diagnostics_panel.data_times)
            self.log_message(f"Diagnostics has {data_points} data points stored")
            
        except Exception as ex:
            self.log_message(f"Error testing diagnostics data update: {ex}")
    
    def test_diagnostics_clear_data(self):
        """Test clearing diagnostics data."""
        try:
            # Clear data
            self.diagnostics_panel._clear_data()
            
            data_points = len(self.diagnostics_panel.data_times)
            self.log_message(f"Diagnostics data cleared: {data_points} data points remaining")
            
        except Exception as ex:
            self.log_message(f"Error testing diagnostics clear data: {ex}")
    
    def test_diagnostics_prefs(self):
        """Test diagnostics panel preferences save/load."""
        try:
            # Get current preferences
            current_prefs = self.diagnostics_panel.get_prefs()
            self.log_message(f"Current diagnostics prefs: {current_prefs}")
            
            # Test setting preferences
            test_prefs = {
                'enabled': True,
                'max_data_points': 500
            }
            self.diagnostics_panel.set_prefs(test_prefs)
            
            # Verify preferences were applied
            new_prefs = self.diagnostics_panel.get_prefs()
            self.log_message(f"Applied diagnostics prefs: {new_prefs}")
            
        except Exception as ex:
            self.log_message(f"Error testing diagnostics preferences: {ex}")


def main():
    """Run the PyQt test harness."""
    print("Starting PyQt Panel Test Harness...")
    print("This tests PyQt panel implementations alongside tkinter versions.")
    print("The production gui_wrk.py and tkinter panels remain unchanged.\n")
    
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("frankentrack PyQt Test")
    app.setOrganizationName("frankentrack")
    
    test_app = TestAppQt()
    test_app.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()