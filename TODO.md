# Acceltrack - TODO List

## Critical (Before v0.1 Release)

### Documentation
- [x] Write README.md
  - [x] Project description and features
  - [x] Hardware requirements (IMU model, Arduino, camera specs)
  - [x] Installation instructions (including Python 3.8-3.13 requirement)
  - [x] Quick start guide
  - [x] Serial data format specification
  - [x] Configuration guide
  - [x] Troubleshooting section
- [x] Add LICENSE file (MIT recommended - matches your open collaboration goals)
- [x] Create .gitignore file
- [ ] Write ARCHITECTURE.md
  - [ ] System overview diagram
  - [ ] Process architecture (workers, queues)
  - [ ] Data flow diagram
  - [ ] Module responsibilities

### Cleanup
- [x] Remove gui_wrk_v2.py OR rename/restructure (decide on one GUI version)
- [x] Delete deprecated/test files if not needed for release
- [x] Remove __pycache__ directories from git tracking
- [x] Add missing __init__.py files:
  - [x] workers/gui/__init__.py
  - [x] workers/gui/managers/__init__.py

### Code Fixes
- [x] Fix hardcoded sleep values in camera_wrk.py (lines 335, 342)
  - [x] Add CAMERA_LOOP_DELAY to config.py
  - [x] Add CAMERA_RETRY_DELAY to config.py
- [x] Add shutdown lock to ProcessHandler (process_man.py)
  - [x] Prevent race condition in signal handler
  - [x] Add threading.Lock() for stop_workers()
- [x] Add camera enumeration timeout (currently can hang on dead cameras)
  - [x] Add timeout parameter to cv2.VideoCapture() calls

### Testing
- [x] Test installation on clean Python environment
- [x] Test on Windows (current platform)
- [x] Test with real hardware (IMU + camera)
- [ ] Test without hardware (mock data mode)
- [x] Verify all panels save/load preferences correctly
- [x] Test UDP output with OpenTrack

### Packaging
- [x] Create requirements.txt with Python 3.13 compatible versions:
  - [x] numpy>=1.26.0 (Python 3.13 support, 3.14 experimental)
  - [x] opencv-python>=4.8.0 (Python 3.13-3.14 wheels)
  - [x] pyserial>=3.5 (all versions)
  - [x] Pillow>=10.0.0 (Python 3.13-3.14 support)
- [x] Add Python version check (3.8-3.13 recommended, 3.14+ experimental)

---

## Important (Should Have for v0.1)

### Testing
- [ ] Add unit tests directory: tests/
- [ ] Write tests for ComplementaryFilter (fusion_wrk.py)
- [ ] Write tests for error_utils.py (safe_queue_put/get)
- [ ] Write tests for PreferencesManager
- [ ] Write tests for IMU data parsing (parse_imu_line)
- [ ] Set up pytest configuration

### Documentation
- [ ] Add docstrings to remaining functions
- [ ] Document configuration file format (config.cfg)
- [ ] Create example configuration files
- [ ] Add screenshots to README

### Code Quality
- [x] Add camera enumeration timeout (1s per camera)
- [x] Review all TODO comments in code
- [ ] Add type hints to critical functions
- [ ] Run linter (pylint/flake8) and fix issues

---

## Nice to Have (Can Wait for v0.2+)

### Features
- [ ] Add recording/playback mode for debugging
- [ ] Add calibration wizard for IMU
- [ ] Add sensitivity adjustment sliders
- [ ] Add data visualization graphs
- [ ] Add multiple profile support

### Testing
- [ ] Add integration tests
- [ ] Set up continuous integration (GitHub Actions)
- [ ] Add performance benchmarks
- [ ] Test on Linux (not yet)
- [ ] Test on macOS (not yet, maybe never)

### Documentation
- [ ] Create video tutorial/demo
- [ ] Write contributor guidelines (CONTRIBUTING.md)
- [x] Add FAQ section
- [ ] Create wiki with detailed guides
- [ ] Document supported hardware list

### Code Improvements
- [ ] Add logging levels (DEBUG, INFO, WARNING, ERROR)
- [ ] Add auto-reconnect for serial port
- [ ] Add camera hot-swap support
- [ ] Optimize camera preview performance
- [ ] Add error recovery mechanisms

---

## Next Steps (Prioritized)

1. **Phase 1 (Today/Tomorrow - 2-4 hours)**
   - [x] Create .gitignore
   - [x] Add MIT LICENSE file
   - [x] Write basic README.md (use template from review)
   - [x] Decide on GUI version (keep gui_wrk_v2.py, remove old?)
   - [x] Create requirements.txt

2. **Phase 2 (This Week - 2-3 hours)**
   - [x] Fix hardcoded values
   - [x] Add shutdown lock
   - [x] Add missing __init__.py files
   - [x] Test on clean environment

3. **Phase 3 (Next Week - 2-4 hours)**
   - [ ] Write ARCHITECTURE.md
   - [ ] Add 5-10 unit tests
   - [ ] Test with hardware
   - [ ] Add screenshots/demo

4. **Phase 4 (Before Release - 2-3 hours)**
   - [ ] Final testing
   - [ ] Review all documentation
   - [ ] Tag v0.1-alpha release
   - [ ] Publish to GitHub

**Estimated Time to v0.1 Release: 8-14 hours**

---

## Notes
- Keep test_panels.py as a development tool (not for end users)
- Consider renaming main.py → acceltrack.py for clarity
- Document that config.cfg is auto-generated (user preferences)
- **Python Requirements: 3.8-3.13 recommended (binary wheels available)**
- **Python 3.14+: Experimental (NumPy builds from source, may crash)**
- Dependencies tested with Python 3.8-3.13 (Nov 2025)