"""
Camera diagnostic and testing tool for PS3 Eye and other devices.

Run with: python tools/test_camera.py

This script helps diagnose camera enumeration issues and test different
OpenCV backends, settings, and workarounds. Useful for troubleshooting
devices like the PS3 Eye that may only appear on certain backends or
with specific configurations.
"""

import cv2
import time
import sys
import traceback


def print_menu():
    """Display the main menu."""
    print("\n" + "="*70)
    print("Camera Diagnostic Tool")
    print("="*70)
    print("1. List all available backends")
    print("2. Enumerate cameras (0-15) with all backends")
    print("3. Test specific camera index")
    print("4. Test specific camera with specific backend")
    print("5. Test all backends for a specific camera")
    print("6. Live preview from camera (press 'q' to quit)")
    print("7. Test capture settings (FPS, resolution)")
    print("8. Continuous enumeration (watch for devices)")
    print("9. Test CAP_PROP queries on device")
    print("10. PS3 Eye optimization test (index 1)")
    print("11. PS3 Eye ADVANCED test (property order variations)")
    print("0. Exit")
    print("="*70)


def get_backend_name(backend_id):
    """Get human-readable name for backend ID."""
    backend_map = {
        cv2.CAP_ANY: "CAP_ANY",
        cv2.CAP_DSHOW: "CAP_DSHOW",
        cv2.CAP_MSMF: "CAP_MSMF",
    }
    # Try additional backends if available
    for name in ['CAP_VFW', 'CAP_MF', 'CAP_AVFOUNDATION', 'CAP_V4L2', 'CAP_GSTREAMER']:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            backend_map[val] = name
    
    return backend_map.get(backend_id, f"Backend_{backend_id}")


def list_backends():
    """List all available OpenCV backends."""
    print("\n--- Available OpenCV Backends ---")
    backends = []
    
    backend_names = [
        'CAP_ANY', 'CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW',
        'CAP_AVFOUNDATION', 'CAP_V4L2', 'CAP_GSTREAMER', 'CAP_FFMPEG'
    ]
    
    for name in backend_names:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            backends.append((name, val))
            print(f"  {name:20} = {val}")
    
    print(f"\nTotal: {len(backends)} backends available")
    return backends


def try_open_camera(cam_index, backend=None, timeout=2.0, verbose=True):
    """
    Attempt to open a camera with optional backend.
    
    Args:
        cam_index: Camera device index
        backend: OpenCV backend constant (or None for default)
        timeout: Seconds to wait for isOpened()
        verbose: Print detailed messages
    
    Returns:
        Tuple of (success, cap_object, backend_used, error_msg)
    """
    cap = None
    error_msg = None
    
    try:
        if backend is None:
            if verbose:
                print(f"  Trying camera {cam_index} with default constructor...")
            cap = cv2.VideoCapture(cam_index)
        else:
            backend_name = get_backend_name(backend)
            if verbose:
                print(f"  Trying camera {cam_index} with {backend_name}...")
            cap = cv2.VideoCapture(cam_index, backend)
        
        # Poll for isOpened() with timeout
        start = time.time()
        while not cap.isOpened() and (time.time() - start) < timeout:
            time.sleep(0.05)
        
        if cap.isOpened():
            if verbose:
                print(f"    ✓ SUCCESS: Camera {cam_index} opened")
            return (True, cap, backend, None)
        else:
            if verbose:
                print(f"    ✗ FAILED: Timeout waiting for camera {cam_index}")
            error_msg = "Timeout"
            try:
                cap.release()
            except Exception:
                pass
            return (False, None, backend, error_msg)
    
    except Exception as e:
        error_msg = str(e)
        if verbose:
            print(f"    ✗ EXCEPTION: {error_msg}")
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        return (False, None, backend, error_msg)


