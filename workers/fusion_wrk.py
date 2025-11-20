"""
Sensor fusion worker using complementary filter for orientation estimation.
Reads IMU data from serialQueue and outputs Euler angles to eulerQueue.
"""
import numpy as np
import time
from queue import Empty
import threading

from config.config import (
     ACCEL_THRESHOLD,
     DEFAULT_CENTER_THRESHOLD,
     ALPHA_YAW,
     ALPHA_PITCH,
     ALPHA_ROLL,
     ALPHA_DRIFT_CORRECTION,
        GYRO_BIAS_CAL_SAMPLES,
    STATIONARY_GYRO_THRESHOLD,
    STATIONARY_DEBOUNCE_S,
     DT_MIN,
     DT_MAX,
     QUEUE_GET_TIMEOUT,
     QUEUE_PUT_TIMEOUT
)
from util.error_utils import (
    safe_queue_put,
    safe_queue_get,
    parse_imu_line,
    normalize_angle
)


class ComplementaryFilter:
    """Complementary filter for orientation estimation using gyro and accel."""
    
    def __init__(self, accel_threshold=ACCEL_THRESHOLD, center_threshold=DEFAULT_CENTER_THRESHOLD, logQueue=None):
        """
        Initialize the complementary filter.
        
        Args:
            accel_threshold: Only apply drift correction when total accel is within
                           this threshold of 1g (e.g., 0.15 means 0.85-1.15g).
                           This prevents correction during movement.
            center_threshold: All angles must be within this many degrees of 0 
                            to enable drift correction.
        """
        # Gyro weight for complementary filter on roll/pitch (0..1).
        # Values <1 allow accelerometer to gently correct long-term drift.
        self.alpha_roll = ALPHA_ROLL  # From config
        self.alpha_pitch = ALPHA_PITCH  # From config
        self.alpha_yaw = ALPHA_YAW  # From config
        self.alpha_drift = ALPHA_DRIFT_CORRECTION  # From config
        self.accel_threshold = accel_threshold
        self.center_threshold = center_threshold
        # Gyro bias for yaw (deg/s). This is set at startup by calibration
        # (if enabled) and is applied as a static correction during runtime.
        self.gyro_bias_yaw = 0.0
        # Whether a gyro yaw bias has been calibrated/applied
        self.gyro_calibrated = False
        # Stationary detection debounce state
        self._stationary_start = None
        self._last_stationary = False
        self._gyro_stationary_threshold = STATIONARY_GYRO_THRESHOLD
        self._stationary_debounce_s = STATIONARY_DEBOUNCE_S
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.last_time = None
        self.logQueue = logQueue
        
    def update(self, gyro, accel, timestamp):
        """
        Update orientation estimate.
        
        Args:
            gyro: (gx, gy, gz) in deg/s
            accel: (ax, ay, az) in g
            timestamp: current time in seconds
        
        Returns:
            (yaw, pitch, roll) in degrees
        """
        if self.last_time is None:
            # First call: establish a time baseline and return a zeroed
            # orientation so the system starts centered at 0,0,0.
            # Log that we're initializing timing baseline (useful after reset)
            try:
                from util.log_utils import log_info
                log_info(self.logQueue, "Fusion", f"Initializing timing baseline at {timestamp}")
            except Exception:
                pass
            try:
                print(f"[Fusion] Initializing timing baseline at {timestamp}")
            except Exception:
                pass
            self.last_time = timestamp
            self.roll = 0.0
            self.pitch = 0.0
            self.yaw = 0.0
            # Return consistent 5-tuple: (yaw, pitch, roll, drift_active, is_stationary)
            return self.yaw, self.pitch, self.roll, False, False
        
        # Calculate dt
        dt = timestamp - self.last_time
        
        # Validate dt before updating time baseline
        if dt <= 0:
            # Negative or zero dt - likely duplicate or time reset, skip update
            return self.yaw, self.pitch, self.roll, False
        
        if dt < DT_MIN:
            # Too small, likely duplicate timestamp
            return self.yaw, self.pitch, self.roll, False
        
        if dt > DT_MAX:
            # Gap too large - reset time baseline without updating orientation
            from util.log_utils import log_warning
            log_warning(self.logQueue, "Fusion", f"Large dt: {dt:.3f}s, resetting baseline")
            self.last_time = timestamp
            return self.yaw, self.pitch, self.roll, False
        
        # Valid dt - update baseline
        self.last_time = timestamp
        
        gx, gy, gz = gyro
        
        # Apply gyro bias correction for yaw before integration
        gz_corr = gz - self.gyro_bias_yaw

        # Gyro integration (primary method)
        gyro_roll = self.roll + gx * dt
        gyro_pitch = self.pitch + gy * dt
        gyro_yaw = self.yaw + gz_corr * dt
        
        # Check if accelerometer is measuring primarily gravity (sensor is quiet)
        ax, ay, az = accel
        accel_magnitude = np.sqrt(ax**2 + ay**2 + az**2)

        # Compute instantaneous gyro magnitude (deg/s)
        gyro_mag = np.sqrt(gx * gx + gy * gy + gz * gz)

        # Instantaneous candidate for stationary: accel near 1g AND gyro magnitude small
        accel_ok = False
        if accel_magnitude >= 0.01:
            accel_ok = abs(accel_magnitude - 1.0) < self.accel_threshold

        candidate_stationary = accel_ok and (gyro_mag < self._gyro_stationary_threshold)

        # Debounce stationary detection: require candidate to persist for configured time
        if candidate_stationary:
            if self._stationary_start is None:
                self._stationary_start = timestamp
            # Only mark stationary once persisted
            is_stationary = (timestamp - self._stationary_start) >= self._stationary_debounce_s
        else:
            # Reset debounce
            self._stationary_start = None
            is_stationary = False
        
        # Check if we're looking approximately straight ahead (all axes near center)
        def _angle_diff(a, b):
            """Smallest angle difference considering wrapping."""
            diff = (a - b + 180) % 360 - 180
            return abs(diff)
        
        is_near_center = (_angle_diff(self.yaw, 0) < self.center_threshold and 
                         _angle_diff(self.pitch, 0) < self.center_threshold and
                         _angle_diff(self.roll, 0) < self.center_threshold)
        
        # Apply drift correction to all axes when stationary and near center
        drift_correction_active = False
        if is_stationary and is_near_center:
            # When looking straight ahead and stationary, use alpha for gentle drift correction
            # This allows angles to slowly return to 0
            self.roll = self.alpha_drift * gyro_roll + (1.0 - self.alpha_drift) * 0.0
            self.pitch = self.alpha_drift * gyro_pitch + (1.0 - self.alpha_drift) * 0.0
            self.yaw = self.alpha_yaw * gyro_yaw + (1.0 - self.alpha_yaw) * 0.0
            drift_correction_active = True
        else:
            # Fuse gyro + accel for roll/pitch when accelerometer reliably measures gravity
            accel_roll, accel_pitch = self._accel_to_rp((ax, ay, az))

            # Consider accelerometer valid when magnitude is close to 1g
            accel_valid = accel_magnitude >= 0.01 and abs(accel_magnitude - 1.0) < self.accel_threshold

            if accel_valid:
                # Blend gyro integration with accel-derived angles for roll/pitch
                self.roll = self.alpha_roll * gyro_roll + (1.0 - self.alpha_roll) * accel_roll
                self.pitch = self.alpha_pitch * gyro_pitch + (1.0 - self.alpha_pitch) * accel_pitch
            else:
                # Fall back to pure gyro integration when accel data isn't reliable
                self.roll = gyro_roll
                self.pitch = gyro_pitch

            # Yaw remains pure gyro (no magnetometer present)
            self.yaw = gyro_yaw

            # Note: live (online) bias estimation removed — bias is set at startup
            # during calibration (if enabled) and remains static during runtime.
        
        # Normalize angles to [-180, 180]
        self.yaw = normalize_angle(self.yaw)
        self.pitch = normalize_angle(self.pitch)
        self.roll = normalize_angle(self.roll)
        
        return self.yaw, self.pitch, self.roll, drift_correction_active, is_stationary
    
    def _accel_to_rp(self, accel):
        """
        Calculate roll and pitch from accelerometer (assumes gravity-only).
        
        Args:
            accel: (ax, ay, az) in g
            
        Returns:
            (roll, pitch) in degrees
        """
        ax, ay, az = accel
        
        # Roll: rotation around X axis
        roll = np.arctan2(ay, az) * 180.0 / np.pi
        
        # Pitch: rotation around Y axis
        pitch = np.arctan2(-ax, np.sqrt(ay**2 + az**2)) * 180.0 / np.pi
        
        return roll, pitch
    
    def reset(self):
        """Reset orientation to zero."""
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0


