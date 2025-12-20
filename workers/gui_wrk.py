"""
PyQt5 GUI Worker with Tabbed Layout for frankentrack.

This is a slimmed-down tabbed interface that organizes panels into focused views:
- Orientation Tracking: Serial, Message, Calibration, Orientation, Network panels

The Message Panel can be collapsed/expanded to save space when not needed.
"""

import sys
import queue
import threading
import time
import os
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
from workers.gui_qt.panels.status_bar import StatusBarQt
from workers.gui_qt.panels.preferences_panel import PreferencesPanel
from workers.gui_qt.panels.about_panel import AboutPanel
from workers.gui_qt.panels.diagnostics_panel import DiagnosticsPanelQt
from workers.gui_qt.panels.hold_panel import HoldPanelQt
from workers.gui_qt.panels.camera_panel import CameraPanelQt

from workers.gui_qt.managers.preferences_manager import PreferencesManager
from workers.gui_qt.helpers.icon_helper import set_window_icon
from workers.gui_qt.managers.theme_manager import ThemeManager

from config.config import (
    GUI_UPDATE_INTERVAL_MS, WORKER_QUEUE_CHECK_INTERVAL_MS,
    APP_NAME, APP_VERSION
)


class TabbedGUISignals(QObject):
    """Signals for the tabbed GUI worker."""
    status_update = pyqtSignal(str, str)  # section, message
    orientation_update = pyqtSignal(float, float, float)  # roll, pitch, yaw
    drift_status_update = pyqtSignal(str)  # status