def enumerate_cameras(max_index=15):
    """Enumerate cameras 0-max_index across all backends."""
    print(f"\n--- Enumerating Cameras (0-{max_index}) ---")
    
    # Get available backends
    backends = []
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW']:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            if val not in backends:
                backends.append(val)
    
    # Also try default (no backend flag)
    backends.append(None)
    
    found_any = False
    results = []
    
    for idx in range(max_index + 1):
        found_this_idx = False
        print(f"\nCamera {idx}:")
        
        for backend in backends:
            success, cap, backend_used, error = try_open_camera(idx, backend, timeout=1.5, verbose=False)
            
            backend_name = get_backend_name(backend) if backend else "default"
            
            if success:
                print(f"  ✓ {backend_name:20} -> OPENED")
                found_this_idx = True
                found_any = True
                results.append((idx, backend_name, "SUCCESS"))
                
                # Try to read a frame to verify it works
                try:
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        print(f"    Frame: {w}x{h}")
                except Exception as e:
                    print(f"    Warning: Could not read frame: {e}")
                
                try:
                    cap.release()
                except Exception:
                    pass
                break  # Found working backend for this index
            else:
                results.append((idx, backend_name, f"FAILED: {error if error else 'unknown'}"))
        
        if not found_this_idx:
            print(f"  ✗ Not detected on any backend")
    
    print(f"\n--- Summary ---")
    if found_any:
        print("Cameras found:")
        for idx, backend, status in results:
            if "SUCCESS" in status:
                print(f"  Camera {idx} on {backend}")
    else:
        print("No cameras detected.")
    
    return results


def test_specific_camera():
    """Test a specific camera index with all backends."""
    try:
        cam_index = int(input("\nEnter camera index (0-15): "))
    except ValueError:
        print("Invalid index")
        return
    
    print(f"\n--- Testing Camera {cam_index} ---")
    
    backends = []
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW']:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            backends.append((name, val))
    backends.append(("default", None))
    
    for name, backend in backends:
        print(f"\nTrying {name}:")
        success, cap, _, error = try_open_camera(cam_index, backend, timeout=2.0, verbose=True)
        
        if success:
            # Query properties
            print(f"  Properties:")
            props = [
                ('CAP_PROP_FRAME_WIDTH', cv2.CAP_PROP_FRAME_WIDTH),
                ('CAP_PROP_FRAME_HEIGHT', cv2.CAP_PROP_FRAME_HEIGHT),
                ('CAP_PROP_FPS', cv2.CAP_PROP_FPS),
                ('CAP_PROP_BACKEND', cv2.CAP_PROP_BACKEND),
            ]
            for prop_name, prop_id in props:
                try:
                    val = cap.get(prop_id)
                    print(f"    {prop_name:25} = {val}")
                except Exception as e:
                    print(f"    {prop_name:25} = Error: {e}")
            
            # Try to read a frame
            print(f"  Reading frame...")
            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    print(f"    ✓ Frame captured: {w}x{h}, dtype={frame.dtype}")
                else:
                    print(f"    ✗ Failed to read frame")
            except Exception as e:
                print(f"    ✗ Exception reading frame: {e}")
            
            try:
                cap.release()
            except Exception:
                pass
            
            print(f"  SUCCESS with {name}")
            break
    else:
        print(f"\n✗ Could not open camera {cam_index} with any backend")


def test_camera_backend():
    """Test specific camera with specific backend."""
    try:
        cam_index = int(input("\nEnter camera index (0-15): "))
    except ValueError:
        print("Invalid index")
        return
    
    print("\nAvailable backends:")
    backends = []
    idx = 1
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW', 'CAP_ANY']:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            backends.append((name, val))
            print(f"  {idx}. {name}")
            idx += 1
    backends.append(("default", None))
    print(f"  {idx}. default (no backend flag)")
    
    try:
        choice = int(input(f"\nSelect backend (1-{len(backends)}): "))
        if choice < 1 or choice > len(backends):
            print("Invalid choice")
            return
        backend_name, backend = backends[choice - 1]
    except ValueError:
        print("Invalid choice")
        return
    
    print(f"\n--- Testing Camera {cam_index} with {backend_name} ---")
    success, cap, _, error = try_open_camera(cam_index, backend, timeout=3.0, verbose=True)
    
    if success:
        print("\nCamera opened successfully!")
        try:
            cap.release()
        except Exception:
            pass
    else:
        print(f"\nFailed to open camera: {error}")