def run_worker(serialQueue, eulerQueue, eulerDisplayQueue, controlQueue, statusQueue, stop_event, logQueue=None):
    """
    Fusion worker that reads IMU data from serialQueue and outputs Euler angles to eulerQueue.
    """
    from util.log_utils import log_info, log_error, log_warning
    
    log_info(logQueue, "Fusion Worker", "Starting complementary filter")
    print("[Fusion Worker] Starting complementary filter...")
    
    # Initialize filter with defaults from config. The GUI can update
    # `filter.center_threshold` at runtime via the controlQueue ('set_center_threshold').
    filter = ComplementaryFilter(
        accel_threshold=ACCEL_THRESHOLD, 
        center_threshold=DEFAULT_CENTER_THRESHOLD,
        logQueue=logQueue
    )
    # Startup calibration disabled: calibration must be triggered manually
    # by the GUI (recalibrate_gyro_bias). Inform GUI of current calibration
    # state (not calibrated) so the UI can reflect it.
    try:
        filter.gyro_calibrated = False
        safe_queue_put(statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
    except Exception:
        # Best-effort: don't block startup if statusQueue is unavailable
        pass
    
    # Translation values (not used, set to 0)
    x, y, z = 0.0, 0.0, 0.0
    
    try:
        while not stop_event.is_set():
            # Check for control commands (non-blocking)
            cmd = safe_queue_get(controlQueue, timeout=0.0, default=None)
            if cmd is not None:
                # support control commands: 'reset' and ('set_center_threshold', value)
                # Accept both bare string commands and tuple/list variants
                if cmd == 'reset_orientation' or (isinstance(cmd, (list, tuple)) and len(cmd) >= 1 and cmd[0] == 'reset_orientation'):
                    # Reset orientation state but preserve calibration/bias.
                    filter.reset()
                    log_info(logQueue, "Fusion Worker", "Orientation reset to zero (preserving calibration)")
                    print("[Fusion Worker] Orientation reset to zero (preserving calibration)")
                elif cmd == 'reset' or (isinstance(cmd, (list, tuple)) and len(cmd) >= 1 and cmd[0] == 'reset'):
                    # Full reset: reset orientation and clear runtime calibration
                    filter.reset()
                    # Clear timing and stationary debounce state so the filter
                    # reinitializes cleanly when new data arrives after a stop/start.
                    try:
                        filter.last_time = None
                        filter._stationary_start = None
                        filter._last_stationary = False
                        # Log timing baseline clear for debugging
                        try:
                            from util.log_utils import log_info
                            log_info(logQueue, "Fusion Worker", "Cleared timing baseline and stationary debounce state on reset")
                        except Exception:
                            pass
                        try:
                            print("[Fusion Worker] Cleared timing baseline and stationary debounce state on reset")
                        except Exception:
                            pass
                    except Exception:
                        pass
                    try:
                        filter.gyro_bias_yaw = 0.0
                        filter.gyro_calibrated = False
                        safe_queue_put(statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
                    except Exception:
                        pass

                    # Also explicitly clear drift and stationary UI indicators so the
                    # front-end does not continue to show stale 'active' state after stop.
                    try:
                        safe_queue_put(statusQueue, ('drift_correction', False), timeout=QUEUE_PUT_TIMEOUT)
                    except Exception:
                        pass
                    try:
                        safe_queue_put(statusQueue, ('stationary', False), timeout=QUEUE_PUT_TIMEOUT)
                    except Exception:
                        pass
                    log_info(logQueue, "Fusion Worker", "Orientation reset to zero and calibration cleared")
                    print("[Fusion Worker] Orientation reset to zero and calibration cleared")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_center_threshold':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 180.0:  # Sanity check
                            filter.center_threshold = new_val
                            log_info(logQueue, "Fusion Worker", f"Center threshold updated to {new_val}")
                            print(f"[Fusion Worker] Center threshold updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid center threshold: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting center threshold: {e}")
                elif (isinstance(cmd, (list, tuple)) and len(cmd) >= 1 and cmd[0] == 'recalibrate_gyro_bias') or cmd == ('recalibrate_gyro_bias',):
                    # Runtime recalibration request. Optional second element: number of samples
                    try:
                        n_samples = None
                        if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                            try:
                                n_samples = int(cmd[1])
                            except Exception:
                                n_samples = None

                        if n_samples is None:
                            n_samples = GYRO_BIAS_CAL_SAMPLES

                        if not n_samples or n_samples <= 0:
                            log_warning(logQueue, "Fusion Worker", f"Recalibration requested with non-positive sample count: {n_samples}")
                        else:
                            log_info(logQueue, "Fusion Worker", f"Recalibrating gyro yaw bias with {n_samples} samples")
                            print(f"[Fusion Worker] Recalibrating gyro yaw bias ({n_samples} samples)...")
                            samples = []
                            last_ts = None
                            while len(samples) < n_samples and not stop_event.is_set():
                                line = safe_queue_get(serialQueue, timeout=QUEUE_GET_TIMEOUT, default=None)
                                if line is None:
                                    continue
                                try:
                                    ts, accel, gyro = parse_imu_line(line)
                                    # Only accept stationary samples: accel near 1g and gyro quiet
                                    ax, ay, az = accel
                                    mag = np.sqrt(ax * ax + ay * ay + az * az)
                                    gyro_mag = np.sqrt(gyro[0] * gyro[0] + gyro[1] * gyro[1] + gyro[2] * gyro[2])
                                    if mag >= 0.01 and abs(mag - 1.0) < ACCEL_THRESHOLD and gyro_mag < STATIONARY_GYRO_THRESHOLD:
                                        samples.append(float(gyro[2]))
                                        last_ts = ts
                                except ValueError:
                                    continue

                            if len(samples) > 0:
                                bias = sum(samples) / float(len(samples))
                                filter.gyro_bias_yaw = bias
                                if last_ts is not None:
                                    filter.last_time = last_ts
                                # Mark filter as calibrated and notify GUI
                                filter.gyro_calibrated = True
                                try:
                                    safe_queue_put(statusQueue, ('gyro_calibrated', True), timeout=QUEUE_PUT_TIMEOUT)
                                except Exception:
                                    pass
                                log_info(logQueue, "Fusion Worker", f"Runtime gyro yaw bias recalibrated from {len(samples)} samples: {bias:.6f} deg/s")
                                print(f"[Fusion Worker] Gyro yaw bias recalibrated: {bias:.6f} deg/s")
                            else:
                                filter.gyro_calibrated = False
                                try:
                                    safe_queue_put(statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
                                except Exception:
                                    pass
                                log_warning(logQueue, "Fusion Worker", "Runtime gyro yaw bias recalibration collected 0 samples")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error during runtime gyro bias recalibration: {e}")
            
            # Get data from serial queue with timeout
            line = safe_queue_get(serialQueue, timeout=QUEUE_GET_TIMEOUT, default=None)
            
            if line is None:
                continue
            
            try:
                # Parse and validate IMU data using error_utils
                timestamp, accel, gyro = parse_imu_line(line)
                
                # Update filter
                yaw, pitch, roll, drift_active, is_stationary = filter.update(gyro, accel, timestamp)
                
                # Send drift correction status to UI
                safe_queue_put(statusQueue, ('drift_correction', drift_active), 
                             timeout=QUEUE_PUT_TIMEOUT)
                # Send stationarity status to UI (used by UI to show moving/stationary)
                safe_queue_put(statusQueue, ('stationary', is_stationary), timeout=QUEUE_PUT_TIMEOUT)
                
                # Put Euler angles into output queues
                # Format: [Yaw, Pitch, Roll, X, Y, Z]
                euler_data = [yaw, pitch, roll, x, y, z]

                # Publish to main euler queue (for UDP) and eulerDisplayQueue (for GUI)
                safe_queue_put(eulerQueue, euler_data, timeout=QUEUE_PUT_TIMEOUT)
                
                if eulerDisplayQueue is not None:
                    safe_queue_put(eulerDisplayQueue, euler_data, timeout=QUEUE_PUT_TIMEOUT)
                
            except ValueError as e:
                # Skip malformed/invalid lines (parse_imu_line raises ValueError)
                # Only log occasionally to avoid spam
                continue
            except Exception as e:
                log_error(logQueue, "Fusion Worker", f"Unexpected error processing data: {e}")
                continue
    
    except KeyboardInterrupt:
        pass
    finally:
        log_info(logQueue, "Fusion Worker", "Stopped")
        print("[Fusion Worker] Stopped.")
