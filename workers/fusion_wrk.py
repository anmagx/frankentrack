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
     FUSION_LOOP_SLEEP_MS,
     DRIFT_SMOOTHING_TIME,
     DRIFT_TRANSITION_CURVE
)
from util.error_utils import (
    safe_queue_put,
    safe_queue_get,
    parse_imu_line,
    normalize_angle
)


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
        self.drift_smoothing_time = DRIFT_SMOOTHING_TIME
        self.drift_curve_type = DRIFT_TRANSITION_CURVE  # Load from config
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
        self._drift_correction_start = None
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

    def _slerp(self, a, b, t):
        """Spherical linear interpolation between quaternions for smoother drift correction.
        
        Provides much smoother interpolation than NLERP, especially for small corrections.
        """
        # Ensure we take the shorter path by checking dot product
        dot = np.dot(a, b)
        if dot < 0.0:
            b = -b  # Flip to shorter path
            dot = -dot
        
        # If quaternions are very close, use linear interpolation to avoid division by zero
        if dot > 0.9995:
            q = (1.0 - t) * a + t * b
            return self._quat_normalize(q)
        
        # Calculate angle between quaternions
        theta = np.arccos(np.clip(dot, -1.0, 1.0))
        sin_theta = np.sin(theta)
        
        # Spherical interpolation
        q = (np.sin((1.0 - t) * theta) / sin_theta) * a + (np.sin(t * theta) / sin_theta) * b
        return self._quat_normalize(q)

    def _nlerp(self, a, b, t):
        """Normalized linear interpolation between quaternions.
        
        Handles the case where quaternions represent the same rotation
        but have opposite signs (q and -q represent the same rotation).
        """
        # Ensure we take the shorter path by checking dot product
        dot = np.dot(a, b)
        if dot < 0.0:
            b = -b  # Flip to shorter path
        
        # Linear interpolation
        q = (1.0 - t) * a + t * b
        return self._quat_normalize(q)

    def _calculate_drift_factor(self, dt, elapsed_time):
        """Calculate drift correction factor based on curve type.
        
        Args:
            dt: Time delta for this update
            elapsed_time: Total time since drift correction started
            
        Returns:
            float: Correction factor between 0.0 and 1.0 for this frame
        """
        # Calculate progress through the smoothing period
        time_progress = min(elapsed_time / self.drift_smoothing_time, 1.0)
        
        if self.drift_curve_type == 'exponential':
            # Exponential approach - fast start, slow finish
            # Use cumulative approach for consistency
            target_progress = 1.0 - np.exp(-elapsed_time / self.drift_smoothing_time)
            if elapsed_time > dt:
                prev_progress = 1.0 - np.exp(-(elapsed_time - dt) / self.drift_smoothing_time)
                factor = min(target_progress - prev_progress, 0.4)
            else:
                factor = min(target_progress, 0.4)
        elif self.drift_curve_type == 'linear':
            # Linear progress - constant rate
            rate_per_second = 1.0 / self.drift_smoothing_time
            factor = min(rate_per_second * dt, 0.1)
        elif self.drift_curve_type == 'cosine':
            # Cosine ease-in-out - smooth start and finish
            target_progress = 0.5 * (1.0 - np.cos(np.pi * time_progress))
            if elapsed_time > dt:
                prev_time_progress = min((elapsed_time - dt) / self.drift_smoothing_time, 1.0)
                prev_progress = 0.5 * (1.0 - np.cos(np.pi * prev_time_progress))
                factor = min(target_progress - prev_progress, 0.4)
            else:
                factor = min(target_progress, 0.4)
        elif self.drift_curve_type == 'quadratic':
            # Quadratic ease-in - slow start, fast finish
            target_progress = time_progress * time_progress
            if elapsed_time > dt:
                prev_time_progress = min((elapsed_time - dt) / self.drift_smoothing_time, 1.0)
                prev_progress = prev_time_progress * prev_time_progress
                factor = min(target_progress - prev_progress, 0.4)
            else:
                factor = min(target_progress, 0.4)
        else:
            # Fallback to exponential
            target_progress = 1.0 - np.exp(-elapsed_time / self.drift_smoothing_time)
            if elapsed_time > dt:
                prev_progress = 1.0 - np.exp(-(elapsed_time - dt) / self.drift_smoothing_time)
                factor = min(target_progress - prev_progress, 0.4)
            else:
                factor = min(target_progress, 0.4)
        
        # Apply smoothness damping to reduce jitter
        # Scale factor based on angle magnitude - smaller corrections for smaller angles
        if elapsed_time < self.drift_smoothing_time:
            angle_magnitude = max(abs(getattr(self, '_last_yaw', 0)), 
                                abs(getattr(self, '_last_pitch', 0)), 
                                abs(getattr(self, '_last_roll', 0)))
            # Reduce factor for smaller angles to make correction even gentler
            if angle_magnitude < 2.0:  # Very close to center
                factor *= 0.5
            elif angle_magnitude < 1.0:  # Extremely close
                factor *= 0.3
        
        return factor

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

        # Helper function for angle differences
        def _angle_diff_fast(a, b):
            """Optimized smallest angle difference using modulo (O(1) vs O(n))."""
            diff = (a - b + 180.0) % 360.0 - 180.0
            return abs(diff)
        
        # Apply normal accelerometer blending first (when not in drift correction)
        if accel_ok:
            accel_roll, accel_pitch = self._accel_to_rp((ax, ay, az))
            
            # Get current orientation from gyro-integrated quaternion
            current_yaw, gyro_pitch, gyro_roll = self._euler_from_quat(q)
            
            # Blend roll and pitch separately using their respective alpha values
            # Higher alpha = more gyro, lower alpha = more accel
            blended_roll = self.alpha_roll * gyro_roll + (1.0 - self.alpha_roll) * accel_roll
            blended_pitch = self.alpha_pitch * gyro_pitch + (1.0 - self.alpha_pitch) * accel_pitch
            
            # Yaw stays from gyro integration (no magnetometer available)
            # Convert back to quaternion with blended roll/pitch and gyro yaw
            q = self._quat_from_euler(current_yaw, blended_pitch, blended_roll)
        
        # Check if we're looking approximately straight ahead AFTER accel correction
        # Require ALL axes to be within their respective drift correction thresholds
        yaw_est, pitch_est, roll_est = self._euler_from_quat(q)
        is_near_center = (_angle_diff_fast(yaw_est, 0) < self.center_threshold_yaw and 
                         _angle_diff_fast(pitch_est, 0) < self.center_threshold_pitch and
                         _angle_diff_fast(roll_est, 0) < self.center_threshold_roll)
        
        # Apply drift correction when stationary and near center
        drift_active = False
        if is_stationary and is_near_center:
            # Track drift correction start time
            if self._drift_correction_start is None:
                self._drift_correction_start = timestamp
            
            elapsed_time = timestamp - self._drift_correction_start
            # Smooth drift correction using configurable curve type
            smoothing_factor = self._calculate_drift_factor(dt, elapsed_time)
            
            # Pull quaternion towards zero rotation smoothly over time
            target_q = self._quat_from_euler(0.0, 0.0, 0.0)
            # Apply time-based smooth correction with selected curve using SLERP
            q = self._slerp(q, target_q, smoothing_factor)
            drift_active = True
            
            # For final convergence: if very close to zero and correction has been active long enough,
            # apply gentle correction to eliminate floating point precision issues
            if elapsed_time > self.drift_smoothing_time * 0.75:  # 75% through smoothing time
                final_yaw, final_pitch, final_roll = self._euler_from_quat(q)
                max_angle = max(abs(final_yaw), abs(final_pitch), abs(final_roll))
                if max_angle < 0.8:  # Tighter threshold for final convergence
                    # Apply gentle direct correction for final convergence
                    final_factor = min(0.2, dt * 3.0)  # Much gentler final correction
                    q = self._slerp(q, target_q, final_factor)  # Use SLERP for smoother final convergence
        else:
            # Reset drift correction timer when not correcting
            self._drift_correction_start = None

        q = self._quat_normalize(q)
        self.q = q

        yaw, pitch, roll = self._euler_from_quat(q)
        # Store angles for next frame's smoothness calculation
        self._last_yaw = yaw
        self._last_pitch = pitch
        self._last_roll = roll
        # normalize angles
        yaw = normalize_angle(yaw)
        pitch = normalize_angle(pitch)
        roll = normalize_angle(roll)

        return yaw, pitch, roll, drift_active, is_stationary

    def reset(self):
        """Reset quaternion orientation to identity (zero rotation)."""
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
        self._drift_correction_start = None
    
    


