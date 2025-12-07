"""
GUI Worker Launcher for frankentrack

This module provides a unified interface for launching either the tkinter or PyQt5 GUI
based on the GUI_BACKEND configuration setting. It maintains compatibility with the
existing process manager while enabling the new tabbed PyQt5 interface.

Supported backends:
- 'tkinter': Original tkinter GUI with full panel layout
- 'pyqt': New PyQt5 GUI with tabbed interface  
- 'pyqt_tabbed': PyQt5 tabbed interface (same as 'pyqt')
"""

import sys
from config.config import GUI_BACKEND


def run_worker(messageQueue, serialDisplayQueue, statusQueue, stop_event, 
               eulerDisplayQueue, controlQueue, serialControlQueue, 
               translationDisplayQueue, cameraControlQueue, cameraPreviewQueue, 
               udpControlQueue, logQueue):
    """
    Launch the appropriate GUI worker based on GUI_BACKEND configuration.
    
    This function maintains the same interface as the original gui_wrk.run_worker
    to ensure compatibility with the existing process manager.
    
    Args:
        messageQueue: Queue for general log messages
        serialDisplayQueue: Queue for raw serial data  
        statusQueue: Queue for status updates
        stop_event: Multiprocessing event for shutdown coordination
        eulerDisplayQueue: Queue for orientation angles
        controlQueue: Queue for fusion worker commands  
        serialControlQueue: Queue for serial worker commands
        translationDisplayQueue: Queue for position data
        cameraControlQueue: Queue for camera worker commands
        cameraPreviewQueue: Queue for camera preview frames
        udpControlQueue: Queue for UDP worker commands  
        logQueue: Queue for log messages
    """
    backend = GUI_BACKEND.lower()
    
    print(f"[GUI Launcher] Starting GUI with backend: {backend}")
    
    if backend in ['pyqt', 'pyqt_tabbed']:
        # Launch PyQt5 tabbed GUI
        try:
            from workers.gui_qt.gui_wrk_qt_tabbed import start_gui_worker
            
            def on_stop():
                """Callback when GUI is closed."""
                stop_event.set()
            
            start_gui_worker(
                serial_control_queue=serialControlQueue,
                fusion_control_queue=controlQueue,
                camera_control_queue=cameraControlQueue,
                udp_control_queue=udpControlQueue,
                status_queue=statusQueue,
                message_queue=messageQueue,
                stop_event=stop_event,
                on_stop_callback=on_stop
            )
            
        except Exception as e:
            print(f"[GUI Launcher] Error starting PyQt5 GUI: {e}")
            print("[GUI Launcher] Falling back to tkinter GUI...")
            _launch_tkinter_gui(
                messageQueue, serialDisplayQueue, statusQueue, stop_event,
                eulerDisplayQueue, controlQueue, serialControlQueue,
                translationDisplayQueue, cameraControlQueue, cameraPreviewQueue,
                udpControlQueue, logQueue
            )
            
    elif backend == 'tkinter':
        # Launch original tkinter GUI
        _launch_tkinter_gui(
            messageQueue, serialDisplayQueue, statusQueue, stop_event,
            eulerDisplayQueue, controlQueue, serialControlQueue,
            translationDisplayQueue, cameraControlQueue, cameraPreviewQueue,
            udpControlQueue, logQueue
        )
        
    else:
        print(f"[GUI Launcher] Unknown GUI backend '{backend}', defaulting to tkinter")
        _launch_tkinter_gui(
            messageQueue, serialDisplayQueue, statusQueue, stop_event,
            eulerDisplayQueue, controlQueue, serialControlQueue,
            translationDisplayQueue, cameraControlQueue, cameraPreviewQueue,
            udpControlQueue, logQueue
        )


def _launch_tkinter_gui(messageQueue, serialDisplayQueue, statusQueue, stop_event, 
                        eulerDisplayQueue, controlQueue, serialControlQueue, 
                        translationDisplayQueue, cameraControlQueue, cameraPreviewQueue, 
                        udpControlQueue, logQueue):
    """Launch the original tkinter GUI worker."""
    try:
        from workers.gui_wrk import run_worker as run_tkinter_worker
        
        run_tkinter_worker(
            messageQueue, serialDisplayQueue, statusQueue, stop_event,
            eulerDisplayQueue, controlQueue, serialControlQueue,
            translationDisplayQueue, cameraControlQueue, cameraPreviewQueue,
            udpControlQueue, logQueue
        )
        
    except Exception as e:
        print(f"[GUI Launcher] Error starting tkinter GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Test the launcher with mock queues
    import queue
    import multiprocessing
    
    print("Testing GUI launcher...")
    
    # Create mock queues
    mock_queues = {}
    queue_names = [
        'messageQueue', 'serialDisplayQueue', 'statusQueue', 'eulerDisplayQueue',
        'controlQueue', 'serialControlQueue', 'translationDisplayQueue',
        'cameraControlQueue', 'cameraPreviewQueue', 'udpControlQueue', 'logQueue'
    ]
    
    for name in queue_names:
        mock_queues[name] = queue.Queue()
    
    stop_event = multiprocessing.Event()
    
    # Test with current backend
    run_worker(
        messageQueue=mock_queues['messageQueue'],
        serialDisplayQueue=mock_queues['serialDisplayQueue'], 
        statusQueue=mock_queues['statusQueue'],
        stop_event=stop_event,
        eulerDisplayQueue=mock_queues['eulerDisplayQueue'],
        controlQueue=mock_queues['controlQueue'],
        serialControlQueue=mock_queues['serialControlQueue'],
        translationDisplayQueue=mock_queues['translationDisplayQueue'],
        cameraControlQueue=mock_queues['cameraControlQueue'],
        cameraPreviewQueue=mock_queues['cameraPreviewQueue'],
        udpControlQueue=mock_queues['udpControlQueue'],
        logQueue=mock_queues['logQueue']
    )