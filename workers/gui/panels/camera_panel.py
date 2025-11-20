"""
Camera control panel for camera preview, enumeration, and position tracking.

This panel handles:
- Camera preview canvas with image display
- Camera enumeration in background thread
- Camera/FPS/Resolution selection
- Preview enable/disable toggle
- Position tracking start/stop
- Detection threshold slider (debounced)
"""

import tkinter as tk
from tkinter import ttk
import threading
from typing import Optional

from config.config import (
    PREVIEW_WIDTH, PREVIEW_HEIGHT,
    DEFAULT_CAMERA_FPS, DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT,
    DEFAULT_DETECTION_THRESHOLD, THRESH_DEBOUNCE_MS,
    QUEUE_PUT_TIMEOUT
)
from util.error_utils import safe_queue_put

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


class CameraPanel(ttk.LabelFrame):
    """Panel for camera preview, enumeration, and position tracking controls."""

    def __init__(
        self,
        parent,
        camera_control_queue,
        message_queue=None,
        **kwargs
    ):
        """
        Args:
            parent: Parent tkinter widget
            camera_control_queue: Queue for sending commands to camera worker
            message_queue: Optional queue for logging messages
            **kwargs: Additional arguments passed to LabelFrame
        """
        super().__init__(parent, text="Camera Control", **kwargs)
        
        self.camera_control_queue = camera_control_queue
        self.message_queue = message_queue
        
        # State tracking
        self.preview_enabled = False
        self.pos_track_enabled = False
        self.cameras = ["Camera 0", "Camera 1", "Camera 2"]  # Default list
        self._thresh_send_job = None  # For debouncing threshold slider
        self._current_preview_image = None  # Store PhotoImage reference
        
        # Create UI elements
        self._create_widgets()
        
    def _create_widgets(self):
        """Build the camera control panel layout."""
        # Preview canvas at top
        preview_frame = ttk.Frame(self)
        preview_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            bg='black'
        )
        self.preview_canvas.pack()
        # Draw default disabled message until preview enabled
        self._draw_preview_disabled()
        
        # Controls frame below canvas
        controls_frame = ttk.Frame(self)
        controls_frame.pack(side="top", fill="x", padx=5, pady=5)
        
        # Row 1: Preview toggle and Enumerate button
        row1 = ttk.Frame(controls_frame)
        row1.pack(side="top", fill="x", pady=2)
        
        self.preview_btn_text = tk.StringVar(value="Enable Preview")
        self.preview_btn = ttk.Button(
            row1,
            textvariable=self.preview_btn_text,
            command=self.toggle_preview
        )
        self.preview_btn.pack(side="left", padx=2)
        
        self.enumerate_btn = ttk.Button(
            row1,
            text="Enumerate Cameras",
            command=self._on_enumerate_clicked
        )
        self.enumerate_btn.pack(side="left", padx=2)
        
        # Row 2: Camera selection
        row2 = ttk.Frame(controls_frame)
        row2.pack(side="top", fill="x", pady=2)
        
        ttk.Label(row2, text="Camera:").pack(side="left")
        self.camera_var = tk.StringVar(value=self.cameras[0])
        self.camera_cb = ttk.Combobox(
            row2,
            textvariable=self.camera_var,
            values=self.cameras,
            state="readonly",
            width=15
        )
        self.camera_cb.pack(side="left", padx=2)
        self.camera_cb.bind('<<ComboboxSelected>>', self._on_camera_selected)
        
        # Row 3: FPS and Resolution
        row3 = ttk.Frame(controls_frame)
        row3.pack(side="top", fill="x", pady=2)
        
        ttk.Label(row3, text="FPS:").pack(side="left")
        self.fps_var = tk.StringVar(value=str(DEFAULT_CAMERA_FPS))
        self.fps_cb = ttk.Combobox(
            row3,
            textvariable=self.fps_var,
            values=['15', '30', '60', '90', '120'],
            state="readonly",
            width=6
        )
        self.fps_cb.pack(side="left", padx=2)
        self.fps_cb.bind('<<ComboboxSelected>>', lambda e: self._on_cam_params_changed())
        
        ttk.Label(row3, text="Resolution:").pack(side="left", padx=(8, 0))
        self.res_var = tk.StringVar(value=f"{DEFAULT_CAMERA_WIDTH}x{DEFAULT_CAMERA_HEIGHT}")
        self.res_cb = ttk.Combobox(
            row3,
            textvariable=self.res_var,
            values=['320x240', '640x480', '1280x720', '1920x1080'],
            state="readonly",
            width=10
        )
        self.res_cb.pack(side="left", padx=2)
        self.res_cb.bind('<<ComboboxSelected>>', lambda e: self._on_cam_params_changed())
        
        # Row 4: Position tracking toggle
        row4 = ttk.Frame(controls_frame)
        row4.pack(side="top", fill="x", pady=2)
        
        self.pos_btn_text = tk.StringVar(value="Start Position Tracking")
        self.pos_btn = ttk.Button(
            row4,
            textvariable=self.pos_btn_text,
            command=self.toggle_position_tracking
        )
        self.pos_btn.pack(side="left", padx=2)
        
        # Row 5: Detection threshold slider
        row5 = ttk.Frame(controls_frame)
        row5.pack(side="top", fill="x", pady=2)
        
        ttk.Label(row5, text="Detection Threshold:").pack(side="left")
        self.thresh_var = tk.IntVar(value=DEFAULT_DETECTION_THRESHOLD)
        self.thresh_scale = ttk.Scale(
            row5,
            from_=0,
            to=255,
            orient="horizontal",
            variable=self.thresh_var,
            command=self._on_thresh_change
        )
        self.thresh_scale.pack(side="left", fill="x", expand=True, padx=2)
        
        self.thresh_label = ttk.Label(row5, text=str(DEFAULT_DETECTION_THRESHOLD), width=4)
        self.thresh_label.pack(side="left")
        
    def toggle_preview(self):
        """Toggle camera preview on/off."""
        self.preview_enabled = not self.preview_enabled
        if self.preview_enabled:
            self.preview_btn_text.set("Disable Preview")
            safe_queue_put(
                self.camera_control_queue,
                ('preview_on',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            self._log_message("Preview enabled")
        else:
            self.preview_btn_text.set("Enable Preview")
            safe_queue_put(
                self.camera_control_queue,
                ('preview_off',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            # Clear canvas when preview disabled
            self._current_preview_image = None
            self._draw_preview_disabled()
            self._log_message("Preview disabled")
    
    def toggle_position_tracking(self):
        """Toggle position tracking mode."""
        self.pos_track_enabled = not self.pos_track_enabled
        if self.pos_track_enabled:
            self.pos_btn_text.set("Stop Position Tracking")
            safe_queue_put(
                self.camera_control_queue,
                ('start_pos',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            self._log_message(f"Position tracking started on {self.camera_var.get()}")
            
            # Disable camera controls while tracking is active
            self.camera_cb.configure(state='disabled')
            self.fps_cb.configure(state='disabled')
            self.res_cb.configure(state='disabled')
            self.thresh_scale.configure(state='disabled')
            self.enumerate_btn.configure(state='disabled')
        else:
            self.pos_btn_text.set("Start Position Tracking")
            safe_queue_put(
                self.camera_control_queue,
                ('stop_pos',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            self._log_message("Position tracking stopped")
            
            # Re-enable camera controls
            self.camera_cb.configure(state='readonly')
            self.fps_cb.configure(state='readonly')
            self.res_cb.configure(state='readonly')
            self.thresh_scale.configure(state='normal')
            self.enumerate_btn.configure(state='normal')
    
    def update_preview(self, jpeg_data: bytes):
        """Update the preview canvas with new JPEG image data.
        
        Args:
            jpeg_data: JPEG-encoded image bytes from camera worker
        """
        if not self.preview_enabled:
            return
        
        if Image is None or ImageTk is None:
            return
        
        try:
            import io
            img = Image.open(io.BytesIO(jpeg_data))
            photo = ImageTk.PhotoImage(img)
            
            # Store reference to prevent garbage collection
            self._current_preview_image = photo
            
            # Update canvas
            self.preview_canvas.delete("all")
            # center the image on canvas if sizes differ
            try:
                cw = int(self.preview_canvas.cget('width'))
                ch = int(self.preview_canvas.cget('height'))
            except Exception:
                cw = PREVIEW_WIDTH
                ch = PREVIEW_HEIGHT
            iw = photo.width()
            ih = photo.height()
            x = max((cw - iw) // 2, 0)
            y = max((ch - ih) // 2, 0)
            self.preview_canvas.create_image(x, y, anchor="nw", image=photo)
        except Exception as e:
            # Don't spam errors for preview updates
            pass

    def _draw_preview_disabled(self):
        """Draw a black background with centered 'Preview disabled' text."""
        try:
            self.preview_canvas.delete("all")
            w = int(self.preview_canvas.cget('width'))
            h = int(self.preview_canvas.cget('height'))
            self.preview_canvas.create_rectangle(0, 0, w, h, fill='black', outline='black')
            self.preview_canvas.create_text(w/2, h/2, text="Preview disabled", fill='white', font=('TkDefaultFont', 14))
        except Exception:
            try:
                # Best-effort fallback
                self.preview_canvas.delete("all")
                self.preview_canvas.create_text(10, 10, text="Preview disabled", fill='white')
            except Exception:
                pass
    
    def set_cameras(self, camera_list: list):
        """Update the list of available cameras.
        
        Args:
            camera_list: List of camera names/indices (e.g., ["Camera 0", "Camera 1"])
        """
        self.cameras = camera_list if camera_list else ["Camera 0"]
        self.camera_cb.configure(values=self.cameras)
        
        # Preserve selected camera if still available, otherwise select first
        current = self.camera_var.get()
        if current not in self.cameras:
            self.camera_var.set(self.cameras[0])
    
    def _on_camera_selected(self, event=None):
        """Handler for camera selection change."""
        # Parse camera index from combobox string (e.g., "Camera 9" -> 9)
        val = self.camera_var.get()
        idx = 0
        try:
            parts = val.rsplit(' ', 1)
            if len(parts) == 2:
                idx = int(parts[1])
            else:
                # Fallback: extract all digits
                digits = ''.join(ch for ch in val if ch.isdigit())
                idx = int(digits) if digits else 0
        except Exception:
            try:
                idx = int(self.camera_cb.current() or 0)
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
            fps = int(self.fps_var.get())
        except Exception:
            fps = DEFAULT_CAMERA_FPS
        
        try:
            res = self.res_var.get()
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
    
    def _on_thresh_change(self, val):
        """Debounced handler for threshold slider changes."""
        # Update display label immediately
        try:
            v = int(float(val))
            self.thresh_label.configure(text=str(v))
        except Exception:
            pass
        
        # Cancel pending threshold send
        if self._thresh_send_job is not None:
            try:
                self.after_cancel(self._thresh_send_job)
            except Exception:
                pass
        
        # Schedule new threshold send after debounce delay
        self._thresh_send_job = self.after(THRESH_DEBOUNCE_MS, self._apply_thresh)
    
    def _apply_thresh(self):
        """Send threshold value to camera worker (called after debounce)."""
        try:
            v = int(self.thresh_var.get())
        except Exception:
            return
        
        safe_queue_put(
            self.camera_control_queue,
            ('set_thresh', v),
            timeout=QUEUE_PUT_TIMEOUT
        )
    
    def _on_enumerate_clicked(self):
        """Handler for 'Enumerate Cameras' button."""
        self.enumerate_btn.configure(state='disabled')
        self._log_message("Camera enumeration started (this can take a minute)...")
        
        # Disable controls during enumeration
        self._disable_controls_for_enumeration()
        
        # Run enumeration in background thread
        threading.Thread(target=self._enumerate_cameras, args=(32,), daemon=True).start()
    
    def _disable_controls_for_enumeration(self):
        """Disable all camera controls during enumeration."""
        self.preview_btn.configure(state='disabled')
        self.enumerate_btn.configure(state='disabled')
        self.camera_cb.configure(state='disabled')
        self.fps_cb.configure(state='disabled')
        self.res_cb.configure(state='disabled')
        self.pos_btn.configure(state='disabled')
        self.thresh_scale.configure(state='disabled')
    
    def _enable_controls_after_enumeration(self):
        """Re-enable camera controls after enumeration completes."""
        self.preview_btn.configure(state='normal')
        self.enumerate_btn.configure(state='normal')
        self.camera_cb.configure(state='readonly')
        self.fps_cb.configure(state='readonly')
        self.res_cb.configure(state='readonly')
        self.pos_btn.configure(state='normal')
        self.thresh_scale.configure(state='normal')
    
    def _enumerate_cameras(self, max_checks: int = 32):
        """Probe camera indices in a background thread.
        
        Args:
            max_checks: Maximum camera index to check (0 to max_checks-1)
        """
        cams = []
        
        # Try importing opencv
        try:
            import cv2
        except ImportError:
            cv2 = None
        
        if cv2 is None:
            # Schedule fallback on main thread
            def _fallback():
                self._log_message("OpenCV not available: using default camera list")
                self.set_cameras(["Camera 0", "Camera 1", "Camera 2"])
                self._enable_controls_after_enumeration()
            self.after(0, _fallback)
            return
        
        # Probe each camera index
        for i in range(max_checks):
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
        
        # Schedule UI update on main thread
        def _update():
            if cams:
                self.set_cameras(cams)
                self._log_message(f"Found {len(cams)} camera(s)")
            else:
                self.set_cameras(["Camera 0"])
                self._log_message("No cameras found, using default")
            self._enable_controls_after_enumeration()
        
        self.after(0, _update)
    
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
        return {
            'camera': self.camera_var.get(),
            'cameras': ','.join(self.cameras),
            'fps': self.fps_var.get(),
            'resolution': self.res_var.get(),
            'thresh': str(self.thresh_var.get()),
        }
    
    def set_prefs(self, prefs: dict):
        """Apply saved preferences to camera controls.
        
        Args:
            prefs: Dictionary with camera preferences
        """
        # Restore camera list first
        cameras_str = prefs.get('cameras', '')
        if cameras_str:
            cam_list = [c.strip() for c in cameras_str.split(',') if c.strip()]
            if cam_list:
                self.set_cameras(cam_list)
        
        # Restore selected camera
        camera = prefs.get('camera')
        if camera and camera in self.cameras:
            self.camera_var.set(camera)
        
        # Restore FPS
        fps = prefs.get('fps')
        if fps:
            self.fps_var.set(fps)
        
        # Restore resolution
        resolution = prefs.get('resolution')
        if resolution:
            self.res_var.set(resolution)
        
        # Restore threshold
        thresh = prefs.get('thresh')
        if thresh:
            try:
                self.thresh_var.set(int(thresh))
                self.thresh_label.configure(text=thresh)
            except Exception:
                pass
        
        # Send initial camera settings to worker
        self._on_camera_selected()
        self._on_cam_params_changed()
        self._apply_thresh()
    
    def is_position_tracking_enabled(self) -> bool:
        """Check if position tracking is currently enabled.
        
        Returns:
            True if position tracking is active
        """
        return self.pos_track_enabled
