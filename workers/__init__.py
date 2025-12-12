"""
Workers package for frankentrack.

This package contains all worker modules for the multiprocess architecture.
Each worker can be imported individually for use in the process manager.

Available workers:
- gui_wrk: PyQt5 tabbed GUI interface worker
- fusion_wrk: Sensor fusion and complementary filter worker
- serial_wrk: Serial communication worker for Arduino sensors
- udp_wrk: UDP network output worker
- process_man: Process manager for coordinating all workers

Workers are designed to run in separate processes with queue-based communication.
"""

# Import worker modules for easy access
from . import gui_wrk
from . import fusion_wrk
from . import serial_wrk
from . import udp_wrk
from . import process_man

# Import main worker entry points
from .gui_wrk import run_worker as run_gui_worker, start_gui_worker
from .fusion_wrk import run_worker as run_fusion_worker
from .serial_wrk import run_worker as run_serial_worker
from .udp_wrk import run_worker as run_udp_worker

# Import process manager class
from .process_man import ProcessHandler

__all__ = [
    # Worker modules
    'gui_wrk',
    'fusion_wrk',
    'serial_wrk',
    'udp_wrk',
    'process_man',
    
    # Worker entry points
    'run_gui_worker',
    'start_gui_worker',
    'run_fusion_worker',
    'run_serial_worker',
    'run_udp_worker',
    
    # Process management
    'ProcessHandler',
]
