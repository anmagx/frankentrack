"""
Test harness for refactored GUI components.

This allows testing new panel implementations in isolation or in a minimal
test GUI without affecting the production gui_wrk.py.

Usage:
    python -m workers.gui.test_panels
"""
import tkinter as tk
from tkinter import ttk
import queue
from config.config import QUEUE_PUT_TIMEOUT
from util.error_utils import safe_queue_get, safe_queue_put
import time

from workers.gui.panels.serial_panel import SerialPanel
from workers.gui.panels.message_panel import MessagePanel
from workers.gui.panels.orientation_panel import OrientationPanel
from workers.gui.panels.status_bar import StatusBar
from workers.gui.panels.network_panel import NetworkPanel
from workers.gui.panels.camera_panel import CameraPanel
from workers.gui.panels.calibration_panel import CalibrationPanel


class TestApp(tk.Tk):
    """Minimal test application for panel testing."""
    
    def __init__(self):
        super().__init__()
        self.title("frankentrack - Panel Test Harness")
        self.geometry("900x700")
        
        # Create mock queues for testing
        self.serial_control_queue = queue.Queue()
        self.fusion_control_queue = queue.Queue()
        self.udp_control_queue = queue.Queue()
        self.camera_control_queue = queue.Queue()
        self.message_queue = queue.Queue()
        
        # Create test panel selection
        self._setup_panel_selector()
        
        # Create message display for logging
        self._setup_message_display()
        
        # Create panels under test
        self._setup_test_panels()
        
        # Create control buttons
        self._setup_controls()
        
        # Pack status bar at bottom
        self.status_bar.pack(side="bottom", fill="x")
        
        # Monitor queue for testing
        self._monitor_queue()
        
        # Auto-generate some test data
        self.after(1000, self._generate_test_data)
    
    def _setup_panel_selector(self):
        """Setup panel selector dropdown."""
        selector_frame = ttk.Frame(self)
        selector_frame.pack(fill="x", padx=8, pady=8)
        
        ttk.Label(selector_frame, text="Panel Under Test:").pack(side="left", padx=(0, 8))
        
        self.panel_var = tk.StringVar(value="OrientationPanel")
        panel_selector = ttk.Combobox(
            selector_frame,
            textvariable=self.panel_var,
            values=["SerialPanel", "MessagePanel", "OrientationPanel", "NetworkPanel", "CameraPanel", "All"],
            state="readonly",
            width=20
        )
        panel_selector.pack(side="left")
        panel_selector.bind('<<ComboboxSelected>>', self._on_panel_changed)
    
    def _setup_message_display(self):
        """Setup message display area for test logging."""
        msg_frame = ttk.LabelFrame(self, text="Test Log", padding=8)
        msg_frame.pack(fill="x", padx=8, pady=(0, 8))
        
        self.log_text = tk.Text(msg_frame, wrap="word", height=6, state="disabled")
        vsb = ttk.Scrollbar(msg_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vsb.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
    
    def _setup_test_panels(self):
        """Setup the panels being tested."""
        self.panel_container = ttk.Frame(self)
        self.panel_container.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Create both panels (we'll show/hide based on selection)
        self.serial_panel = SerialPanel(
            self.panel_container,
            self.serial_control_queue,
            self.log_message,
            padding=8,
            on_stop=self._on_serial_stop
        )
        
        self.message_panel = MessagePanel(
            self.panel_container,
            serial_height=10,
            message_height=10,
            padding=6
        )
        
        self.orientation_panel = OrientationPanel(
            self.panel_container,
            self.fusion_control_queue,
            self.log_message,
            padding=6
        )

        self.calibration_panel = CalibrationPanel(
            self.panel_container,
            self.fusion_control_queue,
            self.log_message,
            padding=6
        )
        
        self.status_bar = StatusBar(self, relief="sunken")
        
        self.network_panel = NetworkPanel(
            self.panel_container,
            self.udp_control_queue,
            self.log_message,
            padding=6
        )
        
        self.camera_panel = CameraPanel(
            self.panel_container,
            self.camera_control_queue,
            self.message_queue,
            padding=6
        )
        
        # Show OrientationPanel by default
        self._show_panel("OrientationPanel")
    
    def _show_panel(self, panel_name):
        """Show the selected panel."""
        # Hide all panels
        self.serial_panel.pack_forget()
        self.message_panel.pack_forget()
        self.orientation_panel.pack_forget()
        self.calibration_panel.pack_forget()
        self.network_panel.pack_forget()
        self.camera_panel.pack_forget()
        
        # Show selected panel(s)
        if panel_name == "SerialPanel":
            self.serial_panel.pack(fill="x", pady=(0, 8))
        elif panel_name == "MessagePanel":
            self.message_panel.pack(fill="both", expand=True)
        elif panel_name == "OrientationPanel":
            self.orientation_panel.pack(fill="x", pady=(0, 0))
            # Show calibration panel directly below orientation
            self.calibration_panel.pack(fill="x", pady=(0, 8))
        elif panel_name == "NetworkPanel":
            self.network_panel.pack(fill="x", pady=(0, 8))
        elif panel_name == "CameraPanel":
            self.camera_panel.pack(fill="both", expand=True, pady=(0, 8))
        elif panel_name == "All":
            self.serial_panel.pack(fill="x", pady=(0, 8))
            self.message_panel.pack(fill="both", expand=True, pady=(0, 8))
            self.orientation_panel.pack(fill="x", pady=(0, 8))
            self.calibration_panel.pack(fill="x", pady=(0, 8))
            self.network_panel.pack(fill="x", pady=(0, 8))
            self.camera_panel.pack(fill="both", expand=True)
    
    def _on_panel_changed(self, event=None):
        """Handle panel selection change."""
        self._show_panel(self.panel_var.get())
        self.log_message(f"Switched to: {self.panel_var.get()}")
    
    def _setup_controls(self):
        """Setup test control buttons."""
        ctrl_frame = ttk.LabelFrame(self, text="Test Controls", padding=8)
        ctrl_frame.pack(fill="x", padx=8, pady=(0, 8))
        
        # Row 1: Serial Panel controls
        row1 = ttk.Frame(ctrl_frame)
        row1.pack(fill="x", pady=(0, 4))
        
        ttk.Label(row1, text="SerialPanel:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row1, 
            text="Test Get Prefs", 
            command=self._test_get_prefs
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row1, 
            text="Test Set Prefs", 
            command=self._test_set_prefs
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row1, 
            text="Show Queue", 
            command=self._show_queue_contents
        ).pack(side="left", padx=2)
        
        # Row 2: Message Panel controls
        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill="x", pady=(0, 4))
        
        ttk.Label(row2, text="MessagePanel:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row2, 
            text="Add Serial Lines", 
            command=self._test_add_serial
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row2, 
            text="Add Messages", 
            command=self._test_add_messages
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row2, 
            text="Clear Serial", 
            command=lambda: self.message_panel.clear_serial()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row2, 
            text="Clear Messages", 
            command=lambda: self.message_panel.clear_messages()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row2, 
            text="Clear All", 
            command=lambda: self.message_panel.clear_all()
        ).pack(side="left", padx=2)
        
        # Row 3: General controls
        row3 = ttk.Frame(ctrl_frame)
        row3.pack(fill="x")
        
        ttk.Label(row3, text="General:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row3, 
            text="Clear Test Log", 
            command=self._clear_log
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row3, 
            text="Generate Test Data", 
            command=self._generate_test_data
        ).pack(side="left", padx=2)
        
        # Row 4: Orientation Panel controls
        row4 = ttk.Frame(ctrl_frame)
        row4.pack(fill="x", pady=(0, 4))
        
        ttk.Label(row4, text="OrientationPanel:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row4,
            text="Update Euler (45°)",
            command=self._test_update_euler
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row4,
            text="Update Position",
            command=self._test_update_position
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row4,
            text="Toggle Drift Status",
            command=self._test_toggle_drift
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row4,
            text="Show Fusion Queue",
            command=self._show_fusion_queue
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row4,
            text="Simulate Data Stream",
            command=self._simulate_orientation_stream
        ).pack(side="left", padx=2)
        
        # Row 5: StatusBar controls
        row5 = ttk.Frame(ctrl_frame)
        row5.pack(fill="x")
        
        ttk.Label(row5, text="StatusBar:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row5,
            text="Update Metrics",
            command=self._test_update_metrics
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row5,
            text="Reset StatusBar",
            command=lambda: self.status_bar.reset()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row5,
            text="Simulate Activity",
            command=self._simulate_status_activity
        ).pack(side="left", padx=2)
        
        # Row 6: NetworkPanel controls
        row6 = ttk.Frame(ctrl_frame)
        row6.pack(fill="x", pady=(4, 0))
        
        ttk.Label(row6, text="NetworkPanel:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row6,
            text="Toggle UDP",
            command=lambda: self.network_panel.toggle_udp()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row6,
            text="Set Test Config",
            command=self._test_set_network_config
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row6,
            text="Get Config",
            command=self._test_get_network_config
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row6,
            text="Show UDP Queue",
            command=self._show_udp_queue
        ).pack(side="left", padx=2)
        
        # Row 7: CameraPanel controls
        row7 = ttk.Frame(ctrl_frame)
        row7.pack(fill="x", pady=(4, 0))
        
        ttk.Label(row7, text="CameraPanel:").pack(side="left", padx=(0, 8))
        
        ttk.Button(
            row7,
            text="Toggle Preview",
            command=lambda: self.camera_panel.toggle_preview()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row7,
            text="Toggle Pos Track",
            command=lambda: self.camera_panel.toggle_position_tracking()
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row7,
            text="Set Test Cameras",
            command=self._test_set_cameras
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row7,
            text="Get Camera Prefs",
            command=self._test_get_camera_prefs
        ).pack(side="left", padx=2)
        
        ttk.Button(
            row7,
            text="Show Camera Queue",
            command=self._show_camera_queue
        ).pack(side="left", padx=2)
    
    def log_message(self, msg):
        """Append a message to the test log display."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    
    def _test_get_prefs(self):
        """Test getting preferences from SerialPanel."""
        prefs = self.serial_panel.get_prefs()
        self.log_message(f"SerialPanel Get Prefs: {prefs}")
    
    def _test_set_prefs(self):
        """Test setting preferences on SerialPanel."""
        test_prefs = {
            'com_port': 'COM3',
            'baud_rate': '115200'
        }
        self.serial_panel.set_prefs(test_prefs)
        self.log_message(f"SerialPanel Set Prefs: {test_prefs}")
    
    def _test_add_serial(self):
        """Test adding serial lines to MessagePanel."""
        test_lines = [
            "a:-0.12,0.45,9.81,g:0.01,-0.02,0.00",
            "a:0.05,0.32,9.85,g:0.00,-0.01,0.01",
            "a:-0.08,0.40,9.79,g:0.02,0.00,-0.01"
        ]
        for line in test_lines:
            self.message_panel.append_serial(line)
        self.message_panel.update_serial_display()
        self.log_message(f"Added {len(test_lines)} serial lines")
    
    def _test_add_messages(self):
        """Test adding messages to MessagePanel."""
        test_messages = [
            "Serial connection established",
            "IMU data streaming started",
            "Fusion worker initialized"
        ]
        for msg in test_messages:
            self.message_panel.append_message(msg)
        self.message_panel.update_message_display()
        self.log_message(f"Added {len(test_messages)} messages")
    
    def _clear_log(self):
        """Clear the test log display."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
    
    def _show_queue_contents(self):
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
    
    def _generate_test_data(self):
        """Generate realistic test data for MessagePanel."""
        import random
        
        # Add some serial lines
        for i in range(5):
            ax = random.uniform(-0.5, 0.5)
            ay = random.uniform(-0.5, 0.5)
            az = random.uniform(9.5, 10.0)
            gx = random.uniform(-0.05, 0.05)
            gy = random.uniform(-0.05, 0.05)
            gz = random.uniform(-0.05, 0.05)
            line = f"a:{ax:.2f},{ay:.2f},{az:.2f},g:{gx:.3f},{gy:.3f},{gz:.3f}"
            self.message_panel.append_serial(line)
        
        # Add some messages
        messages = [
            f"Test data generated at {time.strftime('%H:%M:%S')}",
            f"Serial buffer: {len(self.message_panel.get_serial_buffer())} lines",
            f"Message buffer: {len(self.message_panel.get_message_buffer())} lines"
        ]
        for msg in messages:
            self.message_panel.append_message(msg)
        
        # Update displays
        self.message_panel.update_displays()
        self.log_message("Generated test data")
    
    def _test_update_euler(self):
        """Test updating Euler angles in OrientationPanel."""
        self.orientation_panel.update_euler(45.0, 15.0, -10.0)
        self.log_message("Updated Euler: Yaw=45.0, Pitch=15.0, Roll=-10.0")
    
    def _test_update_position(self):
        """Test updating position in OrientationPanel."""
        import random
        x = random.uniform(-1.0, 1.0)
        y = random.uniform(-1.0, 1.0)
        z = random.uniform(-0.1, 0.1)
        self.orientation_panel.update_position(x, y, z)
        self.log_message(f"Updated Position: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    
    def _test_toggle_drift(self):
        """Test toggling drift correction status."""
        # Toggle between active and inactive
        current = self.orientation_panel.drift_status_var.get()
        active = "Inactive" in current
        self.orientation_panel.update_drift_status(active)
        self.log_message(f"Drift status: {'Active' if active else 'Inactive'}")
    
    def _show_fusion_queue(self):
        """Display contents of the fusion control queue."""
        contents = []
        temp_queue = queue.Queue()
        
        # Drain queue
        while not self.fusion_control_queue.empty():
            try:
                item = self.fusion_control_queue.get_nowait()
                contents.append(item)
                temp_queue.put(item)
            except queue.Empty:
                break
        
        # Restore queue
        while not temp_queue.empty():
            try:
                self.fusion_control_queue.put(temp_queue.get_nowait())
            except queue.Empty:
                break
        
        if contents:
            self.log_message(f"Fusion Queue Contents ({len(contents)} items):")
            for i, item in enumerate(contents, 1):
                self.log_message(f"  {i}. {item}")
        else:
            self.log_message("Fusion Queue is empty")
    
    def _simulate_orientation_stream(self):
        """Simulate a continuous stream of orientation data."""
        import random
        import math
        
        # Simulate 10 updates
        for i in range(10):
            # Generate smooth-ish data
            t = i * 0.1
            yaw = 45 * math.sin(t)
            pitch = 15 * math.cos(t * 1.5)
            roll = -10 * math.sin(t * 0.8)
            
            x = 0.5 * math.sin(t * 2)
            y = 0.3 * math.cos(t * 2.5)
            z = 0.05 * math.sin(t * 3)
            
            self.orientation_panel.update_euler(yaw, pitch, roll)
            self.orientation_panel.update_position(x, y, z)
        
        # Toggle drift status randomly
        self.orientation_panel.update_drift_status(random.choice([True, False]))
        
        self.log_message("Simulated orientation data stream (10 updates)")
    
    def _test_update_metrics(self):
        """Test updating status bar metrics."""
        import random
        msg_rate = random.uniform(50, 150)
        send_rate = random.uniform(40, 60)
        cam_fps = random.uniform(25, 35)
        
        self.status_bar.update_all(
            msg_rate=msg_rate,
            send_rate=send_rate,
            camera_fps=cam_fps
        )
        self.log_message(f"Updated metrics: {msg_rate:.1f} msg/s, {send_rate:.1f} send/s, {cam_fps:.1f} fps")
    
    def _simulate_status_activity(self):
        """Simulate changing status bar values over time."""
        import random
        
        def update_step(count):
            if count <= 0:
                self.log_message("Status activity simulation complete")
                return
            
            # Generate realistic values with some variation
            msg_rate = 100 + random.uniform(-20, 20)
            send_rate = 50 + random.uniform(-5, 5)
            cam_fps = 30 + random.uniform(-3, 3)
            
            self.status_bar.update_all(
                msg_rate=msg_rate,
                send_rate=send_rate,
                camera_fps=cam_fps
            )
            
            # Schedule next update
            self.after(200, lambda: update_step(count - 1))
        
        self.log_message("Starting status activity simulation (10 updates)...")
        update_step(10)
    
    def _test_set_network_config(self):
        """Test setting network configuration."""
        self.network_panel.set_udp_config("192.168.1.100", 5000)
        self.log_message("Set network config: 192.168.1.100:5000")
    
    def _test_get_network_config(self):
        """Test getting network configuration."""
        ip, port = self.network_panel.get_udp_config()
        enabled = self.network_panel.is_udp_enabled()
        self.log_message(f"Network config: {ip}:{port}, Enabled: {enabled}")
    
    def _show_udp_queue(self):
        """Display contents of the UDP control queue."""
        contents = []
        temp_queue = queue.Queue()
        
        # Drain queue
        while not self.udp_control_queue.empty():
            try:
                item = self.udp_control_queue.get_nowait()
                contents.append(item)
                temp_queue.put(item)
            except queue.Empty:
                break
        
        # Restore queue
        while not temp_queue.empty():
            try:
                self.udp_control_queue.put(temp_queue.get_nowait())
            except queue.Empty:
                break
        
        if contents:
            self.log_message(f"UDP Queue Contents ({len(contents)} items):")
            for i, item in enumerate(contents, 1):
                self.log_message(f"  {i}. {item}")
        else:
            self.log_message("UDP Queue is empty")
    
    def _test_set_cameras(self):
        """Test setting camera list in CameraPanel."""
        test_cameras = ["Camera 0", "Camera 1", "Camera 9"]
        self.camera_panel.set_cameras(test_cameras)
        self.log_message(f"Set camera list: {test_cameras}")
    
    def _test_get_camera_prefs(self):
        """Test getting camera preferences."""
        prefs = self.camera_panel.get_prefs()
        self.log_message(f"CameraPanel Get Prefs: {prefs}")
    
    def _show_camera_queue(self):
        """Display contents of the camera control queue."""
        contents = []
        temp_queue = queue.Queue()
        
        # Drain queue
        while not self.camera_control_queue.empty():
            try:
                item = self.camera_control_queue.get_nowait()
                contents.append(item)
                temp_queue.put(item)
            except queue.Empty:
                break
        
        # Restore queue
        while not temp_queue.empty():
            try:
                self.camera_control_queue.put(temp_queue.get_nowait())
            except queue.Empty:
                break
        
        if contents:
            self.log_message(f"Camera Queue Contents ({len(contents)} items):")
            for i, item in enumerate(contents, 1):
                self.log_message(f"  {i}. {item}")
        else:
            self.log_message("Camera Queue is empty")
    
    def _monitor_queue(self):
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
        
        # Monitor fusion control queue
        try:
            while not self.fusion_control_queue.empty():
                try:
                    cmd = self.fusion_control_queue.get_nowait()
                    self.log_message(f"[FUSION QUEUE] {cmd}")
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
        
        # Monitor camera control queue
        try:
            while not self.camera_control_queue.empty():
                try:
                    cmd = self.camera_control_queue.get_nowait()
                    self.log_message(f"[CAMERA QUEUE] {cmd}")
                except queue.Empty:
                    break
        except Exception:
            pass
        
        # Monitor message queue
        try:
            while not self.message_queue.empty():
                try:
                    msg = self.message_queue.get_nowait()
                    self.log_message(f"[MESSAGE] {msg}")
                except queue.Empty:
                    break
        except Exception:
            pass
        
        # Schedule next check
        self.after(100, self._monitor_queue)

    def _on_serial_stop(self):
        """Actions to perform when serial reading is stopped in the test harness.

        This will request a gyro recalibration and drain common queues so the
        test harness starts a fresh recording session.
        """
        try:
            # Request a full fusion reset on the fusion control queue
            try:
                safe_queue_put(self.fusion_control_queue, ('reset',), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

            # Drain non-control/display queues so UI buffers start fresh.
            # IMPORTANT: do NOT drain worker control queues here (e.g. serial
            # control or fusion control) because doing so can remove the
            # ('stop',) or ('reset',) commands that we just enqueued and
            # prevent workers from receiving them.
            for q in (self.message_queue,):
                try:
                    while True:
                        item = safe_queue_get(q, timeout=0.0, default=None)
                        if item is None:
                            break
                except Exception:
                    pass

            # Mark UI as uncalibrated so the user must explicitly recalibrate
            try:
                if hasattr(self, 'calibration_panel'):
                    self.calibration_panel.update_calibration_status(False)
            except Exception:
                pass
            try:
                if hasattr(self, 'status_bar'):
                    # Some test setups may include a status_bar method for calibration
                    if hasattr(self.status_bar, 'update_calibration_status'):
                        self.status_bar.update_calibration_status(False)
            except Exception:
                pass

            self.log_message("Serial stopped: fusion reset requested, marked uncalibrated, and queues drained")
        except Exception:
            self.log_message("Error during on_stop actions")


def main():
    """Run the test harness."""
    print("Starting Panel Test Harness...")
    print("This is a test environment for refactored GUI panels.")
    print("The production gui_wrk.py remains unchanged.\n")
    
    app = TestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
