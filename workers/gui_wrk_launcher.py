"""
GUI Worker Launcher for frankentrack

This module provides the PyQt5 GUI worker interface for frankentrack.
The application has been fully migrated from tkinter to PyQt5.
"""

import sys


def run_worker(messageQueue, serialDisplayQueue, statusQueue, stop_event, 
               eulerDisplayQueue, controlQueue, serialControlQueue, 
               translationDisplayQueue, cameraControlQueue, cameraPreviewQueue, 
               udpControlQueue, logQueue, uiStatusQueue):
    """
    Launch the PyQt5 GUI worker.
    
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
    print("[GUI Launcher] Starting PyQt5 GUI...")
    
    try:
        from workers.gui_wrk_qt_tabbed import start_gui_worker
        
        def on_stop():
            """Callback when GUI is closed."""
            stop_event.set()
        
        start_gui_worker(
            serial_control_queue=serialControlQueue,
            fusion_control_queue=controlQueue,
            camera_control_queue=cameraControlQueue,
            udp_control_queue=udpControlQueue,
            status_queue=statusQueue,
            ui_status_queue=uiStatusQueue,
            message_queue=messageQueue,
            serial_display_queue=serialDisplayQueue,
            euler_display_queue=eulerDisplayQueue,
            translation_display_queue=translationDisplayQueue,
            camera_preview_queue=cameraPreviewQueue,
            log_queue=logQueue,
            stop_event=stop_event,
            on_stop_callback=on_stop
        )
        
    except Exception as e:
        print(f"[GUI Launcher] Error starting PyQt5 GUI: {e}")
        import traceback
        traceback.print_exc()
        raise



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
        'cameraControlQueue', 'cameraPreviewQueue', 'udpControlQueue', 'logQueue', 'uiStatusQueue'
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
        logQueue=mock_queues['logQueue'],
        uiStatusQueue=mock_queues['uiStatusQueue']
    )