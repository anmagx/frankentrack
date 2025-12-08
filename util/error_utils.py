"""
Error handling utilities for consistent exception handling across workers.

Provides helper functions for common error-prone operations like queue
communication, parsing, and validation.
"""

from queue import Full, Empty
from typing import Optional, Any, Tuple, List
import logging


def safe_queue_put(queue, item, timeout: float = 0.1, context: str = "", 
                   log_failures: bool = False, queue_name: str = None) -> bool:
    """
    Put item in queue with consistent error handling and monitoring.
    
    Attempts non-blocking put first, then blocking with timeout on failure.
    
    Args:
        queue: The queue to put the item in (multiprocessing.Queue or queue.Queue)
        item: The item to put in the queue
        timeout: Timeout in seconds for blocking put attempt
        context: Optional context string for error messages
        log_failures: If True, log failures (requires logging to be configured)
        queue_name: Name of queue for monitoring/diagnostics
    
    Returns:
        True if item was successfully queued, False otherwise
    """
    if queue is None:
        return False
    
    # Track queue health for diagnostics
    if queue_name and log_failures:
        try:
            queue_size = queue.qsize()
            max_size = getattr(queue, '_maxsize', 100)
            fill_ratio = queue_size / max_size if max_size > 0 else 0.0
            
            # Log warning if queue getting full
            if fill_ratio > 0.7:  # 70% threshold
                logging.warning(f"Queue '{queue_name}' is {fill_ratio:.1%} full ({queue_size}/{max_size})")
        except Exception:
            pass  # Don't let monitoring break the actual operation
    
    try:
        queue.put_nowait(item)
        return True
    except Full:
        try:
            queue.put(item, timeout=timeout)
            return True
        except (Full, Exception) as e:
            if log_failures:
                queue_info = f" (Queue: {queue_name})" if queue_name else ""
                msg = f"Queue full: {context}{queue_info}" if context else f"Queue full{queue_info}"
                logging.warning(msg)
            return False
    except Exception as e:
        if log_failures:
            queue_info = f" (Queue: {queue_name})" if queue_name else ""
            msg = f"Queue put failed: {context}{queue_info} - {e}" if context else f"Queue put failed{queue_info}: {e}"
            logging.error(msg)
        return False


def monitor_queue_health(queue, queue_name, log_callback=None):
    """
    Check and report queue health status.
    
    Args:
        queue: Queue to monitor
        queue_name: Human-readable name for the queue
        log_callback: Optional function to call with log messages
        
    Returns:
        dict: Queue health statistics
    """
    if queue is None:
        return {"error": "Queue is None"}
    
    try:
        queue_size = queue.qsize()
        max_size = getattr(queue, '_maxsize', 100)
        fill_ratio = queue_size / max_size if max_size > 0 else 0.0
        
        health_info = {
            "name": queue_name,
            "size": queue_size,
            "max_size": max_size, 
            "fill_ratio": fill_ratio,
            "status": "healthy"
        }
        
        # Determine status based on fill ratio
        if fill_ratio > 0.9:
            health_info["status"] = "critical"
            if log_callback:
                log_callback(f"CRITICAL: Queue '{queue_name}' is {fill_ratio:.1%} full!")
        elif fill_ratio > 0.7:
            health_info["status"] = "warning" 
            if log_callback:
                log_callback(f"WARNING: Queue '{queue_name}' is {fill_ratio:.1%} full")
        elif fill_ratio > 0.5:
            health_info["status"] = "moderate"
            
        return health_info
        
    except Exception as e:
        error_info = {"error": f"Failed to monitor queue '{queue_name}': {e}"}
        if log_callback:
            log_callback(f"Queue monitoring error: {e}")
        return error_info


def log_queue_stats(queue_dict, log_callback=None):
    """
    Log statistics for multiple queues.
    
    Args:
        queue_dict: Dictionary of {name: queue} pairs
        log_callback: Optional function for logging
    """
    stats = []
    for name, queue in queue_dict.items():
        health = monitor_queue_health(queue, name, log_callback)
        stats.append(health)
    
    # Log summary
    if log_callback:
        critical = sum(1 for s in stats if s.get("status") == "critical")
        warning = sum(1 for s in stats if s.get("status") == "warning")
        
        if critical > 0 or warning > 0:
            log_callback(f"Queue Health: {critical} critical, {warning} warnings out of {len(stats)} queues")
    
    return stats


