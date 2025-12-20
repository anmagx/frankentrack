"""Camera Panel for frankentrack GUI.

Provides controls to enable/disable preview and position tracking and shows
a small preview image and current X/Y/Z values. Commands are sent to the
camera control queue and preview/position data are received from the
corresponding display queues by the main GUI loop.
"""
from PyQt5.QtWidgets import (QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QDoubleSpinBox, QSizePolicy,
                             QComboBox, QSlider)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer
import base64

from util.error_utils import safe_queue_put
from config.config import QUEUE_PUT_TIMEOUT


class CameraPanelQt(QWidget):
    def __init__(self, parent=None, control_queue=None, message_callback=None, preview_queue=None, padding=6):
        super().__init__(parent)
        self.control_queue = control_queue
        self.message_callback = message_callback
        self.preview_queue = preview_queue

        # Debounce timer for movement scale slider to avoid spamming control queue
        self._scale_send_timer = QTimer(self)
        self._scale_send_timer.setSingleShot(True)
        self._scale_send_timer.timeout.connect(self._apply_scale)
        self._pending_scale_value = None

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # Frame 1: Controls row (Preview, Tracking) left; Cam index right
        frame1 = QGroupBox("Camera Controls")
        f1_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Preview On")
        self.preview_btn.setCheckable(True)
        self.preview_btn.clicked.connect(self._on_preview_toggled)
        f1_layout.addWidget(self.preview_btn)

        self.track_btn = QPushButton("Start Tracking")
        self.track_btn.setCheckable(True)
        self.track_btn.clicked.connect(self._on_track_toggled)
        f1_layout.addWidget(self.track_btn)

        f1_layout.addStretch(1)
        # Cam index selector (dropdown) on the far right
        self.cam_index_combo = QComboBox()
        self._cam_indices = [str(i) for i in range(0, 17)]
        self.cam_index_combo.addItems(self._cam_indices)
        self.cam_index_combo.setCurrentIndex(0)
        self.cam_index_combo.currentTextChanged.connect(self._on_cam_index_changed)
        f1_layout.addWidget(QLabel("Cam index:"))
        f1_layout.addWidget(self.cam_index_combo)

        frame1.setLayout(f1_layout)
        main_layout.addWidget(frame1)

        # Preview label (large) will be added next

        # Frame 2: Preview + Resolution/FPS
        frame2 = QGroupBox("Camera Preview")
        f2_layout = QVBoxLayout()

        # Preview label
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(320, 240)
        self.preview_label.setStyleSheet("background-color: #222; border: 1px solid #444;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        # Show disabled text until preview is activated
        self.preview_label.setText("Preview disabled")
        f2_layout.addWidget(self.preview_label)

        # Resolution + FPS row inside frame2
        res_fps_layout = QHBoxLayout()
        res_fps_layout.addWidget(QLabel("Resolution:"))
        self.resolution_combo = QComboBox()
        self._resolutions = ["320x240", "640x480"]
        self.resolution_combo.addItems(self._resolutions)
        self.resolution_combo.setCurrentIndex(0)
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        res_fps_layout.addWidget(self.resolution_combo)

        res_fps_layout.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self._fps_values = ["15", "30", "60", "120", "200"]
        self.fps_combo.addItems(self._fps_values)
        self.fps_combo.setCurrentIndex(1)
        self.fps_combo.currentTextChanged.connect(self._on_fps_changed)
        res_fps_layout.addWidget(self.fps_combo)
        res_fps_layout.addStretch(1)
        f2_layout.addLayout(res_fps_layout)

        frame2.setLayout(f2_layout)
        main_layout.addWidget(frame2)

        # Frame 3: Tracking settings (Threshold, Exposure, Gain sliders)
        frame3 = QGroupBox("Tracking Settings")
        f3_layout = QVBoxLayout()

        # Threshold
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Threshold:"))
        self.thresh_slider = QSlider(Qt.Horizontal)
        self.thresh_slider.setMinimum(0)
        self.thresh_slider.setMaximum(255)
        self.thresh_slider.setValue(200)
        self.thresh_slider.setTickPosition(QSlider.TicksBelow)
        self.thresh_slider.setTickInterval(5)
        self.thresh_slider.valueChanged.connect(self._on_threshold_changed)
        thresh_layout.addWidget(self.thresh_slider)
        self.thresh_value_label = QLabel(str(self.thresh_slider.value()))
        thresh_layout.addWidget(self.thresh_value_label)
        f3_layout.addLayout(thresh_layout)

        # Movement scale (-30 .. +30)
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Movement Scale:"))
        self.scale_slider = QSlider(Qt.Horizontal)
        # Increased range to +/-50 per request
        self.scale_slider.setMinimum(-50)
        self.scale_slider.setMaximum(50)
        self.scale_slider.setValue(30)
        self.scale_slider.setTickPosition(QSlider.TicksBelow)
        self.scale_slider.setTickInterval(5)
        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self.scale_slider)
        self.scale_value_label = QLabel(str(self.scale_slider.value()))
        scale_layout.addWidget(self.scale_value_label)
        f3_layout.addLayout(scale_layout)

        # Exposure
        exp_layout = QHBoxLayout()
        exp_layout.addWidget(QLabel("Exposure:"))
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setMinimum(0)
        self.exposure_slider.setMaximum(255)
        self.exposure_slider.setValue(128)
        self.exposure_slider.setTickPosition(QSlider.TicksBelow)
        self.exposure_slider.setTickInterval(16)
        self.exposure_slider.valueChanged.connect(self._on_exposure_changed)
        exp_layout.addWidget(self.exposure_slider)
        self.exposure_value_label = QLabel(str(self.exposure_slider.value()))
        exp_layout.addWidget(self.exposure_value_label)
        f3_layout.addLayout(exp_layout)

        # Gain
        gain_layout = QHBoxLayout()
        gain_layout.addWidget(QLabel("Gain:"))
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setMinimum(0)
        self.gain_slider.setMaximum(255)
        self.gain_slider.setValue(128)
        self.gain_slider.setTickPosition(QSlider.TicksBelow)
        self.gain_slider.setTickInterval(16)
        self.gain_slider.valueChanged.connect(self._on_gain_changed)
        gain_layout.addWidget(self.gain_slider)
        self.gain_value_label = QLabel(str(self.gain_slider.value()))
        gain_layout.addWidget(self.gain_value_label)
        f3_layout.addLayout(gain_layout)

        frame3.setLayout(f3_layout)
        main_layout.addWidget(frame3)

        self.setLayout(main_layout)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def _on_preview_toggled(self, checked):
        if self.control_queue is None:
            return
        cmd = ('preview_on',) if checked else ('preview_off',)
        safe_queue_put(self.control_queue, cmd, timeout=QUEUE_PUT_TIMEOUT)
        # Update button text
        self.preview_btn.setText("Preview Off" if checked else "Preview On")
        # Update preview label: clear text when preview enabled, show disabled message and clear pixmap when disabled
        try:
            if checked:
                # Enable: clear any disabled text (preview frames will populate via update_preview)
                try:
                    self.preview_label.setText("")
                except Exception:
                    pass
            else:
                try:
                    # Create a black pixmap with a disabled message so UI is consistent
                    from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
                    size = self.preview_label.size()
                    pix = QPixmap(size)
                    pix.fill(QColor('#111'))
                    painter = QPainter(pix)
                    try:
                        painter.setPen(QColor(180, 180, 180))
                        f = QFont()
                        f.setPointSize(10)
                        painter.setFont(f)
                        painter.drawText(pix.rect(), Qt.AlignCenter, "Preview disabled")
                    finally:
                        painter.end()
                    self.preview_label.setPixmap(pix)
                except Exception:
                    try:
                        self.preview_label.clear()
                        self.preview_label.setText("Preview disabled")
                    except Exception:
                        pass
                # If preview is stopped and tracking is not running, request explicit camera release
                try:
                    if not getattr(self, 'track_btn', None) or not getattr(self.track_btn, 'isChecked', lambda: False)():
                        safe_queue_put(self.control_queue, ('close_cam',), timeout=QUEUE_PUT_TIMEOUT)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_track_toggled(self, checked):
        if self.control_queue is None:
            return
        cmd = ('start_pos',) if checked else ('stop_pos',)
        safe_queue_put(self.control_queue, cmd, timeout=QUEUE_PUT_TIMEOUT)
        self.track_btn.setText("Stop Tracking" if checked else "Start Tracking")
        
        # If tracking is stopped and preview is also off, release the camera
        if not checked:
            try:
                if not getattr(self, 'preview_btn', None) or not self.preview_btn.isChecked():
                    safe_queue_put(self.control_queue, ('close_cam',), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

    def _on_cam_index_changed(self, val):
        if self.control_queue is None:
            return
        try:
            # val may be string from combo or int from spinbox
            safe_queue_put(self.control_queue, ('set_cam', int(val)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_threshold_changed(self, val):
        if self.control_queue is None:
            return
        try:
            self.thresh_value_label.setText(str(int(val)))
            safe_queue_put(self.control_queue, ('set_thresh', int(val)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_resolution_changed(self, text):
        if self.control_queue is None:
            return
        try:
            parts = str(text).split('x')
            if len(parts) == 2:
                w = int(parts[0])
                h = int(parts[1])
                # use current fps selection
                fps = int(self.fps_combo.currentText()) if self.fps_combo.currentText() else None
                safe_queue_put(self.control_queue, ('set_cam_params', fps, w, h), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_fps_changed(self, text):
        if self.control_queue is None:
            return
        try:
            fps = int(text) if text else None
            # use current resolution selection
            res = self.resolution_combo.currentText()
            parts = str(res).split('x')
            if len(parts) == 2:
                w = int(parts[0])
                h = int(parts[1])
                safe_queue_put(self.control_queue, ('set_cam_params', fps, w, h), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_exposure_changed(self, val):
        try:
            self.exposure_value_label.setText(str(int(val)))
            if self.control_queue is None:
                return
            safe_queue_put(self.control_queue, ('set_exposure', int(val)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_gain_changed(self, val):
        try:
            self.gain_value_label.setText(str(int(val)))
            if self.control_queue is None:
                return
            safe_queue_put(self.control_queue, ('set_gain', int(val)), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_scale_changed(self, val):
        try:
            self.scale_value_label.setText(str(int(val)))
            # Debounce send: store pending value and start/reset timer
            self._pending_scale_value = int(val)
            # 120 ms debounce similar to other panels
            self._scale_send_timer.stop()
            self._scale_send_timer.start(120)
        except Exception:
            pass

    def _apply_scale(self):
        """Send the pending scale value to the camera control queue (debounced)."""
        try:
            if self._pending_scale_value is None:
                return
            v = int(self._pending_scale_value)
            if self.control_queue is None:
                self._pending_scale_value = None
                return
            safe_queue_put(self.control_queue, ('set_scale', v), timeout=QUEUE_PUT_TIMEOUT)
            self._pending_scale_value = None
        except Exception:
            pass

    def update_preview(self, jpg_bytes):
        try:
            # If preview toggle is off, ignore incoming frames to avoid flashing
            if hasattr(self, 'preview_btn') and not self.preview_btn.isChecked():
                return
            if not jpg_bytes:
                return
            image = QImage.fromData(jpg_bytes)
            if image.isNull():
                return
            pix = QPixmap.fromImage(image).scaled(self.preview_label.size(), Qt.KeepAspectRatio)
            self.preview_label.setPixmap(pix)
        except Exception:
            pass

    def update_position(self, x, y, z):
        # Position indicators removed from UI; keep no-op to avoid callers failing
        return

    def update_pixel_position(self, px, py):
        # Pixel indicators removed from UI; keep no-op to avoid callers failing
        return

    def get_prefs(self):
        return {
            'cam_index': int(self.cam_index_combo.currentText()),
            'threshold': int(self.thresh_slider.value()),
            'scale': int(self.scale_slider.value()),
            'resolution': str(self.resolution_combo.currentText()),
            'fps': int(self.fps_combo.currentText()),
            'exposure': int(self.exposure_slider.value()),
            'gain': int(self.gain_slider.value())
        }

    def set_prefs(self, prefs):
        try:
            if isinstance(prefs, dict):
                if 'cam_index' in prefs:
                    try:
                        ci = str(int(prefs['cam_index']))
                        if hasattr(self, 'cam_index_combo') and ci in self._cam_indices:
                            self.cam_index_combo.setCurrentText(ci)
                    except Exception:
                        pass
                if 'threshold' in prefs:
                    try:
                        self.thresh_slider.setValue(int(prefs['threshold']))
                        self.thresh_value_label.setText(str(int(prefs['threshold'])))
                    except Exception:
                        pass
                if 'scale' in prefs:
                    try:
                        sv = int(prefs['scale'])
                        if -50 <= sv <= 50:
                            self.scale_slider.setValue(sv)
                            self.scale_value_label.setText(str(sv))
                    except Exception:
                        pass
                if 'resolution' in prefs:
                    try:
                        res = str(prefs['resolution'])
                        if res in self._resolutions:
                            self.resolution_combo.setCurrentText(res)
                    except Exception:
                        pass
                if 'fps' in prefs:
                    try:
                        fpss = str(int(prefs['fps']))
                        if fpss in self._fps_values:
                            self.fps_combo.setCurrentText(fpss)
                    except Exception:
                        pass
                if 'exposure' in prefs:
                    try:
                        ev = int(prefs['exposure'])
                        if 0 <= ev <= 255:
                            self.exposure_slider.setValue(ev)
                            self.exposure_value_label.setText(str(ev))
                    except Exception:
                        pass
                if 'gain' in prefs:
                    try:
                        gv = int(prefs['gain'])
                        if 0 <= gv <= 255:
                            self.gain_slider.setValue(gv)
                            self.gain_value_label.setText(str(gv))
                    except Exception:
                        pass
        except Exception:
            pass