def run_worker(serialQueue, eulerQueue, eulerDisplayQueue, controlQueue, statusQueue, stop_event, logQueue=None, uiStatusQueue=None):
    """
    Fusion worker that reads IMU data from serialQueue and outputs Euler angles to eulerQueue.
    """
    from util.log_utils import log_info, log_error, log_warning
    
    log_info(logQueue, "Fusion Worker", "Starting complementary filter")
    print("[Fusion Worker] Starting complementary filter...")
    
    # Initialize quaternion filter with defaults from config. The GUI can update
    # filter parameters at runtime via the controlQueue.
    def _create_filter():
        return QuaternionComplementaryFilter(accel_threshold=ACCEL_THRESHOLD,
                                            center_threshold=DEFAULT_CENTER_THRESHOLD,
                                            logQueue=logQueue)

    filter = _create_filter()
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
    
    # Track data flow timeout
    last_data_time = None
    data_timeout = 2.0  # Send inactive after 2 seconds without data
    
    # Track status values to only send updates when they change
    last_drift_active = None
    last_stationary = None
    
    try:
        while not stop_event.is_set():
            # Check for control commands (non-blocking)
            cmd = safe_queue_get(controlQueue, timeout=0.0, default=None)
            if cmd is not None:
                # Support control commands: 'reset' and ('set_center_threshold', value)
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
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_drift_smoothing_time':
                    try:
                        new_val = float(cmd[1])
                        if new_val > 0.0:  # Drift smoothing time must be positive
                            filter.drift_smoothing_time = new_val
                            log_info(logQueue, "Fusion Worker", f"Drift smoothing time updated to {new_val}")
                            print(f"[Fusion Worker] Drift smoothing time updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid drift smoothing time: {new_val}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting drift smoothing time: {e}")
                elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == 'set_drift_curve_type':
                    try:
                        new_val = str(cmd[1]).lower()
                        valid_curves = ['exponential', 'linear', 'cosine', 'quadratic']
                        if new_val in valid_curves:
                            filter.drift_curve_type = new_val
                            log_info(logQueue, "Fusion Worker", f"Drift curve type updated to {new_val}")
                            print(f"[Fusion Worker] Drift curve type updated to {new_val}")
                        else:
                            log_warning(logQueue, "Fusion Worker", f"Invalid drift curve type: {new_val}. Valid options: {valid_curves}")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error setting drift curve type: {e}")
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
                            
                            # Notify GUI that calibration is starting
                            try:
                                safe_queue_put(statusQueue, ('gyro_calibrating', True), timeout=QUEUE_PUT_TIMEOUT)
                            except Exception:
                                pass
                            
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
                                    safe_queue_put(statusQueue, ('gyro_calibrating', False), timeout=QUEUE_PUT_TIMEOUT)
                                    safe_queue_put(statusQueue, ('gyro_calibrated', True), timeout=QUEUE_PUT_TIMEOUT)
                                except Exception:
                                    pass
                                log_info(logQueue, "Fusion Worker", f"Runtime gyro yaw bias recalibrated from {len(samples)} samples: {bias:.6f} deg/s")
                                print(f"[Fusion Worker] Gyro yaw bias recalibrated: {bias:.6f} deg/s")
                            else:
                                filter.gyro_calibrated = False
                                try:
                                    safe_queue_put(statusQueue, ('gyro_calibrating', False), timeout=QUEUE_PUT_TIMEOUT)
                                    safe_queue_put(statusQueue, ('gyro_calibrated', False), timeout=QUEUE_PUT_TIMEOUT)
                                except Exception:
                                    pass
                                log_warning(logQueue, "Fusion Worker", "Runtime gyro yaw bias recalibration collected 0 samples")
                    except Exception as e:
                        log_warning(logQueue, "Fusion Worker", f"Error during runtime gyro bias recalibration: {e}")
            
            # Get data from serial queue - drain queue to process most recent data
            line = None
            data_count = 0
            
            # Process multiple items per loop iteration to avoid queue backup
            while data_count < 5:  # Limit to prevent blocking too long
                latest_line = safe_queue_get(serialQueue, timeout=0.0, default=None)
                if latest_line is None:
                    break
                line = latest_line  # Keep most recent
                data_count += 1
            
            if line is None:
                # No data available - check if we should send inactive status
                current_time = time.time()
                
                # If we were previously active and haven't seen data for timeout period
                if (processing_active and last_data_time is not None and 
                    (current_time - last_data_time) > data_timeout):
                    try:
                        if uiStatusQueue:
                            safe_queue_put(uiStatusQueue, ('processing', 'inactive'), timeout=QUEUE_PUT_TIMEOUT)
                        processing_active = False
                        
                        # Also clear drift correction and stationary status when going inactive
                        try:
                            statusQueue.put_nowait(('drift_correction', False))
                            last_drift_active = False
                        except:
                            pass
                        try:
                            statusQueue.put_nowait(('stationary', False))
                            last_stationary = False
                        except:
                            pass
                            
                        log_info(logQueue, "Fusion Worker", "Processing inactive - no data received")
                        print("[Fusion Worker] Processing inactive - no data received")
                    except Exception as e:
                        print(f"[Fusion Worker] Failed to send UI inactive status: {e}")
                
                # Brief non-blocking delay to prevent CPU spinning
                time.sleep(0.001)  # 1ms delay instead of blocking timeout
                continue
            
            try:
                # Parse and validate IMU data using error_utils
                timestamp, accel, gyro = parse_imu_line(line)
                
                # Update data timestamp
                last_data_time = time.time()
                
                # Update filter
                yaw, pitch, roll, drift_active, is_stationary = filter.update(gyro, accel, timestamp)
                
                # Send processing status to UI only when transitioning from inactive to active
                if not processing_active:
                    try:
                        if uiStatusQueue:
                            safe_queue_put(uiStatusQueue, ('processing', 'active'), timeout=QUEUE_PUT_TIMEOUT)
                        processing_active = True
                        log_info(logQueue, "Fusion Worker", "Processing active - data received")
                        print("[Fusion Worker] Processing active - data received")
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
    
    except KeyboardInterrupt:
        pass
    finally:
        # Send processing inactive status when stopping
        try:
            if uiStatusQueue:
                safe_queue_put(uiStatusQueue, ('processing', 'inactive'), timeout=QUEUE_PUT_TIMEOUT)
            processing_active = False
            
            # Also clear drift correction and stationary status when stopping
            try:
                safe_queue_put(statusQueue, ('drift_correction', False), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass
            try:
                safe_queue_put(statusQueue, ('stationary', False), timeout=QUEUE_PUT_TIMEOUT)
            except Exception:
                pass
        except Exception:
            pass
        log_info(logQueue, "Fusion Worker", "Stopped")
        print("[Fusion Worker] Stopped.")