def live_preview():
    """Live preview from a camera."""
    try:
        cam_index = int(input("\nEnter camera index (0-15): "))
    except ValueError:
        print("Invalid index")
        return
    
    print(f"\n--- Live Preview from Camera {cam_index} ---")
    print("Trying to open with all backends...")
    
    backends = []
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW']:
        if hasattr(cv2, name):
            val = getattr(cv2, name)
            backends.append((name, val))
    backends.append(("default", None))
    
    cap = None
    working_backend = None
    
    for name, backend in backends:
        success, cap, _, _ = try_open_camera(cam_index, backend, timeout=2.0, verbose=False)
        if success:
            working_backend = name
            print(f"✓ Opened with {name}")
            break
    
    if cap is None or not cap.isOpened():
        print("✗ Could not open camera with any backend")
        return
    
    print("\nStarting preview... Press 'q' to quit")
    print("(If no window appears, check that cv2.imshow is supported)")
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("Failed to read frame")
                break
            
            frame_count += 1
            
            # Calculate FPS
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
            else:
                fps = 0
            
            # Draw info on frame
            h, w = frame.shape[:2]
            cv2.putText(frame, f"Camera {cam_index} ({working_backend})", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"FPS: {fps:.1f} | {w}x{h}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow(f"Camera {cam_index}", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError during preview: {e}")
        traceback.print_exc()
    finally:
        try:
            cap.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
    
    print(f"\nPreview ended. Captured {frame_count} frames in {elapsed:.1f}s ({fps:.1f} FPS)")


def test_capture_settings():
    """Test different capture settings (resolution, FPS)."""
    try:
        cam_index = int(input("\nEnter camera index (0-15): "))
    except ValueError:
        print("Invalid index")
        return
    
    print(f"\n--- Testing Capture Settings for Camera {cam_index} ---")
    
    # Try to open with best backend
    backends = []
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW']:
        if hasattr(cv2, name):
            backends.append((name, getattr(cv2, name)))
    backends.append(("default", None))
    
    cap = None
    working_backend = None
    for name, backend in backends:
        success, cap, _, _ = try_open_camera(cam_index, backend, timeout=2.0, verbose=False)
        if success:
            working_backend = name
            print(f"✓ Opened with {name}")
            break
    
    if cap is None:
        print("✗ Could not open camera")
        return
    
    # Test different resolutions
    resolutions = [
        (320, 240),
        (640, 480),
        (800, 600),
        (1280, 720),
        (1920, 1080),
    ]
    
    print("\n--- Testing Resolutions ---")
    for w, h in resolutions:
        print(f"\nRequesting {w}x{h}:")
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            
            actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"  Reported: {int(actual_w)}x{int(actual_h)}")
            
            # Try to read a frame to verify
            ret, frame = cap.read()
            if ret and frame is not None:
                fh, fw = frame.shape[:2]
                print(f"  Actual frame: {fw}x{fh}")
                if fw == w and fh == h:
                    print(f"  ✓ Match")
                else:
                    print(f"  ⚠ Mismatch")
            else:
                print(f"  ✗ Could not read frame")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Test FPS settings
    fps_values = [15, 30, 60, 120]
    print("\n--- Testing FPS Settings ---")
    for fps in fps_values:
        print(f"\nRequesting {fps} FPS:")
        try:
            cap.set(cv2.CAP_PROP_FPS, fps)
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"  Reported: {actual_fps:.1f} FPS")
            
            # Measure actual FPS
            frame_count = 0
            start = time.time()
            while frame_count < 30:  # Read 30 frames
                ret, _ = cap.read()
                if ret:
                    frame_count += 1
            elapsed = time.time() - start
            measured_fps = frame_count / elapsed if elapsed > 0 else 0
            print(f"  Measured: {measured_fps:.1f} FPS")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    try:
        cap.release()
    except Exception:
        pass


