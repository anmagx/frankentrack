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
     QUEUE_PUT_TIMEOUT,
     QUEUE_HIGH_WATERMARK,
     QUEUE_CRITICAL_WATERMARK,
     FUSION_LOOP_SLEEP_MS
)
from util.error_utils import (
    safe_queue_put,
    safe_queue_get,
    parse_imu_line,
    normalize_angle
)


class ComplementaryFilter:
    """Complementary filter for orientation estimation using gyro and accel."""
    
    def __init__(self, accel_threshold=ACCEL_THRESHOLD, center_threshold=DEFAULT_CENTER_THRESHOLD, center_threshold_yaw=None, center_threshold_pitch=None, center_threshold_roll=None, logQueue=None):
        """
        Initialize the complementary filter.
        
        Args:
            accel_threshold: Only apply drift correction when total accel is within
                           this threshold of 1g (e.g., 0.15 means 0.85-1.15g).
                           This prevents correction during movement.
            center_threshold: Default threshold for all axes (backward compatibility)
            center_threshold_yaw: Yaw-specific threshold (overrides center_threshold if provided)
            center_threshold_pitch: Pitch-specific threshold (overrides center_threshold if provided)
            center_threshold_roll: Roll-specific threshold (overrides center_threshold if provided)
        """
        # Gyro weight for complementary filter on roll/pitch (0..1).
        # Values <1 allow accelerometer to gently correct long-term drift.
        self.alpha_roll = ALPHA_ROLL  # From config
        self.alpha_pitch = ALPHA_PITCH  # From config
        self.alpha_yaw = ALPHA_YAW  # From config
        self.alpha_drift = ALPHA_DRIFT_CORRECTION  # From config
        self.accel_threshold = accel_threshold
        
        # Use separate thresholds if provided, otherwise use default for all
        self.center_threshold_yaw = center_threshold_yaw if center_threshold_yaw is not None else center_threshold
        self.center_threshold_pitch = center_threshold_pitch if center_threshold_pitch is not None else center_threshold
        self.center_threshold_roll = center_threshold_roll if center_threshold_roll is not None else center_threshold
        
        # Keep backward compatibility
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
        
        # Performance optimizations: pre-allocate result arrays and cache calculations
        self._result_tuple = [0.0, 0.0, 0.0, False, False]  # Reuse to avoid allocations
        self._cached_accel_mag = 0.0
        self._cached_gyro_mag = 0.0
        
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
            return self.yaw, self.pitch, self.roll, False, False

        if dt < DT_MIN:
            # Too small, likely duplicate timestamp
            return self.yaw, self.pitch, self.roll, False, False

        if dt > DT_MAX:
            # Gap too large - reset time baseline without updating orientation
            from util.log_utils import log_warning
            log_warning(self.logQueue, "Fusion", f"Large dt: {dt:.3f}s, resetting baseline")
            self.last_time = timestamp
            return self.yaw, self.pitch, self.roll, False, False
        
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
        # Cache magnitude calculation to avoid recomputation
        self._cached_accel_mag = np.sqrt(ax*ax + ay*ay + az*az)

        # Compute instantaneous gyro magnitude (deg/s) - cache for stationary detection
        self._cached_gyro_mag = np.sqrt(gx*gx + gy*gy + gz*gz)

        # Instantaneous candidate for stationary: accel near 1g AND gyro magnitude small
        accel_ok = False
        if self._cached_accel_mag >= 0.01:
            accel_ok = abs(self._cached_accel_mag - 1.0) < self.accel_threshold

        candidate_stationary = accel_ok and (self._cached_gyro_mag < self._gyro_stationary_threshold)

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
        def _angle_diff_fast(a, b):
            """Optimized smallest angle difference using modulo (O(1) vs O(n))."""
            diff = (a - b + 180.0) % 360.0 - 180.0
            return abs(diff)
        
        is_near_center = (_angle_diff_fast(self.yaw, 0) < self.center_threshold_yaw and 
                         _angle_diff_fast(self.pitch, 0) < self.center_threshold_pitch and
                         _angle_diff_fast(self.roll, 0) < self.center_threshold_roll)
        
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

            # Consider accelerometer valid when magnitude is close to 1g (use cached value)
            accel_valid = self._cached_accel_mag >= 0.01 and abs(self._cached_accel_mag - 1.0) < self.accel_threshold

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
        
        # Reuse result array to avoid memory allocations in hot path
        self._result_tuple[0] = self.yaw
        self._result_tuple[1] = self.pitch  
        self._result_tuple[2] = self.roll
        self._result_tuple[3] = drift_correction_active
        self._result_tuple[4] = is_stationary
        return tuple(self._result_tuple)  # Return tuple for compatibility

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


