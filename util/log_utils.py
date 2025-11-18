"""Minimal logging utilities for worker processes."""

def log(logQueue, level, worker_name, message):
    """
    Send a log message to the log queue.
    
    Args:
        logQueue: Queue to send log messages to
        level: 'INFO', 'WARN', 'ERROR', 'DEBUG'
        worker_name: Name of the worker (e.g., 'SerialWorker')
        message: Log message string
    """
    if logQueue is None:
        return
    
    try:
        logQueue.put_nowait((level, worker_name, message))
    except Exception:
        try:
            logQueue.put((level, worker_name, message), timeout=0.01)
        except Exception:
            # Can't log, queue full - drop message
            pass


def log_error(logQueue, worker_name, message):
    """Convenience wrapper for ERROR level."""
    log(logQueue, 'ERROR', worker_name, message)


def log_warning(logQueue, worker_name, message):
    """Convenience wrapper for WARN level."""
    log(logQueue, 'WARN', worker_name, message)


def log_info(logQueue, worker_name, message):
    """Convenience wrapper for INFO level."""
    log(logQueue, 'INFO', worker_name, message)