def continuous_enumeration():
    """Continuously enumerate cameras (useful for watching device connects/disconnects)."""
    print("\n--- Continuous Camera Enumeration ---")
    print("Watching for cameras... Press Ctrl+C to stop")
    
    try:
        while True:
            print(f"\n[{time.strftime('%H:%M:%S')}] Scanning...")
            found = []
            
            for idx in range(8):  # Check first 8 indices
                # Try with DirectShow (fastest on Windows)
                backend = getattr(cv2, 'CAP_DSHOW', None)
                success, cap, _, _ = try_open_camera(idx, backend, timeout=0.5, verbose=False)
                if success:
                    found.append(idx)
                    try:
                        cap.release()
                    except Exception:
                        pass
            
            if found:
                print(f"  Cameras detected: {found}")
            else:
                print(f"  No cameras detected")
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\nStopped.")


def query_camera_properties():
    """Query all CAP_PROP_* properties for a camera."""
    try:
        cam_index = int(input("\nEnter camera index (0-15): "))
    except ValueError:
        print("Invalid index")
        return
    
    print(f"\n--- Querying Camera {cam_index} Properties ---")
    
    # Try to open
    backends = []
    for name in ['CAP_DSHOW', 'CAP_MSMF', 'CAP_MF', 'CAP_VFW']:
        if hasattr(cv2, name):
            backends.append((name, getattr(cv2, name)))
    backends.append(("default", None))
    
    cap = None
    for name, backend in backends:
        success, cap, _, _ = try_open_camera(cam_index, backend, timeout=2.0, verbose=False)
        if success:
            print(f"✓ Opened with {name}\n")
            break
    
    if cap is None:
        print("✗ Could not open camera")
        return
    
    # Query all known CAP_PROP_* constants
    props = [
        ('CAP_PROP_POS_MSEC', cv2.CAP_PROP_POS_MSEC),
        ('CAP_PROP_POS_FRAMES', cv2.CAP_PROP_POS_FRAMES),
        ('CAP_PROP_POS_AVI_RATIO', cv2.CAP_PROP_POS_AVI_RATIO),
        ('CAP_PROP_FRAME_WIDTH', cv2.CAP_PROP_FRAME_WIDTH),
        ('CAP_PROP_FRAME_HEIGHT', cv2.CAP_PROP_FRAME_HEIGHT),
        ('CAP_PROP_FPS', cv2.CAP_PROP_FPS),
        ('CAP_PROP_FOURCC', cv2.CAP_PROP_FOURCC),
        ('CAP_PROP_FRAME_COUNT', cv2.CAP_PROP_FRAME_COUNT),
        ('CAP_PROP_FORMAT', cv2.CAP_PROP_FORMAT),
        ('CAP_PROP_MODE', cv2.CAP_PROP_MODE),
        ('CAP_PROP_BRIGHTNESS', cv2.CAP_PROP_BRIGHTNESS),
        ('CAP_PROP_CONTRAST', cv2.CAP_PROP_CONTRAST),
        ('CAP_PROP_SATURATION', cv2.CAP_PROP_SATURATION),
        ('CAP_PROP_HUE', cv2.CAP_PROP_HUE),
        ('CAP_PROP_GAIN', cv2.CAP_PROP_GAIN),
        ('CAP_PROP_EXPOSURE', cv2.CAP_PROP_EXPOSURE),
        ('CAP_PROP_CONVERT_RGB', cv2.CAP_PROP_CONVERT_RGB),
        ('CAP_PROP_BACKEND', cv2.CAP_PROP_BACKEND),
        ('CAP_PROP_BUFFERSIZE', cv2.CAP_PROP_BUFFERSIZE),
    ]
    
    print("Properties:")
    for name, prop_id in props:
        try:
            val = cap.get(prop_id)
            print(f"  {name:30} = {val}")
        except Exception as e:
            print(f"  {name:30} = Error: {e}")
    
    try:
        cap.release()
    except Exception:
        pass