def safe_queue_get(queue, timeout: float = 0.5, default=None) -> Any:
    """
    Get item from queue with consistent error handling.
    
    Args:
        queue: The queue to get from
        timeout: Timeout in seconds
        default: Value to return if queue is empty or error occurs
    
    Returns:
        Item from queue, or default value if unavailable
    """
    if queue is None:
        return default
    
    try:
        return queue.get(timeout=timeout)
    except Empty:
        return default
    except Exception:
        return default


def parse_csv_line(line: str, expected_count: int, name: str = "data") -> List[float]:
    """
    Safely parse CSV line with validation.
    
    Args:
        line: The CSV string to parse
        expected_count: Number of comma-separated values expected
        name: Name of the data type for error messages
    
    Returns:
        List of float values
    
    Raises:
        ValueError: If line doesn't have expected format or contains invalid numbers
    """
    if not line or not isinstance(line, str):
        raise ValueError(f"Invalid {name}: expected string, got {type(line)}")
    
    parts = line.strip().split(',')
    
    if len(parts) < expected_count:
        raise ValueError(
            f"Invalid {name}: expected {expected_count} fields, got {len(parts)}"
        )
    
    try:
        values = [float(p) for p in parts[:expected_count]]
    except ValueError as e:
        raise ValueError(f"Invalid {name}: non-numeric values - {e}")
    
    return values


def parse_imu_line(line: str) -> Tuple[float, Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Parse and validate IMU CSV line.
    
    Expected format: Time,Ax,Ay,Az,Gx,Gy,Gz
    
    Args:
        line: CSV string from IMU
    
    Returns:
        Tuple of (timestamp, accel_tuple, gyro_tuple)
        - timestamp: float in seconds
        - accel_tuple: (ax, ay, az) in g-units
        - gyro_tuple: (gx, gy, gz) in deg/s
    
    Raises:
        ValueError: If line is malformed or contains invalid/unreasonable values
    """
    values = parse_csv_line(line, 7, "IMU data")
    
    timestamp = values[0]
    accel = (values[1], values[2], values[3])
    gyro = (values[4], values[5], values[6])
    
    # Sanity checks
    if timestamp < 0:
        raise ValueError(f"Invalid timestamp: {timestamp} (negative)")
    
    # Check accelerometer magnitude (should be ~1g when stationary, <10g for normal movement)
    accel_mag_sq = sum(a**2 for a in accel)
    if accel_mag_sq > 100.0:  # More than 10g
        raise ValueError(f"Accelerometer magnitude too high: {accel_mag_sq**0.5:.2f}g")
    
    # Check gyro rates (most IMUs won't exceed ±2000 deg/s)
    if any(abs(g) > 2000.0 for g in gyro):
        raise ValueError(f"Gyro values out of range: {gyro}")
    
    return timestamp, accel, gyro


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between minimum and maximum.
    
    Args:
        value: The value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
    
    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def normalize_angle(angle: float, min_deg: float = -180.0, max_deg: float = 180.0) -> float:
    """
    Normalize angle to a specified range.
    
    Args:
        angle: Angle in degrees
        min_deg: Minimum of output range (default: -180)
        max_deg: Maximum of output range (default: 180)
    
    Returns:
        Normalized angle in [min_deg, max_deg)
    """
    range_deg = max_deg - min_deg
    while angle >= max_deg:
        angle -= range_deg
    while angle < min_deg:
        angle += range_deg
    return angle


def validate_numeric_range(value: float, min_val: float, max_val: float, 
                          name: str = "value") -> None:
    """
    Validate that a numeric value is within expected range.
    
    Args:
        value: The value to check
        min_val: Minimum acceptable value
        max_val: Maximum acceptable value
        name: Name of the value for error messages
    
    Raises:
        ValueError: If value is outside the acceptable range
    """
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"{name} out of range: {value} (expected {min_val} to {max_val})"
        )


def safe_float_convert(value: Any, default: float = 0.0, 
                      min_val: Optional[float] = None,
                      max_val: Optional[float] = None) -> float:
    """
    Safely convert value to float with optional range validation.
    
    Args:
        value: Value to convert to float
        default: Default value if conversion fails
        min_val: Optional minimum value (clamps if provided)
        max_val: Optional maximum value (clamps if provided)
    
    Returns:
        Float value, clamped to range if specified
    """
    try:
        result = float(value)
        if min_val is not None and max_val is not None:
            result = clamp(result, min_val, max_val)
        elif min_val is not None:
            result = max(min_val, result)
        elif max_val is not None:
            result = min(max_val, result)
        return result
    except (ValueError, TypeError):
        return default