class TabbedGUIWorker(QMainWindow):
    """PyQt5 GUI worker with tabbed layout for frankentrack."""

    def __init__(self, serial_control_queue, fusion_control_queue,
                 udp_control_queue, status_queue, ui_status_queue, message_queue,
                 serial_display_queue=None, euler_display_queue=None,
                 camera_control_queue=None, translation_display_queue=None, camera_preview_queue=None,
                 log_queue=None, stop_event=None, on_stop_callback=None,
                 input_command_queue=None, input_response_queue=None):
        """
        Initialize the tabbed GUI worker.
        
        Args:
            serial_control_queue: Queue for serial worker commands
            fusion_control_queue: Queue for fusion worker commands  
            udp_control_queue: Queue for UDP worker commands
            status_queue: Queue for receiving status updates
            ui_status_queue: Queue for receiving UI-specific status updates
            message_queue: Queue for receiving messages
            serial_display_queue: Queue for raw serial data display
            euler_display_queue: Queue for orientation angles
            translation_display_queue: Queue for position data  
            log_queue: Queue for log messages
            stop_event: Threading event for shutdown coordination
            on_stop_callback: Callback when GUI is closed
            input_command_queue: Queue for sending commands to input worker
            input_response_queue: Queue for receiving responses from input worker
        """
        super().__init__()
        
        # Store queues and state
        self.serial_control_queue = serial_control_queue
        self.fusion_control_queue = fusion_control_queue
        self.udp_control_queue = udp_control_queue
        self.status_queue = status_queue
        self.ui_status_queue = ui_status_queue
        self.message_queue = message_queue
        self.serial_display_queue = serial_display_queue
        self.euler_display_queue = euler_display_queue
        # Camera-related queues
        self.camera_control_queue = camera_control_queue
        self.translation_display_queue = translation_display_queue
        self.camera_preview_queue = camera_preview_queue
        self.log_queue = log_queue
        self.stop_event = stop_event
        self.on_stop_callback = on_stop_callback
        
        # Input worker queues
        self.input_command_queue = input_command_queue
        self.input_response_queue = input_response_queue
        
        # Initialize managers
        self.preferences_manager = PreferencesManager()
        self.theme_manager = ThemeManager(QApplication.instance())
        
        # Initialize signals
        self.signals = TabbedGUISignals()
        self._connect_signals()
        
        # Setup UI
        self.setup_ui()
        self.setup_timers()
        
        # Auto-resize window to fit content perfectly (after UI is built)
        QTimer.singleShot(0, self._finalize_window_size)
        
        self.load_preferences()
    
    def setup_ui(self):
        """Setup the main UI with tabbed layout."""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        
        # Set window icon
        try:
            set_window_icon(self)
        except Exception as e:
            print(f"[GUI] Could not set window icon: {e}")
        
        # Central widget with tab layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Add HOLD STILL panel at the very top
        self.hold_panel = HoldPanelQt(central_widget)
        main_layout.addWidget(self.hold_panel)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        # Connect tab selection to enable/disable diagnostics for performance
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs (Camera tab placed between Orientation and Diagnostics)
        self.create_orientation_tab()
        self.create_camera_tab()
        self.create_diagnostics_tab()
        self.create_messages_tab()
        self.create_preferences_tab()
        self.create_about_tab()
        
        # Status bar at bottom
        self.status_bar = StatusBarQt(self)
        main_layout.addWidget(self.status_bar)
    
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
            on_stop=None  # Don't link serial stop to app shutdown
        )
        layout.addWidget(self.serial_panel)
        
        # Calibration Panel (compact)
        self.calibration_panel = CalibrationPanelQt(
            orientation_widget,
            self.fusion_control_queue,
            self._log_message,
            padding=6,
            input_command_queue=self.input_command_queue,
            input_response_queue=self.input_response_queue
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
        
        # Connect calibration panel to orientation panel for drift angle visualization
        self.orientation_panel.connect_calibration_panel(self.calibration_panel)
        
        # Network Panel (compact)
        self.network_panel = NetworkPanelQt(
            orientation_widget,
            self.udp_control_queue,
            self._log_message,
            padding=6
        )
        layout.addWidget(self.network_panel)
        
        # Add tab
        self.tab_widget.addTab(orientation_widget, "🧭 Orientation Tracking")
    
    def create_diagnostics_tab(self):
        """Create the Diagnostics tab with real-time plotting."""
        diagnostics_widget = QWidget()
        layout = QVBoxLayout(diagnostics_widget)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Diagnostics Panel (full-sized in its own tab)
        self.diagnostics_panel = DiagnosticsPanelQt(
            diagnostics_widget,
            None,  # No control queue needed
            self._log_message,
            padding=6
        )
        layout.addWidget(self.diagnostics_panel)
        
        # Add tab - store index for visibility optimization
        tab_index = self.tab_widget.addTab(diagnostics_widget, "📊 Diagnostics")
        
        # Store tab index to check visibility later for performance optimization
        self.diagnostics_tab_index = tab_index

    def create_camera_tab(self):
        """Create the Camera Tracking tab."""
        camera_widget = QWidget()
        layout = QVBoxLayout(camera_widget)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Camera Panel with control queue and preview handling
        # Note: `translation_display_queue` and `camera_preview_queue` may be None
        # if not provided; TabbedGUIWorker will set attributes earlier in __init__.
        self.camera_panel = CameraPanelQt(
            camera_widget,
            control_queue=getattr(self, 'camera_control_queue', None),
            message_callback=self._log_message,
            preview_queue=getattr(self, 'camera_preview_queue', None),
            padding=6
        )
        layout.addWidget(self.camera_panel)

        # Allow calibration panel to control/latch camera origin and update camera UI.
        try:
            if hasattr(self, 'calibration_panel'):
                # provide a direct reference and control queue so reset can affect camera panel
                self.calibration_panel.camera_panel = self.camera_panel
                self.calibration_panel.camera_control_queue = getattr(self, 'camera_control_queue', None)
        except Exception:
            pass

        self.tab_widget.addTab(camera_widget, "🎥 Camera")

    def create_messages_tab(self):
        """Create the Messages tab with serial monitor and application logs."""
        messages_widget = QWidget()
        layout = QVBoxLayout(messages_widget)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Message Panel (full-sized in its own tab)
        self.message_panel = MessagePanelQt(
            messages_widget,
            serial_height=12,  # Larger in dedicated tab
            message_height=12,  # Larger in dedicated tab
            max_serial_lines=500,  # More history in dedicated tab
            max_message_lines=200,  # More history in dedicated tab
            padding=6
        )
        layout.addWidget(self.message_panel)
        
        # Add tab
        self.tab_widget.addTab(messages_widget, "📜 Messages")
    
    def create_preferences_tab(self):
        """Create the Preferences tab."""
        preferences_widget = QWidget()
        layout = QVBoxLayout(preferences_widget)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Preferences Panel
        self.preferences_panel = PreferencesPanel(
            preferences_widget,
            self.preferences_manager,
            self.input_command_queue,
            self.input_response_queue
        )
        
        # Connect preferences panel to calibration panel for shortcuts
        self.preferences_panel.connect_calibration_panel(self.calibration_panel)
        
        # Connect calibration panel to preferences panel for sample counts
        self.calibration_panel.connect_preferences_panel(self.preferences_panel)
        
        # Connect theme change signal
        self.preferences_panel.theme_changed.connect(self._apply_theme)
        self.preferences_panel.preferences_changed.connect(self.save_preferences)
        
        layout.addWidget(self.preferences_panel, 1)
        
        # Add tab
        self.tab_widget.addTab(preferences_widget, "⚙️ Preferences")
    
    def _apply_theme(self, theme_name):
        """Apply the selected theme to the application."""
        try:
            # Prevent duplicate theme application during startup
            if hasattr(self, '_theme_applied') and self._theme_applied == theme_name:
                return
            self._theme_applied = theme_name
            
            self.theme_manager.load_theme(theme_name)
            print(f"[GUI] Applied theme: {theme_name}")
        except Exception as e:
            print(f"[GUI] Error applying theme {theme_name}: {e}")
    
    def _on_tab_changed(self, index):
        """Handle tab changes to optimize performance by skipping diagnostics updates when not visible."""
        # Log tab changes for debugging (diagnostics updates are now visibility-checked)
        if hasattr(self, 'diagnostics_tab_index'):
            if index == self.diagnostics_tab_index:
                print("[GUI] Diagnostics tab selected - matplotlib updates enabled")
            else:
                print("[GUI] Diagnostics tab not selected - matplotlib updates skipped")
    
    def create_about_tab(self):
        """Create the About tab."""
        about_panel = AboutPanel()
        self.tab_widget.addTab(about_panel, "About")
    
    def _connect_signals(self):
        """Connect internal signals to update methods."""
        self.signals.status_update.connect(self._update_status_bar)
        self.signals.orientation_update.connect(self._update_orientation)
        self.signals.drift_status_update.connect(self._update_drift_status)
    
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
        try:
            # Process euler display queue for real-time orientation updates
            if self.euler_display_queue:
                euler_count = 0
                latest_euler = None
                # Drain queue to get most recent data for real-time performance
                while euler_count < 100 and not self.euler_display_queue.empty():
                    try:
                        euler_data = self.euler_display_queue.get_nowait()
                        if isinstance(euler_data, (list, tuple)) and len(euler_data) >= 6:
                            latest_euler = euler_data
                        elif isinstance(euler_data, (list, tuple)) and len(euler_data) >= 3:
                            latest_euler = euler_data
                        euler_count += 1
                    except:
                        break
                
                # Update display with most recent data only
                if latest_euler:
                    if len(latest_euler) >= 6:
                        # Data format from fusion worker: [yaw, pitch, roll, x, y, z]
                        yaw, pitch, roll = latest_euler[0], latest_euler[1], latest_euler[2]
                        x, y, z = latest_euler[3], latest_euler[4], latest_euler[5]
                        
                        # Update orientation display immediately for real-time response
                        if hasattr(self.orientation_panel, 'update_euler'):
                            self.orientation_panel.update_euler(yaw, pitch, roll)
                        
                        # Update diagnostics panel with orientation data (only if tab is active)
                        if (hasattr(self, 'diagnostics_tab_index') and 
                            self.tab_widget.currentIndex() == self.diagnostics_tab_index and
                            hasattr(self.diagnostics_panel, 'update_euler')):
                            self.diagnostics_panel.update_euler(yaw, pitch, roll)
                        
                        # Update position display immediately
                        if hasattr(self.orientation_panel, 'update_position'):
                            self.orientation_panel.update_position(x, y, z)

                        # Camera translation updates (position from camera worker)
                        if hasattr(self, 'translation_display_queue') and self.translation_display_queue:
                            try:
                                cam_count = 0
                                latest_cam = None
                                while cam_count < 50 and not self.translation_display_queue.empty():
                                    try:
                                        item = self.translation_display_queue.get_nowait()
                                        latest_cam = item
                                        cam_count += 1
                                    except:
                                        break
                                if latest_cam is not None and hasattr(self, 'camera_panel'):
                                    # Handle pixel messages from camera worker
                                    try:
                                        if isinstance(latest_cam, (list, tuple)) and len(latest_cam) >= 1 and isinstance(latest_cam[0], str):
                                            if latest_cam[0] == '_CAM_DATA_' and len(latest_cam) >= 6:
                                                try:
                                                    sx, sy, sz, px, py = latest_cam[1], latest_cam[2], latest_cam[3], latest_cam[4], latest_cam[5]
                                                    if hasattr(self, 'camera_panel'):
                                                        try:
                                                            # Update mapped position and pixel coords
                                                            if hasattr(self.camera_panel, 'update_position'):
                                                                try:
                                                                    self.camera_panel.update_position(sx, sy, sz)
                                                                except Exception:
                                                                    pass
                                                            if hasattr(self.camera_panel, 'update_pixel_position'):
                                                                try:
                                                                    self.camera_panel.update_pixel_position(px, py)
                                                                except Exception:
                                                                    pass
                                                        except Exception:
                                                            pass
                                                except Exception:
                                                    pass
                                            elif isinstance(latest_cam, (list, tuple)) and len(latest_cam) >= 3:
                                                x, y, z = latest_cam[0], latest_cam[1], latest_cam[2]
                                                try:
                                                    self.camera_panel.update_position(x, y, z)
                                                except Exception:
                                                    pass
                                        elif isinstance(latest_cam, (list, tuple)) and len(latest_cam) >= 3:
                                            x, y, z = latest_cam[0], latest_cam[1], latest_cam[2]
                                            try:
                                                self.camera_panel.update_position(x, y, z)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    elif len(latest_euler) >= 3:
                        # Fallback for orientation-only data
                        yaw, pitch, roll = latest_euler[0], latest_euler[1], latest_euler[2]
                        if hasattr(self.orientation_panel, 'update_euler'):
                            self.orientation_panel.update_euler(yaw, pitch, roll)
                        
                        # Update diagnostics panel with orientation data (only if tab is active)
                        if (hasattr(self, 'diagnostics_tab_index') and 
                            self.tab_widget.currentIndex() == self.diagnostics_tab_index and
                            hasattr(self.diagnostics_panel, 'update_euler')):
                            self.diagnostics_panel.update_euler(yaw, pitch, roll)
            
            # Process status updates (check if queue exists and not None)
            if self.status_queue:
                status_count = 0
                while status_count < 20 and not self.status_queue.empty():
                    try:
                        item = self.status_queue.get_nowait()
                        if isinstance(item, tuple) and len(item) >= 2:
                            # Handle tuple format from fusion worker: ('status_type', value)
                            status_type, value = item[0], item[1]
                            self._handle_status_update(status_type, value)
                        elif isinstance(item, dict):
                            if 'section' in item and 'message' in item:
                                self.signals.status_update.emit(item['section'], item['message'])
                            elif 'orientation' in item:
                                # Orientation update from fusion worker
                                euler = item['orientation']
                                if len(euler) >= 3:
                                    # Data format: [yaw, pitch, roll] - emit in correct order
                                    yaw, pitch, roll = euler[0], euler[1], euler[2]
                                    self.signals.orientation_update.emit(roll, pitch, yaw)
                            elif 'position' in item:
                                # Position updates removed with camera functionality
                                pass
                            elif 'drift_status' in item:
                                self.signals.drift_status_update.emit(item['drift_status'])
                            elif 'preview_data' in item:
                                    # Camera preview data (forward to camera panel)
                                    try:
                                        if hasattr(self, 'camera_panel') and isinstance(item['preview_data'], (bytes, bytearray)):
                                            try:
                                                self.camera_panel.update_preview(item['preview_data'])
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                        elif isinstance(item, str):
                            # Simple string status
                            self.signals.status_update.emit('general', item)
                        status_count += 1
                    except:
                        break
                        
            # Process UI status updates (dedicated queue for UI state changes)
            if self.ui_status_queue:
                ui_status_count = 0
                while ui_status_count < 20 and not self.ui_status_queue.empty():
                    try:
                        item = self.ui_status_queue.get_nowait()
                        if isinstance(item, tuple) and len(item) >= 2:
                            # Handle tuple format: ('status_type', value)
                            status_type, value = item[0], item[1]
                            self._handle_ui_status_update(status_type, value)
                        ui_status_count += 1
                    except:
                        break
        except Exception as e:
            # Silently handle queue processing errors to avoid spam
            pass
        
        # Process message queue
        if self.message_queue:
            msg_count = 0
            while msg_count < 30 and not self.message_queue.empty():
                try:
                    msg = self.message_queue.get_nowait()
                    if isinstance(msg, str) and hasattr(self.message_panel, 'append_message'):
                        self.message_panel.append_message(msg)
                    msg_count += 1
                except:
                    break
            
            # Update displays if we processed any messages
            if msg_count > 0 and hasattr(self.message_panel, 'update_displays'):
                self.message_panel.update_displays()
    
    def _update_status_bar(self, section: str, message: str):
        """Update the status bar with new information."""
        # For QStatusBar, we'll show the most recent message
        # You could extend this to show multiple sections if needed
        print(f"[{section}] {message}")
    
    def _update_orientation(self, roll: float, pitch: float, yaw: float):
        """Update orientation display."""
        if hasattr(self.orientation_panel, 'update_euler'):
            self.orientation_panel.update_euler(yaw, pitch, roll)
        
        # Update diagnostics panel with orientation data (only if tab is active)
        if (hasattr(self, 'diagnostics_tab_index') and 
            self.tab_widget.currentIndex() == self.diagnostics_tab_index and
            hasattr(self.diagnostics_panel, 'update_euler')):
            self.diagnostics_panel.update_euler(yaw, pitch, roll)
    
    # Position update functionality removed
    
    def _update_drift_status(self, status):
        """Update drift status display."""
        if hasattr(self.orientation_panel, 'update_drift_status'):
            # Convert string to boolean for drift correction status
            if isinstance(status, bool):
                active = status
            else:
                # Handle string status from older code paths
                active = 'active' in str(status).lower() or 'true' in str(status).lower()
            self.orientation_panel.update_drift_status(active)
    
    # Camera preview functionality removed
    
    def _handle_status_update(self, status_type: str, value):
        """Handle specific status updates from workers."""
        if status_type == 'processing':
            # Update both serial panel and calibration panel with fusion processing status
            is_active = (value == 'active')
            if hasattr(self.serial_panel, 'update_fusion_status'):
                self.serial_panel.update_fusion_status(is_active)
            if hasattr(self.calibration_panel, 'update_processing_status'):
                self.calibration_panel.update_processing_status(value)
        elif status_type == 'serial_connection':
            # Update serial panel with connection status
            if hasattr(self.serial_panel, 'update_connection_status'):
                self.serial_panel.update_connection_status(value)
        elif status_type == 'serial_data':
            # Update serial panel with data activity
            if hasattr(self.serial_panel, 'update_data_activity') and value:
                self.serial_panel.update_data_activity()
        # Add other status types as needed
    
    def _handle_ui_status_update(self, status_type: str, value):
        """Handle UI-specific status updates from workers."""
        if status_type == 'processing':
            # Update both serial panel and calibration panel with fusion processing status
            is_active = (value == 'active')
            if hasattr(self.serial_panel, 'update_fusion_status'):
                self.serial_panel.update_fusion_status(is_active)
            if hasattr(self.calibration_panel, 'update_processing_status'):
                self.calibration_panel.update_processing_status(value)
            
            # Control hold panel blinking based on fusion processing status
            if hasattr(self.hold_panel, 'stop_blinking') and is_active:
                self.hold_panel.stop_blinking()  # Stop blinking when fusion is active
        elif status_type == 'serial_connection':
            # Update serial panel with connection status
            if hasattr(self.serial_panel, 'update_connection_status'):
                self.serial_panel.update_connection_status(value)
            
            # Update calibration panel with serial connection status
            if hasattr(self.calibration_panel, 'update_serial_connection_status'):
                self.calibration_panel.update_serial_connection_status(value)
            
            # Control hold panel blinking based on connection status
            if hasattr(self.hold_panel, 'start_blinking') and value == 'connected':
                self.hold_panel.start_blinking()  # Start blinking when connected but waiting for data
            elif hasattr(self.hold_panel, 'stop_blinking') and value in ['stopped', 'error']:
                self.hold_panel.stop_blinking()  # Stop blinking when disconnected or error
            
            # When serial is disconnected/stopped, clear calibration state and reset status bar
            if value in ['stopped', 'disconnected', 'error']:
                if hasattr(self.calibration_panel, 'clear_calibration_state'):
                    self.calibration_panel.clear_calibration_state()
                
                # Reset message rate in status bar when serial stops
                if hasattr(self.status_bar, 'update_message_rate'):
                    self.status_bar.update_message_rate(0.0)
        elif status_type == 'camera_crashed':
            # value is exitcode; disable camera panel controls and notify user
            try:
                if hasattr(self, 'camera_panel'):
                    try:
                        self.camera_panel.preview_btn.setEnabled(False)
                        self.camera_panel.track_btn.setEnabled(False)
                        self.camera_panel.preview_label.setText('Camera unavailable')
                    except Exception:
                        pass
                # also emit a status update to message panel
                try:
                    self.signals.status_update.emit('camera', f'Camera worker crashed (code {value})')
                except Exception:
                    pass
            except Exception:
                pass
        elif status_type == 'serial_data':
            # Update serial panel with data activity
            if hasattr(self.serial_panel, 'update_data_activity') and value:
                self.serial_panel.update_data_activity()
        # Add other UI status types as needed
    
    def update_gui_elements(self):
        """Periodic GUI updates for display queues only (non-real-time data)."""
        try:
            # Process serial display queue for message panel
            if self.serial_display_queue:
                serial_count = 0
                while serial_count < 30 and not self.serial_display_queue.empty():
                    try:
                        serial_data = self.serial_display_queue.get_nowait()
                        if hasattr(self.message_panel, 'append_serial'):
                            self.message_panel.append_serial(str(serial_data))
                        serial_count += 1
                    except:
                        break
                
                # Update displays if we processed any serial data
                if serial_count > 0 and hasattr(self.message_panel, 'update_displays'):
                    self.message_panel.update_displays()
            
            # Camera preview queue handling (non-real-time, small queue)
            if hasattr(self, 'camera_preview_queue') and self.camera_preview_queue:
                try:
                    latest = None
                    cnt = 0
                    while cnt < 8 and not self.camera_preview_queue.empty():
                        try:
                            item = self.camera_preview_queue.get_nowait()
                            latest = item
                            cnt += 1
                        except:
                            break
                    if latest is not None and hasattr(self, 'camera_panel'):
                        # preview items are (jpg_bytes, timestamp)
                        jpg = latest[0] if isinstance(latest, (list, tuple)) and len(latest) > 0 else latest
                        try:
                            self.camera_panel.update_preview(jpg)
                        except Exception:
                            pass
                except Exception:
                    pass
            # Note: Euler/orientation updates moved to process_queues() for real-time performance
                        
        except Exception as e:
            # Silently handle display queue errors to avoid spam
            pass
    
    def _handle_status_update(self, status_type: str, value):
        """Handle status updates from workers."""
        try:
            if status_type == 'gyro_calibrated' and hasattr(self.calibration_panel, 'update_calibration_status'):
                self.calibration_panel.update_calibration_status(bool(value))
            elif status_type == 'gyro_calibrating' and hasattr(self.calibration_panel, 'update_calibrating_status'):
                self.calibration_panel.update_calibrating_status(bool(value))
                
                # Control hold panel blinking during gyro calibration
                if hasattr(self.hold_panel, 'start_blinking') and bool(value):
                    self.hold_panel.start_blinking()  # Start blinking when calibration starts
                elif hasattr(self.hold_panel, 'stop_blinking') and not bool(value):
                    self.hold_panel.stop_blinking()  # Stop blinking when calibration finishes
            elif status_type == 'processing' and hasattr(self.calibration_panel, 'update_processing_status'):
                self.calibration_panel.update_processing_status(str(value))
            elif status_type == 'drift_correction' and hasattr(self.orientation_panel, 'update_drift_status'):
                self.orientation_panel.update_drift_status(bool(value))
            elif status_type == 'msg_rate' and hasattr(self.status_bar, 'update_message_rate'):
                self.status_bar.update_message_rate(float(value))
            elif status_type == 'send_rate' and hasattr(self.status_bar, 'update_send_rate'):
                self.status_bar.update_send_rate(float(value))
            elif status_type == 'cam_fps' and hasattr(self.status_bar, 'update_camera_fps'):
                try:
                    self.status_bar.update_camera_fps(float(value))
                except Exception:
                    pass
            elif status_type == 'stationary' and hasattr(self.status_bar, 'update_device_status'):
                self.status_bar.update_device_status(bool(value))
            elif status_type == 'serial_connection' and hasattr(self.serial_panel, 'update_connection_status'):
                self.serial_panel.update_connection_status(str(value))
            elif status_type == 'serial_data' and hasattr(self.serial_panel, 'update_data_activity'):
                self.serial_panel.update_data_activity()
            elif status_type == 'filter_type':
                # Filter type change acknowledgment from fusion worker
                if hasattr(self.orientation_panel, 'filter_combo'):
                    try:
                        self.orientation_panel.filter_combo.setCurrentText(str(value))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[GUI] Error handling status update {status_type}: {e}")
    
    def _log_message(self, message: str):
        """Log a message to the message panel."""
        if hasattr(self.message_panel, 'append_message'):
            self.message_panel.append_message(message)
            # Update displays immediately for direct log calls
            if hasattr(self.message_panel, 'update_displays'):
                self.message_panel.update_displays()
    
    def _finalize_window_size(self):
        """Set initial window size to the central widget's sizeHint (small),
        then apply that as the minimum size so it opens compact and grows only as needed.
        """
        # Ensure layouts are up to date
        self.adjustSize()

        # Prefer the minimumSizeHint (smaller, required minimum for content)
        hint = self.centralWidget().minimumSizeHint()
        if hint.isEmpty():
            hint = self.centralWidget().sizeHint()

        # Small decoration padding to account for window chrome (kept minimal)
        target_w = max(700, hint.width() + 8)  # Increased minimum from 200 to 500
        target_h = max(240, hint.height() + 20)

        # Constrain initial width to avoid extremely wide default
        max_width = 600
        target_w = min(target_w, max_width)

        # Resize to the target and make it the minimum start size
        self.resize(target_w, target_h)
        self.setMinimumSize(target_w, target_h)

        # Allow immediate resizing by the user (no temporary maximum lock)
        QTimer.singleShot(50, self._enable_resizing)
    
    def _enable_resizing(self):
        """Remove maximum size constraint to allow user resizing while preserving minimum size."""
        # Remove maximum size constraint but keep minimum size
        self.setMaximumSize(16777215, 16777215)  # Qt's default maximum size
    
    def load_preferences(self):
        """Load saved preferences for all panels."""
        try:
            prefs_manager = PreferencesManager()
            prefs = prefs_manager.load()
            
            # Handle both dict and string formats for preferences
            if isinstance(prefs, str):
                print(f"[GUI] Preferences returned as string, skipping load")
                return
            
            if not isinstance(prefs, dict):
                print(f"[GUI] Unexpected preferences format: {type(prefs)}")
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
            
            if hasattr(self.diagnostics_panel, 'set_prefs') and 'diagnostics' in prefs:
                self.diagnostics_panel.set_prefs(prefs['diagnostics'])

            # Camera panel preferences (if present)
            if hasattr(self, 'camera_panel') and 'camera' in prefs and hasattr(self.camera_panel, 'set_prefs'):
                try:
                    self.camera_panel.set_prefs(prefs['camera'])
                except Exception:
                    pass
            
            # Load preferences for the preferences panel itself
            if hasattr(self.preferences_panel, 'load_preferences'):
                self.preferences_panel.load_preferences()
            
            # Apply theme preference
            if hasattr(self, 'preferences_manager'):
                theme_name = self.preferences_manager.get_theme()
                self._apply_theme(theme_name)
            
            # Restore tab selection
            if 'gui' in prefs and isinstance(prefs['gui'], dict) and 'selected_tab' in prefs['gui']:
                try:
                    tab_index = int(prefs['gui']['selected_tab'])
                    if 0 <= tab_index < self.tab_widget.count():
                        self.tab_widget.setCurrentIndex(tab_index)
                except (ValueError, TypeError):
                    pass
            
            print("[GUI] Preferences loaded")
            
        except Exception as e:
            print(f"[GUI] Error loading preferences: {e}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        print("[GUI] Close event received")
        
        # Stop running timers to prevent callbacks into deleted widgets
        for tname in ('update_timer', 'gui_timer', 'process_timer'):
            try:
                timer = getattr(self, tname, None)
                if timer:
                    timer.stop()
            except Exception:
                pass

        # Stop diagnostics panel updates if present
        try:
            if hasattr(self, 'diagnostics_panel') and getattr(self.diagnostics_panel, 'plot_timer', None):
                try:
                    self.diagnostics_panel.plot_timer.stop()
                except Exception:
                    pass
        except Exception:
            pass

        # Cleanup calibration panel resources (threads) before saving preferences
        if hasattr(self.calibration_panel, 'cleanup'):
            try:
                self.calibration_panel.cleanup()
            except Exception:
                pass

        # Save preferences before closing (do this while panels still exist)
        try:
            self.save_preferences()
        except Exception:
            pass

        # Remove cross-panel references to avoid accessing deleted C++ wrappers
        try:
            if hasattr(self, 'orientation_panel') and hasattr(self.orientation_panel, 'calibration_panel'):
                try:
                    self.orientation_panel.calibration_panel = None
                except Exception:
                    pass
            if hasattr(self, 'preferences_panel') and hasattr(self.preferences_panel, 'calibration_panel'):
                try:
                    self.preferences_panel.calibration_panel = None
                except Exception:
                    pass
            # Finally drop our own reference
            try:
                self.calibration_panel = None
            except Exception:
                pass
        except Exception:
            pass
        
        # Give threads time to cleanup
        QApplication.processEvents()
        
        # Call stop callback if provided
        try:
            if callable(self.on_stop_callback):
                self.on_stop_callback()
        except Exception:
            pass
        
        # Set stop event
        if self.stop_event:
            self.stop_event.set()
        
        event.accept()
    
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
            
            if hasattr(self.diagnostics_panel, 'get_prefs'):
                prefs['diagnostics'] = self.diagnostics_panel.get_prefs()
            
            # Camera panel preferences
            if hasattr(self, 'camera_panel') and hasattr(self.camera_panel, 'get_prefs'):
                try:
                    prefs['camera'] = self.camera_panel.get_prefs()
                except Exception:
                    pass
            
            # Get shortcut preferences from preferences panel
            if hasattr(self.preferences_panel, 'get_shortcut_preferences'):
                shortcut_prefs = self.preferences_panel.get_shortcut_preferences()
                if 'calibration' not in prefs:
                    prefs['calibration'] = {}
                prefs['calibration'].update(shortcut_prefs)
            
            # Get shortcut preferences from preferences panel
            if hasattr(self.preferences_panel, 'get_shortcut_preferences'):
                shortcut_prefs = self.preferences_panel.get_shortcut_preferences()
                if 'calibration' not in prefs:
                    prefs['calibration'] = {}
                prefs['calibration'].update(shortcut_prefs)
            
            # Save GUI state
            prefs['gui'] = {
                'selected_tab': str(self.tab_widget.currentIndex()),
                'theme': self.theme_manager.get_current_theme()
            }
            
            # Save to preferences
            prefs_manager = PreferencesManager()
            prefs_manager.save(prefs)
            
            print("[GUI] Preferences saved")
            
        except Exception as e:
            print(f"[GUI] Error saving preferences: {e}")


def start_gui_worker(serial_control_queue, fusion_control_queue,
                     udp_control_queue, status_queue, ui_status_queue, message_queue,
                     serial_display_queue=None, euler_display_queue=None,
                     camera_control_queue=None, translation_display_queue=None, camera_preview_queue=None,
                 log_queue=None, stop_event=None, on_stop_callback=None,
                 input_command_queue=None, input_response_queue=None):
    """
    Start the PyQt5 GUI worker with tabbed interface.
    
    Args:
        serial_control_queue: Queue for serial worker commands
        fusion_control_queue: Queue for fusion worker commands  
        udp_control_queue: Queue for UDP worker commands
        status_queue: Queue for receiving status updates
        ui_status_queue: Queue for receiving UI-specific status updates
        message_queue: Queue for receiving messages
        serial_display_queue: Queue for raw serial data display
        euler_display_queue: Queue for orientation angles
        log_queue: Queue for log messages
        stop_event: Threading event for shutdown coordination
        on_stop_callback: Callback when GUI is closed
        input_command_queue: Queue for sending commands to input worker
        input_response_queue: Queue for receiving responses from input worker
    """
    # Create or get QApplication instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Set application icon
    try:
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'img', 'icon.ico'))
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            if not app_icon.isNull():
                app.setWindowIcon(app_icon)
                print(f"[GUI] Application icon set: {icon_path}")
            else:
                print(f"[GUI] Failed to load icon: {icon_path}")
        else:
            print("[GUI] No icon file found")
            
    except Exception as e:
        print(f"[GUI] Could not set application icon: {e}")
    
    # Windows-specific taskbar icon handling
    try:
        import platform
        if platform.system() == "Windows":
            import ctypes
            # Set the app ID for proper taskbar grouping
            app_id = f"frankentrack.{APP_NAME}.{APP_VERSION}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            print(f"[GUI] Windows AppUserModelID set: {app_id}")
    except Exception as e:
        print(f"[GUI] Could not set Windows app ID: {e}")
    
    # Create main window
    main_window = TabbedGUIWorker(
        serial_control_queue=serial_control_queue,
        fusion_control_queue=fusion_control_queue,
        udp_control_queue=udp_control_queue,
        status_queue=status_queue,
        ui_status_queue=ui_status_queue,
        message_queue=message_queue,
        serial_display_queue=serial_display_queue,
        euler_display_queue=euler_display_queue,
        camera_control_queue=camera_control_queue,
        translation_display_queue=translation_display_queue,
        camera_preview_queue=camera_preview_queue,
        log_queue=log_queue,
        stop_event=stop_event,
        on_stop_callback=on_stop_callback,
        input_command_queue=input_command_queue,
        input_response_queue=input_response_queue
    )
    
    # Show window
    main_window.show()
    
    print("[GUI] Started")
    
    # Run event loop
    app.exec_()
    
    print("[GUI] PyQt5 tabbed GUI stopped")