def ps3_eye_optimization():
    """Test PS3 Eye specific optimizations on camera index 1."""
    cam_index = 1
    print(f"\n--- PS3 Eye Optimization Test (Camera {cam_index}) ---")
    print("The PS3 Eye supports high FPS: 120 FPS @ 320x240 or 60 FPS @ 640x480")
    print("Testing different backend/resolution/FPS combinations...\n")
    
    # Test configurations optimized for PS3 Eye
    configs = [
        # (backend_name, backend, width, height, fps, description)
        ('CAP_DSHOW', getattr(cv2, 'CAP_DSHOW', None), 320, 240, 120, "Low res, max FPS"),
        ('CAP_DSHOW', getattr(cv2, 'CAP_DSHOW', None), 320, 240, 60, "Low res, 60 FPS"),
        ('CAP_DSHOW', getattr(cv2, 'CAP_DSHOW', None), 640, 480, 60, "Medium res, 60 FPS"),
        ('CAP_DSHOW', getattr(cv2, 'CAP_DSHOW', None), 640, 480, 30, "Medium res, 30 FPS"),
        ('CAP_MSMF', getattr(cv2, 'CAP_MSMF', None), 320, 240, 60, "MSMF low res"),
        ('CAP_MSMF', getattr(cv2, 'CAP_MSMF', None), 640, 480, 30, "MSMF medium res"),
    ]
    
    results = []
    
    for backend_name, backend, width, height, fps, desc in configs:
        if backend is None:
            print(f"✗ {backend_name} not available, skipping")
            continue
        
        print(f"\nTesting: {desc} ({backend_name}, {width}x{height} @ {fps} FPS)")
        
        try:
            cap = cv2.VideoCapture(cam_index, backend)
            
            # Wait for open
            start = time.time()
            while not cap.isOpened() and (time.time() - start) < 2.0:
                time.sleep(0.05)
            
            if not cap.isOpened():
                print(f"  ✗ Failed to open")
                try:
                    cap.release()
                except Exception:
                    pass
                continue
            
            # Set properties BEFORE reading first frame (important for DirectShow)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            
            # Also try setting buffer size to 1 (reduces latency)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            
            # Read reported values
            reported_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            reported_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            reported_fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"  Reported: {reported_w}x{reported_h} @ {reported_fps:.1f} FPS")
            
            # Measure actual FPS by capturing frames
            frame_count = 0
            start_measure = time.time()
            max_frames = 60  # Capture 60 frames to measure
            
            while frame_count < max_frames:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print(f"  ✗ Failed to read frame {frame_count}")
                    break
                frame_count += 1
            
            elapsed = time.time() - start_measure
            
            if frame_count > 0:
                measured_fps = frame_count / elapsed
                print(f"  Measured: {measured_fps:.1f} FPS (captured {frame_count} frames in {elapsed:.2f}s)")
                
                # Check actual frame size
                if frame is not None:
                    fh, fw = frame.shape[:2]
                    print(f"  Actual frame size: {fw}x{fh}")
                
                results.append({
                    'backend': backend_name,
                    'config': desc,
                    'requested': f"{width}x{height} @ {fps} FPS",
                    'reported': f"{reported_w}x{reported_h} @ {reported_fps:.1f} FPS",
                    'measured_fps': measured_fps,
                    'success': True
                })
                
                if measured_fps >= 50:
                    print(f"  ✓ GOOD - High framerate achieved!")
                elif measured_fps >= 25:
                    print(f"  ⚠ OK - Acceptable framerate")
                else:
                    print(f"  ⚠ LOW - Framerate below expected")
            else:
                print(f"  ✗ Could not measure FPS")
                results.append({
                    'backend': backend_name,
                    'config': desc,
                    'success': False
                })
            
            try:
                cap.release()
            except Exception:
                pass
        
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            results.append({
                'backend': backend_name,
                'config': desc,
                'success': False,
                'error': str(e)
            })
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY - Best Configurations:")
    print("="*70)
    
    successful = [r for r in results if r.get('success')]
    if successful:
        # Sort by measured FPS
        successful.sort(key=lambda x: x.get('measured_fps', 0), reverse=True)
        
        print("\nTop performers:")
        for i, r in enumerate(successful[:3], 1):
            print(f"\n{i}. {r['config']}")
            print(f"   Backend: {r['backend']}")
            print(f"   Requested: {r['requested']}")
            print(f"   Measured FPS: {r['measured_fps']:.1f}")
        
        best = successful[0]
        print("\n" + "="*70)
        print("RECOMMENDATION for camera_wrk.py:")
        print("="*70)
        print(f"Use backend: {best['backend']}")
        print(f"Config: {best['config']}")
        print(f"Achieved: {best['measured_fps']:.1f} FPS")
        print("\nTo apply this in your app, set these in the camera panel:")
        print(f"  - Camera Index: {cam_index}")
        print(f"  - Resolution: {best['requested'].split('@')[0].strip()}")
        print(f"  - FPS: {best['requested'].split('@')[1].strip()}")
    else:
        print("\n✗ No configurations succeeded")
    
    print("\n")


