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
from workers.gui.managers.icon_helper import set_window_icon
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

        # Debug: print whether camera_control_queue is available
        try:
            print(f"[CameraPanel] camera_control_queue is {'set' if self.camera_control_queue is not None else 'None'}")
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
        self._thresh_send_job = None  # For debouncing threshold slider
        self._current_preview_image = None  # Store PhotoImage reference
        # Keep a persistent threshold variable for prefs even though the
        # visible slider was moved to the Options dialog.
        self.thresh_var = tk.IntVar(value=DEFAULT_DETECTION_THRESHOLD)
        # Persistent exposure/gain vars for prefs and Options dialog
        self.exposure_var = tk.IntVar(value=0)
        self.gain_var = tk.IntVar(value=0)
        
        # Create UI elements
        self._create_widgets()
        
    def _create_widgets(self):
        """Build the camera control panel layout."""

        # Top row: Backend (left) + Options button
        top_row = ttk.Frame(self)
        top_row.pack(side="top", fill="x", padx=5, pady=(5, 2))

        # Left: Backend selector with Options button next to it
        left_top = ttk.Frame(top_row)
        left_top.pack(side="left", anchor='w')
        ttk.Label(left_top, text="Backend:").pack(side="left")
        self.backend_var = tk.StringVar(value='openCV')
        self.backend_cb = ttk.Combobox(
            left_top,
            textvariable=self.backend_var,
            values=['openCV', 'pseyepy (PS3Eye)'],
            state="readonly",
            width=18
        )
        self.backend_cb.pack(side="left", padx=4)
        self.backend_cb.bind('<<ComboboxSelected>>', lambda e: self._on_backend_selected())

        # (Options button moved to camera row per layout requirements)

        # Camera row below top row: Camera selector + Options (adjacent)
        camera_row = ttk.Frame(self)
        camera_row.pack(side="top", fill="x", padx=5, pady=(4, 2))
        ttk.Label(camera_row, text="Camera:").pack(side="left")
        self.camera_var = tk.StringVar(value=self.cameras[0])
        self.camera_cb = ttk.Combobox(
            camera_row,
            textvariable=self.camera_var,
            values=self.cameras,
            state="readonly",
            width=20
        )
        self.camera_cb.pack(side="left", padx=4)
        self.camera_cb.bind('<<ComboboxSelected>>', self._on_camera_selected)

        # Options button placed immediately to the right of the camera combobox
        self.options_btn = ttk.Button(
            camera_row,
            text="Options",
            command=self._open_options_dialog
        )
        self.options_btn.pack(side="right", padx=(6, 0))
        
        # Top-row right side: Enumerate button (moved to top row for prominence)
        try:
            right_top
        except NameError:
            # If top_row's right container wasn't created earlier, create it now
            right_top = ttk.Frame(top_row)
            right_top.pack(side="right", anchor='e')
        self.enumerate_btn = ttk.Button(
            right_top,
            text="Enumerate Cameras",
            command=self._on_enumerate_clicked
        )
        self.enumerate_btn.pack(side="right")

        # Preview canvas below top selectors
        preview_frame = ttk.Frame(self)
        # Do not expand the preview container so FPS controls sit directly below
        preview_frame.pack(side="top", fill="both", expand=False, padx=8, pady=(4, 4))

        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            bg='black'
        )
        self.preview_canvas.pack()
        self._draw_preview_disabled()

        # FPS / Resolution row centered below the preview
        params_row = ttk.Frame(self)
        params_row.pack(side="top", fill="x", padx=8, pady=(6, 6))

        # Center container for FPS/Resolution controls
        center_params = ttk.Frame(params_row)
        center_params.pack(side="top", anchor='center')
        ttk.Label(center_params, text="FPS:").pack(side="left")
        self.fps_var = tk.StringVar(value=str(DEFAULT_CAMERA_FPS))
        self.fps_cb = ttk.Combobox(
            center_params,
            textvariable=self.fps_var,
            values=['15', '30', '60', '90', '120'],
            state="readonly",
            width=6
        )
        self.fps_cb.pack(side="left", padx=4)
        self.fps_cb.bind('<<ComboboxSelected>>', lambda e: self._on_cam_params_changed())

        ttk.Label(center_params, text="Resolution:").pack(side="left", padx=(8, 0))
        self.res_var = tk.StringVar(value=f"{DEFAULT_CAMERA_WIDTH}x{DEFAULT_CAMERA_HEIGHT}")
        self.res_cb = ttk.Combobox(
            center_params,
            textvariable=self.res_var,
            values=['320x240', '640x480', '1280x720', '1920x1080'],
            state="readonly",
            width=10
        )
        self.res_cb.pack(side="left", padx=4)
        self.res_cb.bind('<<ComboboxSelected>>', lambda e: self._on_cam_params_changed())

        # Preview toggle centered under FPS/Resolution controls
        preview_btn_row = ttk.Frame(self)
        preview_btn_row.pack(side="top", fill="x", padx=8, pady=(4, 6))
        self.preview_btn_text = tk.StringVar(value="Enable Preview")
        self.preview_btn = ttk.Button(
            preview_btn_row,
            textvariable=self.preview_btn_text,
            command=self.toggle_preview
        )
        self.preview_btn.pack(anchor='center')

        # (Detection threshold moved to Options dialog)

        # Position tracking centered at the bottom
        pos_row = ttk.Frame(self)
        pos_row.pack(side="top", fill="x", padx=8, pady=(6, 8))
        self.pos_btn_text = tk.StringVar(value="Start Position Tracking")
        self.pos_btn = ttk.Button(
            pos_row,
            textvariable=self.pos_btn_text,
            command=self.toggle_position_tracking
        )
        self.pos_btn.pack(anchor='center')
        
    def _open_options_dialog(self):
        """Open a modal Options dialog for threshold/exposure/gain."""
        # If dialog already exists, focus it
        if hasattr(self, '_options_win') and self._options_win.winfo_exists():
            try:
                self._options_win.lift()
                return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title('Camera Options')
        # Use same icon as main GUI if available
        try:
            set_window_icon(win)
        except Exception:
            pass
        win.transient(self)
        win.resizable(False, False)
        self._options_win = win

        # Detection threshold
        row1 = ttk.Frame(win, padding=8)
        row1.pack(fill='x')
        ttk.Label(row1, text='Detection Threshold:').pack(side='left')
        self._opt_thresh_var = self.thresh_var
        thresh_scale = ttk.Scale(row1, from_=0, to=255, orient='horizontal', variable=self._opt_thresh_var, command=self._on_options_thresh_change, length=220)
        thresh_scale.pack(side='left', padx=6)
        self._opt_thresh_label = ttk.Label(row1, text=str(self._opt_thresh_var.get()), width=4)
        self._opt_thresh_label.pack(side='left')

        # Exposure
        row2 = ttk.Frame(win, padding=8)
        row2.pack(fill='x')
        ttk.Label(row2, text='Exposure:').pack(side='left')
        self._opt_exposure_var = self.exposure_var
        # Exposure range 0-255
        exp_scale = ttk.Scale(row2, from_=0, to=255, orient='horizontal', variable=self._opt_exposure_var, command=self._on_options_exposure_change, length=220)
        exp_scale.pack(side='left', padx=6)
        self._opt_exposure_label = ttk.Label(row2, text=str(self._opt_exposure_var.get()), width=4)
        self._opt_exposure_label.pack(side='left')

        # Gain
        row3 = ttk.Frame(win, padding=8)
        row3.pack(fill='x')
        ttk.Label(row3, text='Gain:').pack(side='left')
        self._opt_gain_var = self.gain_var
        # Gain range for PS3Eye: 0-63
        gain_scale = ttk.Scale(row3, from_=0, to=63, orient='horizontal', variable=self._opt_gain_var, command=self._on_options_gain_change, length=220)
        gain_scale.pack(side='left', padx=6)
        self._opt_gain_label = ttk.Label(row3, text=str(self._opt_gain_var.get()), width=4)
        self._opt_gain_label.pack(side='left')

        # Close button
        btn_row = ttk.Frame(win, padding=8)
        btn_row.pack(fill='x')
        close_btn = ttk.Button(btn_row, text='Close', command=win.destroy)
        close_btn.pack(side='right')

    def _on_options_thresh_change(self, val):
        try:
            v = int(float(val))
            self._opt_thresh_label.configure(text=str(v))
            # update option slider label
            # debounce using existing mechanism
            try:
                self.thresh_var.set(v)
            except Exception:
                pass
            # schedule sending via existing debounce logic
            if self._thresh_send_job is not None:
                try:
                    self.after_cancel(self._thresh_send_job)
                except Exception:
                    pass
            self._thresh_send_job = self.after(THRESH_DEBOUNCE_MS, self._apply_thresh)
        except Exception:
            pass

    def _on_options_exposure_change(self, val):
        try:
            v = int(float(val))
            # update persistent var and label
            try:
                self.exposure_var.set(v)
            except Exception:
                pass
            self._opt_exposure_label.configure(text=str(v))
            # send to worker
            safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'exposure', v), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass

    def _on_options_gain_change(self, val):
        try:
            v = int(float(val))
            try:
                self.gain_var.set(v)
            except Exception:
                pass
            self._opt_gain_label.configure(text=str(v))
            safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'gain', v), timeout=QUEUE_PUT_TIMEOUT)
        except Exception:
            pass
        
    def toggle_preview(self):
        """Toggle camera preview on/off."""
        self.preview_enabled = not self.preview_enabled
        if self.preview_enabled:
            self.preview_btn_text.set("Disable Preview")
            ok = safe_queue_put(
                self.camera_control_queue,
                ('preview_on',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            try:
                print(f"[CameraPanel] Sent preview_on -> ok={ok}")
            except Exception:
                pass
            self._log_message("Preview enabled")
        else:
            self.preview_btn_text.set("Enable Preview")
            ok = safe_queue_put(
                self.camera_control_queue,
                ('preview_off',),
                timeout=QUEUE_PUT_TIMEOUT
            )
            try:
                print(f"[CameraPanel] Sent preview_off -> ok={ok}")
            except Exception:
                pass
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
            self.backend_cb.configure(state='disabled')
            self.res_cb.configure(state='disabled')
            # thresh_scale is now in Options dialog, not main panel
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
            self.backend_cb.configure(state='readonly')
            self.res_cb.configure(state='readonly')
            # thresh_scale is now in Options dialog, not main panel
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

    def _on_backend_selected(self, event=None):
        """Handler for backend selection change."""
        val = self.backend_var.get()
        # Map display value to backend key used by camera worker
        key = 'pseyepy' if 'pseyepy' in val.lower() else 'openCV'
        safe_queue_put(
            self.camera_control_queue,
            ('set_backend', key),
            timeout=QUEUE_PUT_TIMEOUT
        )
        self._log_message(f"Camera backend set to {val}")

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
        self.backend_cb.configure(state='disabled')
        self.res_cb.configure(state='disabled')
        self.pos_btn.configure(state='disabled')
        # thresh_scale is now in Options dialog, not main panel
    
    def _enable_controls_after_enumeration(self):
        """Re-enable camera controls after enumeration completes."""
        self.preview_btn.configure(state='normal')
        self.enumerate_btn.configure(state='normal')
        self.camera_cb.configure(state='readonly')
        self.fps_cb.configure(state='readonly')
        self.backend_cb.configure(state='readonly')
        self.res_cb.configure(state='readonly')
        self.pos_btn.configure(state='normal')
        # thresh_scale is now in Options dialog, not main panel
    
    def _enumerate_cameras(self, max_checks: int = 32):
        """Probe camera indices in a background thread.
        
        Args:
            max_checks: Maximum camera index to check (0 to max_checks-1)
        """
        cams = []
        
        # If backend is pseyepy, prefer using its cam_count() helper which is fast
        backend_display = self.backend_var.get() if hasattr(self, 'backend_var') else 'openCV'
        try:
            if 'pseyepy' in backend_display.lower():
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
                        # Cache for pseyepy backend
                        try:
                            self._cached_cameras['pseyepy'] = list(cams)
                        except Exception:
                            pass
                        # Schedule UI update
                        def _update_pseyepy():
                            self.set_cameras(cams)
                            self._log_message(f"Found {len(cams)} PS3Eye camera(s)")
                            self._enable_controls_after_enumeration()
                            # Persist updated per-backend camera enumeration immediately
                            try:
                                PreferencesManager().update(self.get_prefs())
                            except Exception:
                                pass
                        self.after(0, _update_pseyepy)
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
            # Schedule fallback on main thread
            def _fallback():
                self._log_message("OpenCV not available: using default camera list")
                self.set_cameras(["Camera 0", "Camera 1", "Camera 2"])
                self._enable_controls_after_enumeration()
            self.after(0, _fallback)
            return

        # Probe each camera index using OpenCV
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
                # Cache under current backend
                try:
                    backend_display = self.backend_var.get() if hasattr(self, 'backend_var') else 'openCV'
                    backend_key = 'pseyepy' if 'pseyepy' in backend_display.lower() else 'openCV'
                    self._cached_cameras[backend_key] = list(cams)
                except Exception:
                    pass
                self.set_cameras(cams)
                self._log_message(f"Found {len(cams)} camera(s)")
                # Persist updated per-backend camera enumeration immediately
                try:
                    PreferencesManager().update(self.get_prefs())
                except Exception:
                    pass
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
        # Include per-backend cached camera lists so switching backends restores
        # the last-known enumeration for that backend.
        cams_opencv = ','.join(self._cached_cameras.get('openCV', []))
        cams_pseyepy = ','.join(self._cached_cameras.get('pseyepy', []))
        return {
            'camera': self.camera_var.get(),
            'cameras': ','.join(self.cameras),
            'cameras_opencv': cams_opencv,
            'cameras_pseyepy': cams_pseyepy,
            'fps': self.fps_var.get(),
            'resolution': self.res_var.get(),
            'thresh': str(self.thresh_var.get()),
            'exposure': str(self.exposure_var.get()),
            'gain': str(self.gain_var.get()),
            'backend': self.backend_var.get(),
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
                if hasattr(self, 'thresh_label'):
                    try:
                        self.thresh_label.configure(text=thresh)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore exposure and gain
        exposure = prefs.get('exposure')
        if exposure is not None:
            try:
                self.exposure_var.set(int(exposure))
                # send to worker so provider can apply if open
                safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'exposure', int(exposure)), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

        gain = prefs.get('gain')
        if gain is not None:
            try:
                self.gain_var.set(int(gain))
                safe_queue_put(self.camera_control_queue, ('set_cam_setting', 'gain', int(gain)), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass

        # Restore backend selection
        backend = prefs.get('backend')
        if backend:
            try:
                # If saved value is the worker key (e.g., 'pseyepy'), try to map to display
                if backend == 'pseyepy':
                    self.backend_var.set('pseyepy (PS3Eye)')
                else:
                    self.backend_var.set(backend)
            except Exception:
                pass

        # Send initial camera settings to worker
        # Notify backend first so camera init uses correct driver
        try:
            self._on_backend_selected()
        except Exception:
            pass

        # Restore saved camera selection if it exists for the current cached list
        try:
            if saved_camera and saved_camera in self.cameras:
                self.camera_var.set(saved_camera)
        except Exception:
            pass

        # Now notify the worker of camera selection and params
        try:
            self._on_camera_selected()
        except Exception:
            pass
        self._on_cam_params_changed()
        self._apply_thresh()
    
    def is_position_tracking_enabled(self) -> bool:
        """Check if position tracking is currently enabled.
        
        Returns:
            True if position tracking is active
        """
        return self.pos_track_enabled
