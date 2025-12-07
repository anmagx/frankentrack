"""
PyQt5 GUI Worker with Tabbed Layout for frankentrack.

This is a slimmed-down tabbed interface that organizes panels into two focused views:
- Orientation Tracking: Serial, Message, Calibration, Orientation, Network panels
- Position Tracking: Camera panel

The Message Panel can be collapsed/expanded to save space when not needed.
"""

import sys
import queue
import threading
import time
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QFrame, QSplitter, QSizePolicy, QStatusBar
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QIcon

from workers.gui_qt.panels.serial_panel import SerialPanelQt
from workers.gui_qt.panels.network_panel import NetworkPanelQt
from workers.gui_qt.panels.message_panel import MessagePanelQt
from workers.gui_qt.panels.orientation_panel import OrientationPanelQt
from workers.gui_qt.panels.calibration_panel import CalibrationPanelQt
from workers.gui_qt.panels.camera_panel import CameraPanelQt

from workers.gui.managers.preferences_manager import PreferencesManager
from workers.gui.managers.icon_helper import set_window_icon

from config.config import (
    GUI_UPDATE_INTERVAL_MS, WORKER_QUEUE_CHECK_INTERVAL_MS,
    APP_NAME, APP_VERSION
)


class TabbedGUISignals(QObject):
    """Signals for the tabbed GUI worker."""
    status_update = pyqtSignal(str, str)  # section, message
    orientation_update = pyqtSignal(float, float, float)  # roll, pitch, yaw
    position_update = pyqtSignal(float, float, float)  # x, y, z
    drift_status_update = pyqtSignal(str)  # status
    preview_update = pyqtSignal(bytes)  # jpeg_data