def ps3_eye_advanced_test():
    """Advanced PS3 Eye test with different property-setting strategies."""
    cam_index = 1
    print(f"\n--- PS3 Eye ADVANCED Test (Camera {cam_index}) ---")
    print("Testing different property-setting strategies and orders...")
    print("DirectShow cameras often require specific property sequences.\n")
    
    backend = getattr(cv2, 'CAP_DSHOW', None)
    if backend is None:
        print("✗ CAP_DSHOW not available")
        return
    
    strategies = [
        {
            'name': 'Strategy 1: Set BEFORE first read (FPS→Width→Height)',
            'steps': [
                ('set_fps_first', True),
                ('set_resolution', True),
                ('set_buffer', True),
            ]
        },
        {
            'name': 'Strategy 2: Set AFTER first read',
            'steps': [
                ('read_dummy', True),
                ('set_fps_first', True),
                ('set_resolution', True),
                ('set_buffer', True),
            ]
        },
        {
            'name': 'Strategy 3: Set Width→Height→FPS (reverse order)',
            'steps': [
                ('set_resolution', True),
                ('set_fps_after', True),
                ('set_buffer', True),
            ]
        },
        {
            'name': 'Strategy 4: Set FOURCC + resolution',
            'steps': [
                ('set_fourcc_mjpeg', True),
                ('set_resolution', True),
                ('set_fps_first', True),
                ('set_buffer', True),
            ]
        },
        {
            'name': 'Strategy 5: Multiple set attempts',
            'steps': [
                ('set_resolution', True),
                ('set_fps_first', True),
                ('read_dummy', True),
                ('set_resolution', True),  # Set again
                ('set_fps_first', True),  # Set again
                ('set_buffer', True),
            ]
        },
    ]
    
    # Test configs
    test_configs = [
        (320, 240, 120, "320x240 @ 120 FPS"),
        (320, 240, 60, "320x240 @ 60 FPS"),
        (640, 480, 60, "640x480 @ 60 FPS"),
    ]
    
    best_result = None
    best_fps = 0
    
    for config_w, config_h, config_fps, config_desc in test_configs:
        print(f"\n{'='*70}")
        print(f"TARGET: {config_desc}")
        print(f"{'='*70}")
        
        for strategy in strategies:
            print(f"\n{strategy['name']}")
            
            try:
                cap = cv2.VideoCapture(cam_index, backend)
                
                # Wait for open
                start = time.time()
                while not cap.isOpened() and (time.time() - start) < 2.0:
                    time.sleep(0.05)
                
                if not cap.isOpened():
                    print(f"  ✗ Failed to open")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    continue
                
                # Execute strategy steps
                for step, _ in strategy['steps']:
                    if step == 'set_fps_first':
                        cap.set(cv2.CAP_PROP_FPS, config_fps)
                    elif step == 'set_fps_after':
                        cap.set(cv2.CAP_PROP_FPS, config_fps)
                    elif step == 'set_resolution':
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config_w)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config_h)
                    elif step == 'set_buffer':
                        try:
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        except Exception:
                            pass
                    elif step == 'read_dummy':
                        try:
                            cap.read()
                        except Exception:
                            pass
                    elif step == 'set_fourcc_mjpeg':
                        try:
                            # MJPEG fourcc
                            fourcc = cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')
                            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                        except Exception:
                            pass
                
                # Check what we got
                actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps_reported = cap.get(cv2.CAP_PROP_FPS)
                
                # Measure real FPS
                frame_count = 0
                start_measure = time.time()
                max_frames = 30
                
                while frame_count < max_frames:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        break
                    frame_count += 1
                
                elapsed = time.time() - start_measure
                
                if frame_count > 0 and frame is not None:
                    measured_fps = frame_count / elapsed
                    fh, fw = frame.shape[:2]
                    
                    # Check if resolution matches
                    res_match = (fw == config_w and fh == config_h)
                    res_indicator = "✓" if res_match else "✗"
                    
                    # Check if FPS is good
                    fps_good = measured_fps >= (config_fps * 0.8)  # Within 80% of target
                    fps_indicator = "✓" if fps_good else "⚠"
                    
                    print(f"  {res_indicator} Resolution: {fw}x{fh} (wanted {config_w}x{config_h})")
                    print(f"  {fps_indicator} Measured FPS: {measured_fps:.1f} (wanted {config_fps}, reported {actual_fps_reported:.1f})")
                    
                    # Track best result
                    if res_match and measured_fps > best_fps:
                        best_fps = measured_fps
                        best_result = {
                            'strategy': strategy['name'],
                            'config': config_desc,
                            'width': fw,
                            'height': fh,
                            'fps': measured_fps,
                            'steps': strategy['steps']
                        }
                    
                    if res_match and fps_good:
                        print(f"  ✓✓ SUCCESS - This configuration works!")
                else:
                    print(f"  ✗ Failed to capture frames")
                
                try:
                    cap.release()
                except Exception:
                    pass
                
                # Small delay between tests
                time.sleep(0.2)
            
            except Exception as e:
                print(f"  ✗ Exception: {e}")
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL RECOMMENDATION:")
    print(f"{'='*70}")
    
    if best_result:
        print(f"\n✓ Best result found:")
        print(f"  Config: {best_result['config']}")
        print(f"  Strategy: {best_result['strategy']}")
        print(f"  Achieved: {best_result['width']}x{best_result['height']} @ {best_result['fps']:.1f} FPS")
        print(f"\n  Implementation steps:")
        for i, (step, _) in enumerate(best_result['steps'], 1):
            print(f"    {i}. {step}")
        print(f"\n  This is the sequence to use in camera_wrk.py for best results.")
    else:
        print("\n✗ No optimal configuration found.")
        print("   The PS3 Eye may require:")
        print("   - CL-Eye driver (https://codelaboratories.com/downloads/)")
        print("   - Or a 32-bit Python environment")
        print("   - Or try a different USB port/hub")
    
    print("\n")


def main():
    """Main menu loop."""
    print("\nOpenCV Camera Diagnostic Tool")
    print(f"OpenCV version: {cv2.__version__}")
    print(f"Python version: {sys.version}")
    
    while True:
        print_menu()
        choice = input("\nSelect option: ").strip()
        
        if choice == '1':
            list_backends()
        elif choice == '2':
            enumerate_cameras()
        elif choice == '3':
            test_specific_camera()
        elif choice == '4':
            test_camera_backend()
        elif choice == '5':
            test_specific_camera()  # Same as option 3
        elif choice == '6':
            live_preview()
        elif choice == '7':
            test_capture_settings()
        elif choice == '8':
            continuous_enumeration()
        elif choice == '9':
            query_camera_properties()
        elif choice == '10':
            ps3_eye_optimization()
        elif choice == '11':
            ps3_eye_advanced_test()
        elif choice == '0':
            print("\nExiting...")
            break
        else:
            print("\nInvalid option")
        
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        traceback.print_exc()
