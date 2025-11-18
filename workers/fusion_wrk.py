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
     ALPHA_DRIFT_CORRECTION,
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
        self.alpha_roll = 1  # Pure gyro for roll
        self.alpha_pitch = 1  # Pure gyro for pitch
        self.alpha_yaw = ALPHA_YAW  # From config
        self.alpha_drift = ALPHA_DRIFT_CORRECTION  # From config
        self.accel_threshold = accel_threshold
        self.center_threshold = center_threshold
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
            self.last_time = timestamp
            self.roll = 0.0
            self.pitch = 0.0
            self.yaw = 0.0
            return self.yaw, self.pitch, self.roll, False
        
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
        
        # Gyro integration (primary method)
        gyro_roll = self.roll + gx * dt
        gyro_pitch = self.pitch + gy * dt
        gyro_yaw = self.yaw + gz * dt
        
        # Check if accelerometer is measuring primarily gravity (sensor is stationary)
        ax, ay, az = accel
        accel_magnitude = np.sqrt(ax**2 + ay**2 + az**2)
        
        # Avoid division by zero and check if magnitude is close to 1g
        if accel_magnitude < 0.01:
            is_stationary = False
        else:
            is_stationary = abs(accel_magnitude - 1.0) < self.accel_threshold
        
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
            # Use pure gyro integration (holds angles perfectly)
            self.roll = gyro_roll
            self.pitch = gyro_pitch
            self.yaw = gyro_yaw
        
        # Normalize angles to [-180, 180]
        self.yaw = normalize_angle(self.yaw)
        self.pitch = normalize_angle(self.pitch)
        self.roll = normalize_angle(self.roll)
        
        return self.yaw, self.pitch, self.roll, drift_correction_active
    
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
    
    # Translation values (not used, set to 0)
    x, y, z = 0.0, 0.0, 0.0
    
    try:
        while not stop_event.is_set():
            # Check for control commands (non-blocking)
            cmd = safe_queue_get(controlQueue, timeout=0.0, default=None)
            if cmd is not None:
                # support control commands: 'reset' and ('set_center_threshold', value)
                if cmd == 'reset':
                    filter.reset()
                    log_info(logQueue, "Fusion Worker", "Orientation reset to zero")
                    print("[Fusion Worker] Orientation reset to zero")
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
            
            # Get data from serial queue with timeout
            line = safe_queue_get(serialQueue, timeout=QUEUE_GET_TIMEOUT, default=None)
            
            if line is None:
                continue
            
            try:
                # Parse and validate IMU data using error_utils
                timestamp, accel, gyro = parse_imu_line(line)
                
                # Update filter
                yaw, pitch, roll, drift_active = filter.update(gyro, accel, timestamp)
                
                # Send drift correction status to UI
                safe_queue_put(statusQueue, ('drift_correction', drift_active), 
                             timeout=QUEUE_PUT_TIMEOUT)
                
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
