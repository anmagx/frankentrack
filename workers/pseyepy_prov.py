"""Clean pseyepy camera provider with subprocess isolation.

This provider runs pseyepy in a separate subprocess to isolate native code
crashes and provide robust frame capture. Frames are encoded as JPEG in the
subprocess and passed via stdout to avoid shared memory complexity.

Interface:
    - read() -> (frame, timestamp) - Returns BGR numpy array and timestamp
    - set_params(width, height, fps) - Update camera parameters (restarts camera)
    - set_setting(name, value) - Set camera attribute (exposure, gain, etc.)
    - close() - Clean shutdown of subprocess and camera
"""
import os
import sys
import time
import struct
import subprocess
import threading
import queue
import tempfile
import traceback
import cv2
import numpy as np


class PSEyeProvider:
    """Subprocess-based pseyepy camera provider.
    
    This provider runs pseyepy in a subprocess to isolate crashes and provides
    a clean interface for camera_wrk.py.
    """
    
    def __init__(self, cam_index, width, height, fps, logQueue=None):
        """Initialize camera provider.
        
        Args:
            cam_index: Camera device index (0, 1, 2, ...)
            width: Frame width in pixels
            height: Frame height in pixels
            fps: Target frames per second (None for camera default)
            logQueue: Optional queue for logging messages
        """
        self.cam_index = cam_index
        self.width = width
        self.height = height
        self.fps = fps
        self.logQueue = logQueue
        
        self.proc = None
        self._reader_thread = None
        self._frame_queue = queue.Queue(maxsize=2)  # Small buffer for latest frames
        self._stop_event = threading.Event()
        self._last_frame = None
        self._last_ts = None
        
        # Start subprocess
        self._start_subprocess()
    
    def _log(self, level, msg):
        """Send log message to logQueue if available."""
        if self.logQueue is not None:
            try:
                self.logQueue.put((level, 'CameraProvider', msg), timeout=0.1)
            except Exception:
                pass
    
    def _start_subprocess(self):
        """Start camera capture subprocess."""
        try:
            self._log('INFO', f"Starting camera subprocess: index={self.cam_index}, {self.width}x{self.height} @ {self.fps}fps")
            
            # Create wrapper script in temp directory
            wrapper_script = self._create_wrapper_script()
            
            # Start subprocess
            self.proc = subprocess.Popen(
                [sys.executable, wrapper_script, 
                 str(self.cam_index), str(self.width), str(self.height), str(self.fps or 0)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            self._log('INFO', f"Subprocess started (PID: {self.proc.pid})")
            
            # Start reader thread to parse frames from stdout
            self._stop_event.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            
            # Start stderr monitor thread for subprocess logs
            stderr_thread = threading.Thread(target=self._stderr_monitor, daemon=True)
            stderr_thread.start()
            
        except Exception as e:
            self._log('ERROR', f"Failed to start subprocess: {e}")
            raise
    
    def _create_wrapper_script(self):
        """Create a temporary Python script that runs the camera worker inline."""
        # Embed the entire worker function in the wrapper to avoid import issues
        wrapper_code = '''
import sys
import time
import struct
import cv2
import numpy as np

def camera_worker(cam_index, width, height, fps):
    """Camera capture subprocess - runs pseyepy and streams JPEG frames to stdout."""
    def log(msg):
        """Log to stderr (stdout is reserved for frame data)."""
        try:
            print(f"[CamSubproc] {msg}", file=sys.stderr, flush=True)
        except Exception:
            pass
    
    log(f"Starting camera worker: index={cam_index}, {width}x{height} @ {fps}fps")
    
    # Import pseyepy (subprocess-only import)
    try:
        import pseyepy
        log("pseyepy imported")
    except Exception as e:
        log(f"ERROR: Failed to import pseyepy: {e}")
        return 1
    
    # Open camera
    cam = None
    try:
        # Determine resolution mode
        res = 0  # default
        if hasattr(pseyepy.Camera, 'RES_SMALL') and hasattr(pseyepy.Camera, 'RES_LARGE'):
            res = pseyepy.Camera.RES_SMALL if width <= 320 else pseyepy.Camera.RES_LARGE
        
        # Create camera with FPS if specified
        if fps is not None and fps > 0:
            cam = pseyepy.Camera(ids=cam_index, resolution=res, fps=int(fps), colour=True)
        else:
            cam = pseyepy.Camera(ids=cam_index, resolution=res, colour=True)
        
        log(f"Camera opened successfully")
    except Exception as e:
        log(f"ERROR: Failed to open camera: {e}")
        import traceback
        log(traceback.format_exc())
        return 2
    
    # Main capture loop
    running = True
    frame_count = 0
    
    try:
        while running:
            # Read frame from camera
            try:
                # Try to read with timestamp
                try:
                    data = cam.read(timestamp=True, squeeze=True)
                    if isinstance(data, (tuple, list)) and len(data) >= 2:
                        frame, ts = data[0], data[1]
                    else:
                        frame = data
                        ts = time.time()
                except TypeError:
                    # Fallback: read without timestamp
                    frame = cam.read()
                    ts = time.time()
            except Exception as e:
                log(f"ERROR: cam.read() failed: {e}")
                time.sleep(0.01)
                continue
            
            if frame is None:
                time.sleep(0.001)
                continue
            
            # Convert RGB to BGR for OpenCV compatibility
            try:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception:
                frame_bgr = frame
            
            # Encode as JPEG
            try:
                ret, buf = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ret:
                    log("ERROR: JPEG encoding failed")
                    continue
                
                img_bytes = buf.tobytes()
                length = len(img_bytes)
                
                # Write frame to stdout: [size][timestamp][jpeg_data]
                header = struct.pack('<I', length)
                ts_bytes = struct.pack('<d', float(ts if ts is not None else time.time()))
                
                sys.stdout.buffer.write(header + ts_bytes + img_bytes)
                sys.stdout.buffer.flush()
                
                frame_count += 1
                if frame_count == 1:
                    log(f"First frame sent ({length} bytes)")
                elif frame_count % 30 == 0:
                    log(f"Sent {frame_count} frames")
                
            except Exception as e:
                log(f"ERROR: Frame encoding/writing failed: {e}")
                if "closed" in str(e).lower() or "broken" in str(e).lower():
                    log("Stdout broken, exiting")
                    break
    
    finally:
        # Clean shutdown
        try:
            if cam is not None:
                log("Closing camera...")
                cam.end()
                log("Camera closed")
        except Exception as e:
            log(f"ERROR during camera cleanup: {e}")
    
    log(f"Camera worker exiting (sent {frame_count} frames)")
    return 0

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: script.py <cam_index> <width> <height> <fps>", file=sys.stderr)
        sys.exit(1)
    
    cam_index = int(sys.argv[1])
    width = int(sys.argv[2])
    height = int(sys.argv[3])
    fps_val = int(sys.argv[4])
    fps = fps_val if fps_val > 0 else None
    
    sys.exit(camera_worker(cam_index, width, height, fps))
'''
        
        # Write wrapper script to temp file
        fd, path = tempfile.mkstemp(suffix='.py', prefix='frankentrack_cam_')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(wrapper_code)
        except Exception:
            os.close(fd)
            raise
        
        self._wrapper_script = path
        return path
    
    def _stderr_monitor(self):
        """Monitor subprocess stderr and log messages."""
        if self.proc is None or self.proc.stderr is None:
            return
        
        try:
            for line in iter(self.proc.stderr.readline, b''):
                if self._stop_event.is_set():
                    break
                try:
                    msg = line.decode('utf-8', errors='replace').strip()
                    if msg:
                        # Log subprocess messages (reduce verbosity)
                        if 'ERROR' in msg:
                            self._log('ERROR', msg)
                        elif 'Starting' in msg or 'First frame' in msg or 'opened' in msg:
                            self._log('INFO', msg)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _reader_loop(self):
        """Read frames from subprocess stdout and queue them."""
        try:
            while not self._stop_event.is_set() and self.proc is not None:
                try:
                    # Read frame header: 4-byte size + 8-byte timestamp
                    header = self._read_exact(12)
                    if header is None:
                        break
                    
                    frame_size = struct.unpack('<I', header[:4])[0]
                    timestamp = struct.unpack('<d', header[4:12])[0]
                    
                    # Read JPEG data
                    jpeg_data = self._read_exact(frame_size)
                    if jpeg_data is None:
                        break
                    
                    # Decode JPEG to numpy array
                    frame = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    
                    # Store frame (drop old frames if queue full)
                    try:
                        self._frame_queue.put_nowait((frame, timestamp))
                    except queue.Full:
                        # Drop oldest frame and add new one
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._frame_queue.put_nowait((frame, timestamp))
                        except queue.Full:
                            pass
                
                except Exception as e:
                    if not self._stop_event.is_set():
                        self._log('ERROR', f"Frame read error: {e}")
                    break
        
        except Exception as e:
            if not self._stop_event.is_set():
                self._log('ERROR', f"Reader loop crashed: {e}")
    
    def _read_exact(self, n):
        """Read exactly n bytes from subprocess stdout."""
        if self.proc is None or self.proc.stdout is None:
            return None
        
        data = b''
        while len(data) < n:
            if self._stop_event.is_set():
                return None
            
            try:
                chunk = self.proc.stdout.read(n - len(data))
                if not chunk:
                    return None  # EOF
                data += chunk
            except Exception:
                return None
        
        return data
    
    def read(self):
        """Read the latest frame.
        
        Returns:
            (frame, timestamp): BGR numpy array and timestamp, or (None, None) if unavailable
        """
        try:
            # Try to get latest frame (non-blocking)
            frame, ts = self._frame_queue.get_nowait()
            self._last_frame = frame
            self._last_ts = ts
            return (frame, ts)
        except queue.Empty:
            # Return last known frame if available
            return (self._last_frame, self._last_ts)
    
    def set_params(self, width, height, fps):
        """Update camera parameters by restarting subprocess.
        
        Args:
            width: New frame width
            height: New frame height
            fps: New target FPS (None for default)
        """
        self._log('INFO', f"Updating camera params: {width}x{height} @ {fps}fps")
        
        # Store new parameters
        self.width = width
        self.height = height
        self.fps = fps
        
        # Restart subprocess with new parameters
        self.close()
        time.sleep(0.5)  # Brief delay to ensure camera is released
        self._start_subprocess()
    
    def set_setting(self, name, value):
        """Set camera attribute (exposure, gain, etc.).
        
        Note: Command interface not fully implemented in subprocess worker yet.
        This is a placeholder for future enhancement.
        
        Args:
            name: Setting name (e.g., 'exposure', 'gain')
            value: Setting value
        """
        # Future: Send SET command via stdin
        # For now, log only
        self._log('INFO', f"set_setting called: {name}={value} (not yet implemented)")
    
    def close(self):
        """Shutdown subprocess and clean up resources."""
        self._log('INFO', "Closing camera provider")
        
        # Signal threads to stop
        self._stop_event.set()
        
        # Shutdown subprocess gracefully
        if self.proc is not None:
            try:
                # Step 1: Close stdout to signal subprocess to exit (broken pipe)
                # The subprocess detects broken pipe during frame write and exits cleanly
                try:
                    if self.proc.stdout:
                        self.proc.stdout.close()
                except Exception:
                    pass
                
                # Step 2: Wait briefly for subprocess to detect broken pipe and exit gracefully
                try:
                    self.proc.wait(timeout=1.0)
                    self._log('INFO', "Subprocess exited gracefully")
                except subprocess.TimeoutExpired:
                    # Step 3: Subprocess didn't exit - try closing stdin as well
                    try:
                        if self.proc.stdin:
                            self.proc.stdin.close()
                    except Exception:
                        pass
                    
                    # Wait a bit more
                    try:
                        self.proc.wait(timeout=0.5)
                        self._log('INFO', "Subprocess exited after stdin close")
                    except subprocess.TimeoutExpired:
                        # Step 4: Force termination as last resort
                        self._log('WARN', "Subprocess did not exit gracefully, terminating")
                        try:
                            self.proc.terminate()
                            self.proc.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            # Step 5: Kill if terminate didn't work
                            self.proc.kill()
                            try:
                                self.proc.wait(timeout=0.5)
                            except Exception:
                                pass
            except Exception as e:
                self._log('ERROR', f"Error during subprocess cleanup: {e}")
            
            # Close remaining pipes
            try:
                if self.proc.stdin and not self.proc.stdin.closed:
                    self.proc.stdin.close()
            except Exception:
                pass
            try:
                if self.proc.stderr:
                    self.proc.stderr.close()
            except Exception:
                pass
            
            self.proc = None
        
        # Wait for reader thread
        if self._reader_thread is not None:
            try:
                self._reader_thread.join(timeout=1.0)
            except Exception:
                pass
            self._reader_thread = None
        
        # Clean up wrapper script
        try:
            if hasattr(self, '_wrapper_script') and self._wrapper_script and os.path.exists(self._wrapper_script):
                os.remove(self._wrapper_script)
                self._wrapper_script = None
        except Exception:
            pass
        
        self._log('INFO', "Camera provider closed")
