"""
PyQt Camera control panel for camera preview, enumeration, and position tracking.

This panel handles:
- Camera preview display using QLabel with QPixmap
- Camera enumeration using QThread for background processing
- Camera/FPS/Resolution selection with QComboBox
- Preview enable/disable toggle
- Position tracking start/stop
- Detection threshold slider with QTimer debouncing
- Options dialog for threshold/exposure/gain controls
"""

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QSlider, QFrame, QDialog, QApplication
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QPixmap, QIcon
import threading
from typing import Optional

from config.config import (
    PREVIEW_WIDTH, PREVIEW_HEIGHT,
    DEFAULT_CAMERA_FPS, DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT,
    DEFAULT_DETECTION_THRESHOLD, THRESH_DEBOUNCE_MS,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put
from workers.gui.managers.preferences_manager import PreferencesManager

try:
    from PIL import Image
    import io
except ImportError:
    Image = None
    io = None


class CameraEnumerationThread(QThread):
    """Background thread for camera enumeration to avoid blocking GUI."""
    
    cameras_found = pyqtSignal(list)  # Signal emitted when cameras are found
    enumeration_finished = pyqtSignal()  # Signal emitted when enumeration is complete
    
    def __init__(self, max_checks=32, backend='openCV', parent=None):
        super().__init__(parent)
        self.max_checks = max_checks
        self.backend = backend
        
    def run(self):
        """Run camera enumeration in background thread."""
        cams = []
        
        # If backend is pseyepy, try using its cam_count() helper first
        try:
            if self.backend == 'pseyepy' or 'pseyepy' in self.backend.lower():
                try:
                    import pseyepy
                    n = 0
                    try:
                        # pseyepy.cam_count() typically returns number of attached PS3Eye cameras
                        n = int(pseyepy.cam_count())
                    except Exception:
                        # Some pseyepy builds may expose different API names; try cameras()
                        try:
                            n = int(len(pseyepy.cameras()))
                        except Exception:
                            n = 0
                    if n > 0:
                        cams = [f"Camera {i}" for i in range(n)]
                        self.cameras_found.emit(cams)
                        self.enumeration_finished.emit()
                        return
                except Exception:
                    # Fall back to OpenCV probe if pseyepy import or cam_count fails
                    pass
        except Exception:
            pass

        # Try importing opencv as a fallback
        try:
            import cv2
        except ImportError:
            cv2 = None

        if cv2 is None:
            # Use default camera list
            cams = ["Camera 0", "Camera 1", "Camera 2"]
            self.cameras_found.emit(cams)
            self.enumeration_finished.emit()
            return

        # Probe each camera index using OpenCV
        for i in range(self.max_checks):
            cap = None
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    # Try reading a frame to confirm it's a real camera
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        cams.append(f"Camera {i}")
            except Exception:
                pass
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        
        # Emit results
        if cams:
            self.cameras_found.emit(cams)
        else:
            self.cameras_found.emit(["Camera 0"])
        self.enumeration_finished.emit()


class CameraOptionsDialog(QDialog):
    """Modal dialog for camera threshold, exposure, and gain settings."""
    
    def __init__(self, thresh_var, exposure_var, gain_var, camera_control_queue, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Camera Options')
        self.setModal(True)
        self.setFixedSize(320, 200)
        
        self.thresh_var = thresh_var
        self.exposure_var = exposure_var
        self.gain_var = gain_var
        self.camera_control_queue = camera_control_queue
        self._thresh_send_job = None
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Build the options dialog layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Detection threshold
        thresh_frame = QFrame()
        thresh_layout = QHBoxLayout(thresh_frame)
        thresh_layout.setContentsMargins(0, 0, 0, 0)
        thresh_layout.addWidget(QLabel('Detection Threshold:'))
        
        self.thresh_slider = QSlider(Qt.Horizontal)
        self.thresh_slider.setRange(0, 255)
        self.thresh_slider.setValue(self.thresh_var)
        self.thresh_slider.setMinimumWidth(160)
        self.thresh_slider.valueChanged.connect(self._on_thresh_change)
        thresh_layout.addWidget(self.thresh_slider)
        
        self.thresh_label = QLabel(str(self.thresh_var))
        self.thresh_label.setMinimumWidth(30)
        thresh_layout.addWidget(self.thresh_label)
        layout.addWidget(thresh_frame)
        
        # Exposure
        exposure_frame = QFrame()
        exposure_layout = QHBoxLayout(exposure_frame)
        exposure_layout.setContentsMargins(0, 0, 0, 0)
        exposure_layout.addWidget(QLabel('Exposure:'))
        
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(0, 255)
        self.exposure_slider.setValue(self.exposure_var)
        self.exposure_slider.setMinimumWidth(160)
        self.exposure_slider.valueChanged.connect(self._on_exposure_change)
        exposure_layout.addWidget(self.exposure_slider)
        
        self.exposure_label = QLabel(str(self.exposure_var))
        self.exposure_label.setMinimumWidth(30)
        exposure_layout.addWidget(self.exposure_label)
        layout.addWidget(exposure_frame)
        
        # Gain
        gain_frame = QFrame()
        gain_layout = QHBoxLayout(gain_frame)
        gain_layout.setContentsMargins(0, 0, 0, 0)
        gain_layout.addWidget(QLabel('Gain:'))
        
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 63)  # PS3Eye gain range: 0-63
        self.gain_slider.setValue(self.gain_var)
        self.gain_slider.setMinimumWidth(160)
        self.gain_slider.valueChanged.connect(self._on_gain_change)
        gain_layout.addWidget(self.gain_slider)
        
        self.gain_label = QLabel(str(self.gain_var))
        self.gain_label.setMinimumWidth(30)
        gain_layout.addWidget(self.gain_label)
        layout.addWidget(gain_frame)
        
        # Close button
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()
        
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addWidget(button_frame)
        
        # Setup timer for threshold debouncing
        self.thresh_timer = QTimer()
        self.thresh_timer.setSingleShot(True)
        self.thresh_timer.timeout.connect(self._apply_thresh)
        
    def _on_thresh_change(self, value):
        """Handle threshold slider changes with debouncing."""
        self.thresh_label.setText(str(value))
        self.thresh_var = value
        
        # Cancel pending threshold send and schedule new one
        self.thresh_timer.stop()
        self.thresh_timer.start(THRESH_DEBOUNCE_MS)
        
    def _apply_thresh(self):
        """Send threshold value to camera worker (called after debounce)."""
        safe_queue_put(
            self.camera_control_queue,
            ('set_thresh', self.thresh_var),
            timeout=QUEUE_PUT_TIMEOUT
        )
        
    def _on_exposure_change(self, value):
        """Handle exposure slider changes."""
        self.exposure_label.setText(str(value))
        self.exposure_var = value
        safe_queue_put(
            self.camera_control_queue,
            ('set_cam_setting', 'exposure', value),
            timeout=QUEUE_PUT_TIMEOUT
        )
        
    def _on_gain_change(self, value):
        """Handle gain slider changes."""
        self.gain_label.setText(str(value))
        self.gain_var = value
        safe_queue_put(
            self.camera_control_queue,
            ('set_cam_setting', 'gain', value),
            timeout=QUEUE_PUT_TIMEOUT
        )


class CameraPanelQt(QGroupBox):
    """PyQt Camera control panel for camera preview, enumeration, and position tracking."""

    def __init__(self, camera_control_queue, message_queue=None, parent=None):
        """
        Args:
            camera_control_queue: Queue for sending commands to camera worker
            message_queue: Optional queue for logging messages
            parent: Parent widget
        """
        super().__init__("Camera Control", parent)
        
        self.camera_control_queue = camera_control_queue
        self.message_queue = message_queue

        # Debug: print whether camera_control_queue is available
        try:
            print(f"[CameraPanelQt] camera_control_queue is {'set' if self.camera_control_queue is not None else 'None'}")
        except Exception:
            pass
        
        # State tracking
        self.preview_enabled = False
        self.pos_track_enabled = False
        self.cameras = ["Camera 0", "Camera 1", "Camera 2"]  # Default list
        # Per-backend cached enumerations (keys: 'openCV', 'pseyepy')
        self._cached_cameras = {
            'openCV': list(self.cameras),
            'pseyepy': []
        }
        self._current_preview_pixmap = None  # Store QPixmap reference
        
        # Persistent variables for preferences
        self.thresh_var = DEFAULT_DETECTION_THRESHOLD
        self.exposure_var = 0
        self.gain_var = 0
        
        # Enumeration thread
        self.enum_thread = None
        
        # Create UI elements
        self._create_widgets()
        
    def _create_widgets(self):
        """Build the camera control panel layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 12, 8, 8)

        # Top row: Backend + Enumerate button
        top_row = QFrame()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left: Backend selector
        backend_label = QLabel("Backend:")
        top_layout.addWidget(backend_label)
        
        self.backend_cb = QComboBox()
        self.backend_cb.addItems(['openCV', 'pseyepy (PS3Eye)'])
        self.backend_cb.setCurrentText('openCV')
        self.backend_cb.currentTextChanged.connect(self._on_backend_selected)
        top_layout.addWidget(self.backend_cb)
        
        top_layout.addStretch()
        
        # Right: Enumerate button
        self.enumerate_btn = QPushButton("Enumerate Cameras")
        self.enumerate_btn.clicked.connect(self._on_enumerate_clicked)
        top_layout.addWidget(self.enumerate_btn)
        
        layout.addWidget(top_row)

        # Camera row: Camera selector + Options button
        camera_row = QFrame()
        camera_layout = QHBoxLayout(camera_row)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        
        camera_label = QLabel("Camera:")
        camera_layout.addWidget(camera_label)
        
        self.camera_cb = QComboBox()
        self.camera_cb.addItems(self.cameras)
        self.camera_cb.currentTextChanged.connect(self._on_camera_selected)
        camera_layout.addWidget(self.camera_cb)
        
        camera_layout.addStretch()
        
        # Options button
        self.options_btn = QPushButton("Options")
        self.options_btn.clicked.connect(self._open_options_dialog)
        camera_layout.addWidget(self.options_btn)
        
        layout.addWidget(camera_row)

        # Preview canvas
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        preview_frame.setLineWidth(1)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(2, 2, 2, 2)
        
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_label.setMaximumSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_label.setStyleSheet("background-color: black;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self._draw_preview_disabled()
        preview_layout.addWidget(self.preview_label)
        
        layout.addWidget(preview_frame)

        # FPS / Resolution row
        params_row = QFrame()
        params_layout = QHBoxLayout(params_row)
        params_layout.setContentsMargins(0, 0, 0, 0)
        
        # Center the FPS/Resolution controls
        params_layout.addStretch()
        
        fps_label = QLabel("FPS:")
        params_layout.addWidget(fps_label)
        
        self.fps_cb = QComboBox()
        self.fps_cb.addItems(['15', '30', '60', '90', '120'])
        self.fps_cb.setCurrentText(str(DEFAULT_CAMERA_FPS))
        self.fps_cb.currentTextChanged.connect(self._on_cam_params_changed)
        params_layout.addWidget(self.fps_cb)
        
        res_label = QLabel("Resolution:")
        params_layout.addWidget(res_label)
        
        self.res_cb = QComboBox()
        self.res_cb.addItems(['320x240', '640x480', '1280x720', '1920x1080'])
        self.res_cb.setCurrentText(f"{DEFAULT_CAMERA_WIDTH}x{DEFAULT_CAMERA_HEIGHT}")
        self.res_cb.currentTextChanged.connect(self._on_cam_params_changed)
        params_layout.addWidget(self.res_cb)
        
        params_layout.addStretch()
        layout.addWidget(params_row)

        # Preview toggle button
        preview_btn_row = QFrame()
        preview_btn_layout = QHBoxLayout(preview_btn_row)
        preview_btn_layout.setContentsMargins(0, 0, 0, 0)
        preview_btn_layout.addStretch()
        
        self.preview_btn = QPushButton("Enable Preview")
        self.preview_btn.clicked.connect(self.toggle_preview)
        preview_btn_layout.addWidget(self.preview_btn)
        
        preview_btn_layout.addStretch()
        layout.addWidget(preview_btn_row)

        # Position tracking button
        pos_row = QFrame()
        pos_layout = QHBoxLayout(pos_row)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.addStretch()
        
        self.pos_btn = QPushButton("Start Position Tracking")
        self.pos_btn.clicked.connect(self.toggle_position_tracking)
        pos_layout.addWidget(self.pos_btn)
        
        pos_layout.addStretch()
        layout.addWidget(pos_row)
        
    def _open_options_dialog(self):
        """Open a modal Options dialog for threshold/exposure/gain."""
        dialog = CameraOptionsDialog(
            self.thresh_var,
            self.exposure_var,
            self.gain_var,
            self.camera_control_queue,
            self
        )
        result = dialog.exec_()
        
        # Update our variables with the dialog's current values
        if result == QDialog.Accepted:
            self.thresh_var = dialog.thresh_var
            self.exposure_var = dialog.exposure_var
            self.gain_var = dialog.gain_var
        
    def toggle_preview(self):
        """Toggle camera preview on/off."""
        self.preview_enabled = not self.preview_enabled
        if self.preview_enabled:
            self.preview_btn.setText("Disable Preview")
            ok = safe_queue_put(
                self.camera_control_queue,
                ('preview_on',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            try:
                print(f"[CameraPanelQt] Sent preview_on -> ok={ok}")
            except Exception:
                pass
            self._log_message("Preview enabled")
        else:
            self.preview_btn.setText("Enable Preview")
            ok = safe_queue_put(
                self.camera_control_queue,
                ('preview_off',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            try:
                print(f"[CameraPanelQt] Sent preview_off -> ok={ok}")
            except Exception:
                pass
            # Clear preview when disabled
            self._current_preview_pixmap = None
            self._draw_preview_disabled()
            self._log_message("Preview disabled")
    
    def toggle_position_tracking(self):
        """Toggle position tracking mode."""
        self.pos_track_enabled = not self.pos_track_enabled
        if self.pos_track_enabled:
            self.pos_btn.setText("Stop Position Tracking")
            safe_queue_put(
                self.camera_control_queue,
                ('start_pos',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            self._log_message(f"Position tracking started on {self.camera_cb.currentText()}")
            
            # Disable camera controls while tracking is active
            self.camera_cb.setEnabled(False)
            self.fps_cb.setEnabled(False)
            self.backend_cb.setEnabled(False)
            self.res_cb.setEnabled(False)
            self.enumerate_btn.setEnabled(False)
        else:
            self.pos_btn.setText("Start Position Tracking")
            safe_queue_put(
                self.camera_control_queue,
                ('stop_pos',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            self._log_message("Position tracking stopped")
            
            # Re-enable camera controls
            self.camera_cb.setEnabled(True)
            self.fps_cb.setEnabled(True)
            self.backend_cb.setEnabled(True)
            self.res_cb.setEnabled(True)
            self.enumerate_btn.setEnabled(True)
    
    def update_preview(self, jpeg_data: bytes):
        """Update the preview display with new JPEG image data.
        
        Args:
            jpeg_data: JPEG-encoded image bytes from camera worker
        """
        if not self.preview_enabled:
            return
        
        if Image is None or io is None:
            return
        
        try:
            # Convert JPEG bytes to PIL Image
            img = Image.open(io.BytesIO(jpeg_data))
            
            # Convert PIL Image to QPixmap
            img_data = img.tobytes("raw", "RGB")
            qimg = QImage(img_data, img.width, img.height, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            
            # Scale to fit preview area if needed
            if pixmap.width() > PREVIEW_WIDTH or pixmap.height() > PREVIEW_HEIGHT:
                pixmap = pixmap.scaled(
                    PREVIEW_WIDTH, PREVIEW_HEIGHT,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            
            # Store reference and update display
            self._current_preview_pixmap = pixmap
            self.preview_label.setPixmap(pixmap)
            
        except Exception as e:
            # Don't spam errors for preview updates
            pass

    def _draw_preview_disabled(self):
        """Draw preview disabled text on the preview label."""
        self.preview_label.clear()
        self.preview_label.setText("Preview disabled")
        self.preview_label.setStyleSheet("background-color: black; color: white; font-size: 14px;")
    
    def set_cameras(self, camera_list: list):
        """Update the list of available cameras.
        
        Args:
            camera_list: List of camera names/indices (e.g., ["Camera 0", "Camera 1"])
        """
        self.cameras = camera_list if camera_list else ["Camera 0"]
        
        # Update combobox
        current = self.camera_cb.currentText()
        self.camera_cb.clear()
        self.camera_cb.addItems(self.cameras)
        
        # Preserve selected camera if still available, otherwise select first
        if current in self.cameras:
            self.camera_cb.setCurrentText(current)
        else:
            self.camera_cb.setCurrentText(self.cameras[0])
    
    def _on_camera_selected(self, camera_text):
        """Handler for camera selection change."""
        # Parse camera index from combobox string (e.g., "Camera 9" -> 9)
        idx = 0
        try:
            parts = camera_text.rsplit(' ', 1)
            if len(parts) == 2:
                idx = int(parts[1])
            else:
                # Fallback: extract all digits
                digits = ''.join(ch for ch in camera_text if ch.isdigit())
                idx = int(digits) if digits else 0
        except Exception:
            try:
                idx = self.camera_cb.currentIndex()
            except Exception:
                idx = 0
        
        # Send selected camera index to camera worker
        safe_queue_put(
            self.camera_control_queue,
            ('set_cam', int(idx)),
            timeout=QUEUE_PUT_TIMEOUT
        )
        
        # Also send current camera params so new camera is initialized correctly
        self._on_cam_params_changed()
        
        self._log_message(f"Camera {idx} selected")
    
    def _on_cam_params_changed(self):
        """Send current FPS/resolution selection to camera worker."""
        try:
            fps = int(self.fps_cb.currentText())
        except Exception:
            fps = DEFAULT_CAMERA_FPS
        
        try:
            res = self.res_cb.currentText()
            parts = res.split('x')
            w = int(parts[0]) if len(parts) == 2 else DEFAULT_CAMERA_WIDTH
            h = int(parts[1]) if len(parts) == 2 else DEFAULT_CAMERA_HEIGHT
        except Exception:
            w, h = DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT
        
        safe_queue_put(
            self.camera_control_queue,
            ('set_cam_params', fps, w, h),
            timeout=QUEUE_PUT_TIMEOUT
        )

    def _on_backend_selected(self, backend_text):
        """Handler for backend selection change."""
        # Map display value to backend key used by camera worker
        key = 'pseyepy' if 'pseyepy' in backend_text.lower() else 'openCV'
        safe_queue_put(
            self.camera_control_queue,
            ('set_backend', key),
            timeout=QUEUE_PUT_TIMEOUT
        )
        self._log_message(f"Camera backend set to {backend_text}")

        # Update camera selector to use cached list for this backend (or a safe default)
        try:
            cams = self._cached_cameras.get(key, None)
            if cams and len(cams) > 0:
                self.set_cameras(list(cams))
            else:
                # clear to default single entry for this backend
                self.set_cameras(["Camera 0"])
        except Exception:
            pass
    
    def _on_enumerate_clicked(self):
        """Handler for 'Enumerate Cameras' button."""
        self.enumerate_btn.setEnabled(False)
        self._log_message("Camera enumeration started (this can take a minute)...")
        
        # Disable controls during enumeration
        self._disable_controls_for_enumeration()
        
        # Get current backend for enumeration
        backend_text = self.backend_cb.currentText()
        backend_key = 'pseyepy' if 'pseyepy' in backend_text.lower() else 'openCV'
        
        # Start enumeration thread
        self.enum_thread = CameraEnumerationThread(max_checks=32, backend=backend_key, parent=self)
        self.enum_thread.cameras_found.connect(self._on_cameras_found)
        self.enum_thread.enumeration_finished.connect(self._on_enumeration_finished)
        self.enum_thread.start()
    
    def _disable_controls_for_enumeration(self):
        """Disable all camera controls during enumeration."""
        self.preview_btn.setEnabled(False)
        self.enumerate_btn.setEnabled(False)
        self.camera_cb.setEnabled(False)
        self.fps_cb.setEnabled(False)
        self.backend_cb.setEnabled(False)
        self.res_cb.setEnabled(False)
        self.pos_btn.setEnabled(False)
    
    def _enable_controls_after_enumeration(self):
        """Re-enable camera controls after enumeration completes."""
        self.preview_btn.setEnabled(True)
        self.enumerate_btn.setEnabled(True)
        self.camera_cb.setEnabled(True)
        self.fps_cb.setEnabled(True)
        self.backend_cb.setEnabled(True)
        self.res_cb.setEnabled(True)
        self.pos_btn.setEnabled(True)
    
    def _on_cameras_found(self, camera_list):
        """Handle cameras found signal from enumeration thread."""
        if camera_list:
            # Cache under current backend
            try:
                backend_text = self.backend_cb.currentText()
                backend_key = 'pseyepy' if 'pseyepy' in backend_text.lower() else 'openCV'
                self._cached_cameras[backend_key] = list(camera_list)
            except Exception:
                pass
            self.set_cameras(camera_list)
            self._log_message(f"Found {len(camera_list)} camera(s)")
            # Persist updated per-backend camera enumeration immediately
            try:
                PreferencesManager().update(self.get_prefs())
            except Exception:
                pass
        else:
            self.set_cameras(["Camera 0"])
            self._log_message("No cameras found, using default")
    
    def _on_enumeration_finished(self):
        """Handle enumeration finished signal from thread."""
        self._enable_controls_after_enumeration()
    
    def _log_message(self, msg: str):
        """Send a message to the message queue if available.
        
        Args:
            msg: Message text to log
        """
        if self.message_queue is not None:
            safe_queue_put(self.message_queue, msg, timeout=QUEUE_PUT_TIMEOUT)
    
    def get_prefs(self) -> dict:
        """Get current camera preferences for persistence.
        
        Returns:
            Dictionary with camera, fps, resolution, threshold, and camera list
        """
        # Include per-backend cached camera lists so switching backends restores
        # the last-known enumeration for that backend.
        cams_opencv = ','.join(self._cached_cameras.get('openCV', []))
        cams_pseyepy = ','.join(self._cached_cameras.get('pseyepy', []))
        return {
            'camera': self.camera_cb.currentText(),
            'cameras': ','.join(self.cameras),
            'cameras_opencv': cams_opencv,
            'cameras_pseyepy': cams_pseyepy,
            'fps': self.fps_cb.currentText(),
            'resolution': self.res_cb.currentText(),
            'thresh': str(self.thresh_var),
            'exposure': str(self.exposure_var),
            'gain': str(self.gain_var),
            'backend': self.backend_cb.currentText(),
        }
    
    def set_prefs(self, prefs: dict):
        """Apply saved preferences to camera controls.
        
        Args:
            prefs: Dictionary with camera preferences
        """
        # Restore per-backend cached camera lists first
        try:
            cams_opencv_str = prefs.get('cameras_opencv', '')
            if cams_opencv_str:
                cam_list = [c.strip() for c in cams_opencv_str.split(',') if c.strip()]
                if cam_list:
                    self._cached_cameras['openCV'] = cam_list
        except Exception:
            pass
        try:
            cams_pseyepy_str = prefs.get('cameras_pseyepy', '')
            if cams_pseyepy_str:
                cam_list = [c.strip() for c in cams_pseyepy_str.split(',') if c.strip()]
                if cam_list:
                    self._cached_cameras['pseyepy'] = cam_list
        except Exception:
            pass

        # If an explicit generic 'cameras' key exists (legacy), use it for initial list
        cameras_str = prefs.get('cameras', '')
        if cameras_str and not any(self._cached_cameras.values()):
            cam_list = [c.strip() for c in cameras_str.split(',') if c.strip()]
            if cam_list:
                self.set_cameras(cam_list)
        
        # Remember saved selected camera and restore it after backend is applied
        saved_camera = prefs.get('camera')
        
        # Restore FPS
        fps = prefs.get('fps')
        if fps:
            self.fps_cb.setCurrentText(fps)
        
        # Restore resolution
        resolution = prefs.get('resolution')
        if resolution:
            self.res_cb.setCurrentText(resolution)
        
        # Restore threshold
        thresh = prefs.get('thresh')
        if thresh:
            try:
                self.thresh_var = int(thresh)
            except Exception:
                pass

        # Restore exposure and gain
        exposure = prefs.get('exposure')
        if exposure is not None:
            try:
                self.exposure_var = int(exposure)
                # send to worker so provider can apply if open
                safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'exposure', int(exposure)), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

        gain = prefs.get('gain')
        if gain is not None:
            try:
                self.gain_var = int(gain)
                safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'gain', int(gain)), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

        # Restore backend selection
        backend = prefs.get('backend')
        if backend:
            try:
                # If saved value is the worker key (e.g., 'pseyepy'), try to map to display
                if backend == 'pseyepy':
                    self.backend_cb.setCurrentText('pseyepy (PS3Eye)')
                else:
                    self.backend_cb.setCurrentText(backend)
            except Exception:
                pass

        # Send initial camera settings to worker
        # Notify backend first so camera init uses correct driver
        try:
            self._on_backend_selected(self.backend_cb.currentText())
        except Exception:
            pass

        # Restore saved camera selection if it exists for the current cached list
        try:
            if saved_camera and saved_camera in self.cameras:
                self.camera_cb.setCurrentText(saved_camera)
        except Exception:
            pass

        # Now notify the worker of camera selection and params
        try:
            self._on_camera_selected(self.camera_cb.currentText())
        except Exception:
            pass
        self._on_cam_params_changed()
        # Apply threshold through queue
        safe_queue_put(
            self.camera_control_queue,
            ('set_thresh', self.thresh_var),
            timeout=QUEUE_PUT_TIMEOUT
        )
    
    def is_position_tracking_enabled(self) -> bool:
        """Check if position tracking is currently enabled.
        
        Returns:
            True if position tracking is active
        """
        return self.pos_track_enabled


# Import fix for QImage
from PyQt5.QtGui import QImage