def run_worker(messageQueue, serialDisplayQueue, statusQueue, stop_event, 
               eulerDisplayQueue, controlQueue, serialControlQueue, 
               udpControlQueue, logQueue, uiStatusQueue, cameraControlQueue, translationDisplayQueue, cameraPreviewQueue, inputCommandQueue, inputResponseQueue):
    """
    Compatibility wrapper for the process manager.
    
    This function maintains the same interface as the original launcher
    to ensure compatibility with the existing process manager.
    Camera functionality has been removed.
    """
    start_gui_worker(
        serial_control_queue=serialControlQueue,
        fusion_control_queue=controlQueue,
        udp_control_queue=udpControlQueue,
        status_queue=statusQueue,
        ui_status_queue=uiStatusQueue,
        message_queue=messageQueue,
        serial_display_queue=serialDisplayQueue,
        euler_display_queue=eulerDisplayQueue,
        camera_control_queue=cameraControlQueue,
        translation_display_queue=translationDisplayQueue,
        camera_preview_queue=cameraPreviewQueue,
        log_queue=logQueue,
        stop_event=stop_event,
        input_command_queue=inputCommandQueue,
        input_response_queue=inputResponseQueue,
        on_stop_callback=lambda: stop_event.set()
    )


if __name__ == "__main__":
    # Test the tabbed GUI independently
    print("Testing PyQt5 Tabbed GUI...")
    
    # Create mock queues
    import queue
    import threading
    
    test_queues = {
        'serial': queue.Queue(),
        'fusion': queue.Queue(),
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
        udp_control_queue=test_queues['udp'],
        status_queue=test_queues['status'],
        message_queue=test_queues['message'],
        stop_event=stop_event,
        on_stop_callback=test_stop
    )