class QuaternionComplementaryFilter:
    """Complementary filter implemented with quaternion integration.

    This provides the same external API as `ComplementaryFilter` but uses
    quaternions for orientation integration and accel-based roll/pitch
    correction.
    """

    def __init__(self, accel_threshold=ACCEL_THRESHOLD, center_threshold=DEFAULT_CENTER_THRESHOLD, center_threshold_yaw=None, center_threshold_pitch=None, center_threshold_roll=None, logQueue=None):
        self.alpha_roll = ALPHA_ROLL
        self.alpha_pitch = ALPHA_PITCH
        self.alpha_yaw = ALPHA_YAW
        self.alpha_drift = ALPHA_DRIFT_CORRECTION
        self.accel_threshold = accel_threshold
        
        # Use separate thresholds if provided, otherwise use default for all
        self.center_threshold_yaw = center_threshold_yaw if center_threshold_yaw is not None else center_threshold
        self.center_threshold_pitch = center_threshold_pitch if center_threshold_pitch is not None else center_threshold
        self.center_threshold_roll = center_threshold_roll if center_threshold_roll is not None else center_threshold
        
        # Keep backward compatibility
        self.center_threshold = center_threshold
        self.gyro_bias_yaw = 0.0
        self.gyro_calibrated = False
        self._stationary_start = None
        self._last_stationary = False
        self._gyro_stationary_threshold = STATIONARY_GYRO_THRESHOLD
        self._stationary_debounce_s = STATIONARY_DEBOUNCE_S
        # Quaternion as [w, x, y, z]
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
        self.last_time = None
        self.logQueue = logQueue

    # --- Quaternion helper methods ---
    def _quat_normalize(self, q):
        n = np.linalg.norm(q)
        if n == 0:
            return np.array([1.0, 0.0, 0.0, 0.0])
        return q / n

    def _quat_mul(self, a, b):
        # Hamilton product
        w1, x1, y1, z1 = a
        w2, x2, y2, z2 = b
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2
        ], dtype=float)

    def _euler_from_quat(self, q):
        # returns (yaw, pitch, roll) in degrees
        w, x, y, z = q
        # roll (x-axis rotation)
        t0 = +2.0 * (w * x + y * z)
        t1 = +1.0 - 2.0 * (x * x + y * y)
        roll = np.degrees(np.arctan2(t0, t1))

        # pitch (y-axis)
        t2 = +2.0 * (w * y - z * x)
        t2 = np.clip(t2, -1.0, 1.0)
        pitch = np.degrees(np.arcsin(t2))

        # yaw (z-axis)
        t3 = +2.0 * (w * z + x * y)
        t4 = +1.0 - 2.0 * (y * y + z * z)
        yaw = np.degrees(np.arctan2(t3, t4))

        return yaw, pitch, roll

    def _quat_from_euler(self, yaw, pitch, roll):
        # input degrees
        cy = np.cos(np.radians(yaw) * 0.5)
        sy = np.sin(np.radians(yaw) * 0.5)
        cp = np.cos(np.radians(pitch) * 0.5)
        sp = np.sin(np.radians(pitch) * 0.5)
        cr = np.cos(np.radians(roll) * 0.5)
        sr = np.sin(np.radians(roll) * 0.5)

        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        return np.array([w, x, y, z], dtype=float)

    def _nlerp(self, a, b, t):
        q = (1.0 - t) * a + t * b
        return self._quat_normalize(q)

    def _accel_to_rp(self, accel):
        ax, ay, az = accel
        roll = np.arctan2(ay, az) * 180.0 / np.pi
        pitch = np.arctan2(-ax, np.sqrt(ay**2 + az**2)) * 180.0 / np.pi
        return roll, pitch

    def update(self, gyro, accel, timestamp):
        # Maintain same semantics as ComplementaryFilter.update
        if self.last_time is None:
            try:
                from util.log_utils import log_info
                log_info(self.logQueue, "Fusion", f"Initializing quaternion baseline at {timestamp}")
            except Exception:
                pass
            try:
                print(f"[Fusion] Initializing quaternion baseline at {timestamp}")
            except Exception:
                pass
            self.last_time = timestamp
            self.q = np.array([1.0, 0.0, 0.0, 0.0])
            return 0.0, 0.0, 0.0, False, False

        dt = timestamp - self.last_time
        if dt <= 0 or dt < DT_MIN:
            y, p, r = self._euler_from_quat(self.q)
            return y, p, r, False, False
        if dt > DT_MAX:
            try:
                from util.log_utils import log_warning
                log_warning(self.logQueue, "Fusion", f"Large dt: {dt:.3f}s, resetting quaternion baseline")
            except Exception:
                pass
            self.last_time = timestamp
            y, p, r = self._euler_from_quat(self.q)
            return y, p, r, False, False

        self.last_time = timestamp

        gx, gy, gz = gyro
        # apply bias to gz
        gz_corr = gz - self.gyro_bias_yaw

        # Integrate quaternion using gyro (deg/s -> rad/s)
        omega = np.array([0.0, np.radians(gx), np.radians(gy), np.radians(gz_corr)])
        q = self.q
        q_dot = 0.5 * self._quat_mul(q, omega)
        q = q + q_dot * dt
        q = self._quat_normalize(q)

        # accel-based roll/pitch correction (if accel valid)
        ax, ay, az = accel
        accel_mag = np.sqrt(ax*ax + ay*ay + az*az)
        gyro_mag = np.sqrt(gx*gx + gy*gy + gz*gz)

        accel_ok = False
        if accel_mag >= 0.01:
            accel_ok = abs(accel_mag - 1.0) < self.accel_threshold

        candidate_stationary = accel_ok and (gyro_mag < self._gyro_stationary_threshold)
        if candidate_stationary:
            if self._stationary_start is None:
                self._stationary_start = timestamp
            is_stationary = (timestamp - self._stationary_start) >= self._stationary_debounce_s
        else:
            self._stationary_start = None
            is_stationary = False

        # If stationary+near center use drift correction similar to Euler filter
        yaw_est, pitch_est, roll_est = self._euler_from_quat(q)
        def _angle_diff(a, b):
            diff = (a - b + 180) % 360 - 180
            return abs(diff)
        is_near_center = (_angle_diff(yaw_est, 0) < self.center_threshold_yaw and
                          _angle_diff(pitch_est, 0) < self.center_threshold_pitch and
                          _angle_diff(roll_est, 0) < self.center_threshold_roll)

        drift_active = False
        if is_stationary and is_near_center:
            # Pull quaternion towards zero roll/pitch slowly
            target_q = self._quat_from_euler(0.0, 0.0, 0.0)
            q = self._nlerp(q, target_q, 1.0 - self.alpha_drift)
            drift_active = True
        else:
            if accel_ok:
                accel_roll, accel_pitch = self._accel_to_rp((ax, ay, az))
                # Build target quaternion that retains current yaw but uses accel roll/pitch
                current_yaw, _, _ = self._euler_from_quat(q)
                target_q = self._quat_from_euler(current_yaw, accel_pitch, accel_roll)
                # Blend between gyro-integrated quaternion and accel-derived quaternion
                q = self._nlerp(q, target_q, 1.0 - self.alpha_roll)

        q = self._quat_normalize(q)
        self.q = q

        yaw, pitch, roll = self._euler_from_quat(q)
        # normalize angles
        yaw = normalize_angle(yaw)
        pitch = normalize_angle(pitch)
        roll = normalize_angle(roll)

        return yaw, pitch, roll, drift_active, is_stationary

    def reset(self):
        """Reset quaternion orientation to identity (zero rotation)."""
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    
    