class TabbedGUIWorker(QMainWindow):
    """PyQt5 GUI worker with tabbed layout for frankentrack."""

    def __init__(self, 
                 serial_control_queue,
                 fusion_control_queue, 
                 camera_control_queue,
                 udp_control_queue,
                 status_queue,
                 message_queue,
                 stop_event,
                 on_stop_callback=None):
        """
        Initialize the tabbed GUI worker.
        
        Args:
            serial_control_queue: Queue for serial worker commands
            fusion_control_queue: Queue for fusion worker commands  
            camera_control_queue: Queue for camera worker commands
            udp_control_queue: Queue for UDP worker commands
            status_queue: Queue for receiving status updates
            message_queue: Queue for receiving messages
            stop_event: Threading event for shutdown coordination
            on_stop_callback: Callback when GUI is closed
        """
        super().__init__()
        
        # Store queues and state
        self.serial_control_queue = serial_control_queue
        self.fusion_control_queue = fusion_control_queue
        self.camera_control_queue = camera_control_queue
        self.udp_control_queue = udp_control_queue
        self.status_queue = status_queue
        self.message_queue = message_queue
        self.stop_event = stop_event
        self.on_stop_callback = on_stop_callback
        
        # GUI state
        self.message_panel_collapsed = False
        
        # Initialize signals
        self.signals = TabbedGUISignals()
        self._connect_signals()
        
        # Setup UI
        self.setup_ui()
        self.setup_timers()
        self.load_preferences()
        
        print("[TabbedGUI] PyQt5 tabbed GUI worker initialized")
    
    def setup_ui(self):
        """Setup the main UI with tabbed layout."""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - PyQt5")
        self.setGeometry(100, 100, 900, 700)
        
        # Set window icon
        try:
            set_window_icon(self)
        except Exception as e:
            print(f"[TabbedGUI] Could not set window icon: {e}")
        
        # Central widget with tab layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.create_orientation_tab()
        self.create_position_tab()
        
        # Status bar at bottom
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("frankentrack ready")
        self.setStatusBar(self.status_bar)
    
    def create_orientation_tab(self):
        """Create the Orientation Tracking tab."""
        orientation_widget = QWidget()
        layout = QVBoxLayout(orientation_widget)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Serial Panel (always visible)
        self.serial_panel = SerialPanelQt(
            orientation_widget,
            self.serial_control_queue,
            self._log_message,
            padding=6,
            on_stop=self._on_serial_stop
        )
        layout.addWidget(self.serial_panel)
        
        # Message Panel with collapse/expand functionality
        message_frame = QFrame()
        message_layout = QVBoxLayout(message_frame)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(2)
        
        # Message panel header with collapse button
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 2, 4, 2)
        
        self.message_toggle_btn = QPushButton("📜 Messages (Click to collapse)")
        self.message_toggle_btn.setStyleSheet("text-align: left; padding: 4px;")
        self.message_toggle_btn.clicked.connect(self.toggle_message_panel)
        header_layout.addWidget(self.message_toggle_btn)
        
        header_layout.addStretch()
        message_layout.addWidget(header_frame)
        
        # Message Panel
        self.message_panel = MessagePanelQt(
            message_frame,
            serial_height=6,
            message_height=6,
            max_serial_lines=150,
            max_message_lines=75,
            padding=4
        )
        message_layout.addWidget(self.message_panel)
        
        layout.addWidget(message_frame)
        
        # Calibration Panel (compact)
        self.calibration_panel = CalibrationPanelQt(
            orientation_widget,
            self.fusion_control_queue,
            self._log_message,
            padding=6
        )
        layout.addWidget(self.calibration_panel)
        
        # Orientation Panel (main focus)
        self.orientation_panel = OrientationPanelQt(
            orientation_widget,
            self.fusion_control_queue,
            self._log_message,
            padding=6
        )
        layout.addWidget(self.orientation_panel)
        
        # Network Panel (compact)
        self.network_panel = NetworkPanelQt(
            orientation_widget,
            self.udp_control_queue,
            self._log_message,
            padding=6
        )
        layout.addWidget(self.network_panel)
        
        # Add stretch to push everything to top
        layout.addStretch()
        
        # Add tab
        self.tab_widget.addTab(orientation_widget, "🧭 Orientation Tracking")
    
    def create_position_tab(self):
        """Create the Position Tracking tab."""
        position_widget = QWidget()
        layout = QVBoxLayout(position_widget)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Camera Panel (main focus of this tab)
        self.camera_panel = CameraPanelQt(
            self.camera_control_queue,
            self.message_queue,
            position_widget
        )
        layout.addWidget(self.camera_panel)
        
        # Add stretch to center the camera panel
        layout.addStretch()
        
        # Add tab
        self.tab_widget.addTab(position_widget, "📹 Position Tracking")
    
    def toggle_message_panel(self):
        """Toggle the message panel collapsed/expanded state."""
        if self.message_panel_collapsed:
            # Expand
            self.message_panel.show()
            self.message_toggle_btn.setText("📜 Messages (Click to collapse)")
            self.message_panel_collapsed = False
        else:
            # Collapse
            self.message_panel.hide()
            self.message_toggle_btn.setText("📜 Messages (Click to expand)")
            self.message_panel_collapsed = True
    
    def _connect_signals(self):
        """Connect internal signals to update methods."""
        self.signals.status_update.connect(self._update_status_bar)
        self.signals.orientation_update.connect(self._update_orientation)
        self.signals.position_update.connect(self._update_position)
        self.signals.drift_status_update.connect(self._update_drift_status)
        self.signals.preview_update.connect(self._update_preview)
    
    def setup_timers(self):
        """Setup update timers."""
        # Main update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.process_queues)
        self.update_timer.start(WORKER_QUEUE_CHECK_INTERVAL_MS)
        
        # Periodic GUI updates
        self.gui_timer = QTimer()
        self.gui_timer.timeout.connect(self.update_gui_elements)
        self.gui_timer.start(GUI_UPDATE_INTERVAL_MS)
    
    def process_queues(self):
        """Process incoming queue messages."""
        # Process status updates
        while not self.status_queue.empty():
            try:
                item = self.status_queue.get_nowait()
                if isinstance(item, dict):
                    if 'section' in item and 'message' in item:
                        self.signals.status_update.emit(item['section'], item['message'])
                    elif 'orientation' in item:
                        # Orientation update from fusion worker
                        euler = item['orientation']
                        if len(euler) >= 3:
                            self.signals.orientation_update.emit(euler[0], euler[1], euler[2])
                    elif 'position' in item:
                        # Position update from fusion worker
                        pos = item['position']
                        if len(pos) >= 3:
                            self.signals.position_update.emit(pos[0], pos[1], pos[2])
                    elif 'drift_status' in item:
                        self.signals.drift_status_update.emit(item['drift_status'])
                    elif 'preview_data' in item:
                        # Camera preview data
                        self.signals.preview_update.emit(item['preview_data'])
                elif isinstance(item, str):
                    # Simple string status
                    self.signals.status_update.emit('general', item)
            except queue.Empty:
                break
            except Exception as e:
                print(f"[TabbedGUI] Error processing status queue: {e}")
        
        # Process message queue
        while not self.message_queue.empty():
            try:
                msg = self.message_queue.get_nowait()
                if isinstance(msg, str):
                    self.message_panel.append_message(msg)
            except queue.Empty:
                break
            except Exception as e:
                print(f"[TabbedGUI] Error processing message queue: {e}")
    
    def _update_status_bar(self, section: str, message: str):
        """Update the status bar with new information."""
        # For QStatusBar, we'll show the most recent message
        # You could extend this to show multiple sections if needed
        self.status_bar.showMessage(f"{section}: {message}", 5000)  # Show for 5 seconds
    
    def _update_orientation(self, roll: float, pitch: float, yaw: float):
        """Update orientation display."""
        if hasattr(self.orientation_panel, 'update_euler_angles'):
            self.orientation_panel.update_euler_angles(roll, pitch, yaw)
    
    def _update_position(self, x: float, y: float, z: float):
        """Update position display."""
        if hasattr(self.orientation_panel, 'update_position'):
            self.orientation_panel.update_position(x, y, z)
    
    def _update_drift_status(self, status: str):
        """Update drift status display."""
        if hasattr(self.calibration_panel, 'update_calibration_status'):
            # Map status to calibration panel format
            if 'active' in status.lower() or 'drifting' in status.lower():
                self.calibration_panel.update_calibration_status(False)  # Not calibrated
            else:
                self.calibration_panel.update_calibration_status(True)   # Calibrated
    
    def _update_preview(self, jpeg_data: bytes):
        """Update camera preview."""
        if hasattr(self.camera_panel, 'update_preview'):
            self.camera_panel.update_preview(jpeg_data)
    
    def update_gui_elements(self):
        """Periodic GUI updates."""
        # Update any time-based displays
        pass
    
    def _log_message(self, message: str):
        """Log a message to the message panel."""
        if hasattr(self.message_panel, 'append_message'):
            self.message_panel.append_message(message)
    
    def _on_serial_stop(self):
        """Handle serial panel stop button."""
        self._log_message("Serial panel stop requested")
        if self.on_stop_callback:
            self.on_stop_callback()
    
    def load_preferences(self):
        """Load saved preferences for all panels."""
        try:
            prefs_manager = PreferencesManager()
            prefs = prefs_manager.load()
            
            # Handle both dict and string formats for preferences
            if isinstance(prefs, str):
                print(f"[TabbedGUI] Preferences returned as string, skipping load")
                return
            
            if not isinstance(prefs, dict):
                print(f"[TabbedGUI] Unexpected preferences format: {type(prefs)}")
                return
            
            # Apply preferences to each panel
            if hasattr(self.serial_panel, 'set_prefs') and 'serial' in prefs:
                self.serial_panel.set_prefs(prefs['serial'])
            
            if hasattr(self.network_panel, 'set_prefs') and 'network' in prefs:
                self.network_panel.set_prefs(prefs['network'])
            
            if hasattr(self.orientation_panel, 'set_prefs') and 'orientation' in prefs:
                self.orientation_panel.set_prefs(prefs['orientation'])
            
            if hasattr(self.calibration_panel, 'set_prefs') and 'calibration' in prefs:
                self.calibration_panel.set_prefs(prefs['calibration'])
            
            if hasattr(self.camera_panel, 'set_prefs') and 'camera' in prefs:
                self.camera_panel.set_prefs(prefs['camera'])
            
            # Restore tab selection
            if 'gui' in prefs and isinstance(prefs['gui'], dict) and 'selected_tab' in prefs['gui']:
                try:
                    tab_index = int(prefs['gui']['selected_tab'])
                    if 0 <= tab_index < self.tab_widget.count():
                        self.tab_widget.setCurrentIndex(tab_index)
                except (ValueError, TypeError):
                    pass
            
            # Restore message panel state
            if 'gui' in prefs and isinstance(prefs['gui'], dict) and 'message_collapsed' in prefs['gui']:
                try:
                    collapsed = prefs['gui']['message_collapsed'].lower() == 'true'
                    if collapsed != self.message_panel_collapsed:
                        self.toggle_message_panel()
                except (AttributeError, KeyError):
                    pass
            
            print("[TabbedGUI] Preferences loaded")
            
        except Exception as e:
            print(f"[TabbedGUI] Error loading preferences: {e}")
    
    def save_preferences(self):
        """Save current preferences from all panels."""
        try:
            # Collect preferences from all panels
            prefs = {}
            
            if hasattr(self.serial_panel, 'get_prefs'):
                prefs['serial'] = self.serial_panel.get_prefs()
            
            if hasattr(self.network_panel, 'get_prefs'):
                prefs['network'] = self.network_panel.get_prefs()
            
            if hasattr(self.orientation_panel, 'get_prefs'):
                prefs['orientation'] = self.orientation_panel.get_prefs()
            
            if hasattr(self.calibration_panel, 'get_prefs'):
                prefs['calibration'] = self.calibration_panel.get_prefs()
            
            if hasattr(self.camera_panel, 'get_prefs'):
                prefs['camera'] = self.camera_panel.get_prefs()
            
            # Save GUI state
            prefs['gui'] = {
                'selected_tab': str(self.tab_widget.currentIndex()),
                'message_collapsed': str(self.message_panel_collapsed).lower()
            }
            
            # Save to preferences
            prefs_manager = PreferencesManager()
            prefs_manager.save(prefs)
            
            print("[TabbedGUI] Preferences saved")
            
        except Exception as e:
            print(f"[TabbedGUI] Error saving preferences: {e}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        print("[TabbedGUI] Close event received")
        
        # Save preferences before closing
        self.save_preferences()
        
        # Stop timers
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        if hasattr(self, 'gui_timer'):
            self.gui_timer.stop()
        
        # Signal shutdown
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
        
        # Call stop callback
        if self.on_stop_callback:
            self.on_stop_callback()
        
        # Accept close event
        event.accept()


def start_gui_worker(serial_control_queue,
                    fusion_control_queue,
                    camera_control_queue, 
                    udp_control_queue,
                    status_queue,
                    message_queue,
                    stop_event,
                    on_stop_callback=None):
    """
    Start the PyQt5 tabbed GUI worker.
    
    Args:
        serial_control_queue: Queue for serial commands
        fusion_control_queue: Queue for fusion commands
        camera_control_queue: Queue for camera commands
        udp_control_queue: Queue for UDP commands
        status_queue: Queue for receiving status updates
        message_queue: Queue for receiving messages
        stop_event: Threading event for shutdown coordination
        on_stop_callback: Callback when GUI is closed
    """
    print("[TabbedGUI] Starting PyQt5 tabbed GUI worker...")
    
    # Initialize QApplication
    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} - PyQt5")
    app.setOrganizationName("frankentrack")
    
    # Create main window
    main_window = TabbedGUIWorker(
        serial_control_queue=serial_control_queue,
        fusion_control_queue=fusion_control_queue,
        camera_control_queue=camera_control_queue,
        udp_control_queue=udp_control_queue,
        status_queue=status_queue,
        message_queue=message_queue,
        stop_event=stop_event,
        on_stop_callback=on_stop_callback
    )
    
    # Show window
    main_window.show()
    
    print("[TabbedGUI] PyQt5 tabbed GUI started")
    
    # Run event loop
    app.exec_()
    
    print("[TabbedGUI] PyQt5 tabbed GUI stopped")


if __name__ == "__main__":
    # Test the tabbed GUI independently
    print("Testing PyQt5 Tabbed GUI...")
    
    # Create mock queues
    import queue
    import threading
    
    test_queues = {
        'serial': queue.Queue(),
        'fusion': queue.Queue(), 
        'camera': queue.Queue(),
        'udp': queue.Queue(),
        'status': queue.Queue(),
        'message': queue.Queue()
    }
    
    stop_event = threading.Event()
    
    def test_stop():
        print("Test stop callback called")
        stop_event.set()
    
    # Start GUI
    start_gui_worker(
        serial_control_queue=test_queues['serial'],
        fusion_control_queue=test_queues['fusion'],
        camera_control_queue=test_queues['camera'],
        udp_control_queue=test_queues['udp'],
        status_queue=test_queues['status'],
        message_queue=test_queues['message'],
        stop_event=stop_event,
        on_stop_callback=test_stop
    )