def run_worker(serialQueue, eulerQueue, eulerDisplayQueue, controlQueue, statusQueue, stop_event, logQueue=None, uiStatusQueue=None):
    """
    Fusion worker that reads IMU data from serialQueue and outputs Euler angles to eulerQueue.
    """
    from util.log_utils import log_info, log_error, log_warning
    
    log_info(logQueue, "Fusion Worker", "Starting complementary filter")
    print("[Fusion Worker] Starting complementary filter...")
    
    # Initialize filter with defaults from config. The GUI can update
    # `filter.center_threshold` at runtime via the controlQueue ('set_center_threshold').
    # Support two filter implementations: 'complementary' (Euler-based) and 'quaternion'.
    def _create_filter(name):
        if name == 'quaternion':
            return QuaternionComplementaryFilter(accel_threshold=ACCEL_THRESHOLD,
                                                 center_threshold=DEFAULT_CENTER_THRESHOLD,
                                                 logQueue=logQueue)
        else:
            return ComplementaryFilter(accel_threshold=ACCEL_THRESHOLD,
                                       center_threshold=DEFAULT_CENTER_THRESHOLD,
                                       logQueue=logQueue)

    filter_type = 'complementary'
    filter = _create_filter(filter_type)
    # Startup calibration disabled: calibration must be triggered manually
    # by the GUI (recalibrate_gyro_bias). Inform GUI of current calibration
    # state (not calibrated) so the UI can reflect it.
    try:
        filter.gyro_calibrated = False
        safe_queue_put(statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
        safe_queue_put(statusQueue, ('processing', 'inactive'), timeout=QUEUE_PUT_TIMEOUT)
    except Exception:
        # Best-effort: don't block startup if statusQueue is unavailable
        pass
    
    # Translation values (not used, set to 0)
    x, y, z = 0.0, 0.0, 0.0
    
    # Track processing state to avoid spam
    processing_active = False
    
    # Track status values to only send updates when they change
    last_drift_active = None
    last_stationary = None
    
    try:
        while not stop_event.is_set():
            # Check for control commands (non-blocking)
            cmd = safe_queue_get(controlQueue, timeout=0.0, default=None)
            if cmd is not None:
                # Allow switching filter implementation at runtime
                if (isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_filter') or (isinstance(cmd, str) and cmd.startswith('set_filter')):
                    try:
                        # Accept ('set_filter', 'quaternion') or ('set_filter', 'complementary')
                        if isinstance(cmd, (list, tuple)):
                            new_type = str(cmd[1])
                        else:
                            # string form: 'set_filter:quaternion' not expected but support gracefully
                            parts = cmd.split(':', 1)
                            new_type = parts[1] if len(parts) > 1 else 'complementary'

                        new_type = new_type.lower()
                        if new_type not in ('quaternion', 'complementary'):
                            new_type = 'complementary'

                        if new_type != filter_type:
                            old_bias = getattr(filter, 'gyro_bias_yaw', 0.0)
                            old_cal = getattr(filter, 'gyro_calibrated', False)
                            old_thresh_yaw = getattr(filter, 'center_threshold_yaw', DEFAULT_CENTER_THRESHOLD)
                            old_thresh_pitch = getattr(filter, 'center_threshold_pitch', DEFAULT_CENTER_THRESHOLD)
                            old_thresh_roll = getattr(filter, 'center_threshold_roll', DEFAULT_CENTER_THRESHOLD)
                            
                            filter = _create_filter(new_type)
                            
                            # preserve bias/calibrated flag and separate thresholds where applicable
                            try:
                                filter.gyro_bias_yaw = float(old_bias)
                            except Exception:
                                pass
                            try:
                                filter.gyro_calibrated = bool(old_cal)
                            except Exception:
                                pass
                            try:
                                filter.center_threshold_yaw = float(old_thresh_yaw)
                            except Exception:
                                pass
                            try:
                                filter.center_threshold_pitch = float(old_thresh_pitch)
                            except Exception:
                                pass
                            try:
                                filter.center_threshold_roll = float(old_thresh_roll)
                            except Exception:
                                pass
                            # reset timing baseline so new filter initializes cleanly
                            filter.last_time = None
                            filter_type = new_type
                            try:
                                safe_queue_put(statusQueue, ('filter_type', filter_type), timeout=QUEUE_PUT_TIMEOUT)
                            except Exception:
                                pass
                            log_info(logQueue, "Fusion Worker", f"Switched filter to {filter_type}")
                            print(f"[Fusion Worker] Switched filter to {filter_type}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error switching filter: {e}")
                    continue
                # support control commands: 'reset' and ('set_center_threshold', value)
                # Accept both bare string commands and tuple/list variants
                if cmd == 'reset_orientation' or (isinstance(cmd, (list, tuple)) and len(cmd) >= 1 and cmd[0] == 'reset_orientation'):
                    # Reset orientation state but preserve calibration/bias.
                    try:
                        filter.reset()
                        # Clear timing baseline so the next update returns a zeroed orientation
                        filter.last_time = None
                    except Exception:
                        try:
                            filter.reset()
                        except Exception:
                            pass
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
                            # Update all thresholds for backward compatibility
                            filter.center_threshold_yaw = new_val
                            filter.center_threshold_pitch = new_val
                            filter.center_threshold_roll = new_val
                            log_info(logQueue, "Fusion Worker", f"Center threshold updated to {new_val}")
                            print(f"[Fusion Worker] Center threshold updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid center threshold: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting center threshold: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_center_threshold_yaw':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 180.0:  # Sanity check
                            filter.center_threshold_yaw = new_val
                            log_info(logQueue, "Fusion Worker", f"Yaw center threshold updated to {new_val}")
                            print(f"[Fusion Worker] Yaw center threshold updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid yaw center threshold: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting yaw center threshold: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_center_threshold_pitch':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 180.0:  # Sanity check
                            filter.center_threshold_pitch = new_val
                            log_info(logQueue, "Fusion Worker", f"Pitch center threshold updated to {new_val}")
                            print(f"[Fusion Worker] Pitch center threshold updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid pitch center threshold: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting pitch center threshold: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_center_threshold_roll':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 180.0:  # Sanity check
                            filter.center_threshold_roll = new_val
                            log_info(logQueue, "Fusion Worker", f"Roll center threshold updated to {new_val}")
                            print(f"[Fusion Worker] Roll center threshold updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid roll center threshold: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting roll center threshold: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_alpha_yaw':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 1.0:  # Alpha values must be between 0 and 1
                            filter.alpha_yaw = new_val
                            log_info(logQueue, "Fusion Worker", f"Alpha yaw updated to {new_val}")
                            print(f"[Fusion Worker] Alpha yaw updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid alpha yaw: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting alpha yaw: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_alpha_pitch':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 1.0:  # Alpha values must be between 0 and 1
                            filter.alpha_pitch = new_val
                            log_info(logQueue, "Fusion Worker", f"Alpha pitch updated to {new_val}")
                            print(f"[Fusion Worker] Alpha pitch updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid alpha pitch: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting alpha pitch: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_alpha_roll':
                    try:
                        new_val = float(cmd[1])
                        if 0.0 <= new_val <= 1.0:  # Alpha values must be between 0 and 1
                            filter.alpha_roll = new_val
                            log_info(logQueue, "Fusion Worker", f"Alpha roll updated to {new_val}")
                            print(f"[Fusion Worker] Alpha roll updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid alpha roll: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting alpha roll: {e}")
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
                
                # Send processing status to UI only when transitioning from inactive to active
                if not processing_active:
                    try:
                        if uiStatusQueue:
                            safe_queue_put(uiStatusQueue, ('processing', 'active'), timeout=QUEUE_PUT_TIMEOUT)
                        processing_active = True
                    except Exception as e:
                        print(f"[Fusion Worker] Failed to send UI processing status: {e}")
                        pass
                
                # Send drift correction status to UI only when it changes (non-blocking)
                if drift_active != last_drift_active:
                    try:
                        statusQueue.put_nowait(('drift_correction', drift_active))
                        last_drift_active = drift_active
                    except:
                        pass
                        
                # Send stationarity status to UI only when it changes (non-blocking)
                if is_stationary != last_stationary:
                    try:
                        statusQueue.put_nowait(('stationary', is_stationary))
                        last_stationary = is_stationary
                    except:
                        pass
                
                # Put Euler angles into output queues
                # Format: [Yaw, Pitch, Roll, X, Y, Z]
                euler_data = [yaw, pitch, roll, x, y, z]

                # Publish to main euler queue (for UDP) - non-blocking for real-time
                try:
                    eulerQueue.put_nowait(euler_data)
                except:
                    # Drop frame if queue full rather than blocking
                    pass
                
                # Send to display queue with queue health monitoring
                if eulerDisplayQueue is not None:
                    try:
                        # Check queue health and log if getting full
                        queue_size = eulerDisplayQueue.qsize()
                        max_size = getattr(eulerDisplayQueue, '_maxsize', 60)
                        
                        # Only apply sampling if queue is very full (>90%)
                        if max_size > 0 and queue_size / max_size > 0.9:
                            # Queue critically full - skip some frames and log warning
                            filter._frame_counter = getattr(filter, '_frame_counter', 0) + 1
                            if filter._frame_counter % 2 == 0:  # Send every 2nd frame
                                eulerDisplayQueue.put_nowait(euler_data)
                            # Log critical queue state occasionally
                            if filter._frame_counter % 100 == 0:
                                print(f"[Fusion] Display queue critical: {queue_size}/{max_size} ({queue_size/max_size:.1%})")
                        else:
                            # Queue not full - send all frames
                            eulerDisplayQueue.put_nowait(euler_data)
                            # Log warning if queue getting full
                            if max_size > 0 and queue_size / max_size > 0.7:
                                filter._warning_counter = getattr(filter, '_warning_counter', 0) + 1
                                if filter._warning_counter % 200 == 0:  # Log every 200 frames when >70%
                                    print(f"[Fusion] Display queue warning: {queue_size}/{max_size} ({queue_size/max_size:.1%})")
                    except Exception as e:
                        # Track queue errors 
                        filter._error_counter = getattr(filter, '_error_counter', 0) + 1
                        if filter._error_counter % 50 == 0:  # Log every 50 errors
                            print(f"[Fusion] Display queue error #{filter._error_counter}: {e}")
                        pass
                
            except ValueError as e:
                # Skip malformed/invalid lines (parse_imu_line raises ValueError)
                # Only log occasionally to avoid spam
                continue
            except Exception as e:
                log_error(logQueue, "Fusion Worker", f"Unexpected error processing data: {e}")
                continue
        
        # Only add minimal sleep if no data was processed to prevent busy waiting
        if line is None:
            time.sleep(FUSION_LOOP_SLEEP_MS / 1000.0)
    
    except KeyboardInterrupt:
        pass
    finally:
        # Send processing inactive status when stopping
        try:
            if uiStatusQueue:
                safe_queue_put(uiStatusQueue, ('processing', 'inactive'), timeout=QUEUE_PUT_TIMEOUT)
            processing_active = False
        except Exception:
            pass
        log_info(logQueue, "Fusion Worker", "Stopped")
        print("[Fusion Worker] Stopped.")
