# Acceltrack - TODO List

## Critical (Before v0.1 Release)

### Documentation
- [ ] Write README.md
  - [ ] Project description and features
  - [ ] Hardware requirements (IMU model, Arduino, camera specs)
  - [ ] Installation instructions
  - [ ] Quick start guide
  - [ ] Serial data format specification
  - [ ] Configuration guide
  - [ ] Troubleshooting section
- [ ] Add LICENSE file (see recommendation below)
- [ ] Create .gitignore file
- [ ] Write ARCHITECTURE.md
  - [ ] System overview diagram
  - [ ] Process architecture (workers, queues)
  - [ ] Data flow diagram
  - [ ] Module responsibilities

### Cleanup
- [ ] Remove gui_wrk_v2.py OR rename/restructure (decide on one GUI version)
- [ ] Delete deprecated/test files if not needed for release
- [ ] Remove __pycache__ directories from git tracking
- [ ] Add missing __init__.py files:
  - [ ] workers/gui/__init__.py
  - [ ] workers/gui/managers/__init__.py

### Code Fixes
- [ ] Fix hardcoded sleep values in camera_wrk.py (lines 335, 342)
  - [ ] Add CAMERA_LOOP_DELAY to config.py
  - [ ] Add CAMERA_RETRY_DELAY to config.py
- [ ] Add shutdown lock to ProcessHandler (process_man.py)
  - [ ] Prevent race condition in signal handler
  - [ ] Add threading.Lock() for stop_workers()

### Testing
- [ ] Test installation on clean Python environment
- [ ] Test on Windows (current platform)
- [ ] Test with real hardware (IMU + camera)
- [ ] Test without hardware (mock data mode)
- [ ] Verify all panels save/load preferences correctly
- [ ] Test UDP output with OpenTrack

### Packaging
- [ ] Create requirements.txt with pinned versions:
  - [ ] numpy>=1.20.0
  - [ ] opencv-python>=4.5.0
  - [ ] pyserial>=3.5
  - [ ] Pillow>=8.0.0 (for camera preview)
- [ ] Optional: Create setup.py for pip installation

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
- [ ] Document expected IMU models/compatibility

### Code Quality
- [ ] Add camera enumeration timeout (1s per camera)
- [ ] Review all TODO comments in code
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
- [ ] Test on Linux
- [ ] Test on macOS

### Documentation
- [ ] Create video tutorial/demo
- [ ] Write contributor guidelines (CONTRIBUTING.md)
- [ ] Add FAQ section
- [ ] Create wiki with detailed guides
- [ ] Document supported hardware list

### Code Improvements
- [ ] Add logging levels (DEBUG, INFO, WARNING, ERROR)
- [ ] Add auto-reconnect for serial port
- [ ] Add camera hot-swap support
- [ ] Optimize camera preview performance
- [ ] Add error recovery mechanisms

---

## LICENSE RECOMMENDATION

### Recommended: **MIT License**

**Why MIT?**
- ✅ Most permissive open-source license
- ✅ Allows commercial use
- ✅ Simple and short (easy to understand)
- ✅ Compatible with almost all other licenses
- ✅ Popular for hardware + software projects
- ✅ No requirement to share modifications (but users can if they want)
- ✅ Good for projects that want maximum adoption

**Other Options:**

### Apache 2.0
- ✅ Similar to MIT but includes patent protection
- ✅ Better for projects with corporate contributors
- ✅ More explicit about contributions
- ⚠️ Slightly more complex license text

### GPL-3.0
- ✅ Strong copyleft (derivatives must be open source)
- ✅ Good if you want to prevent proprietary forks
- ⚠️ Less permissive (requires sharing modifications)
- ⚠️ Can limit commercial adoption

### BSD 3-Clause
- ✅ Similar to MIT, very permissive
- ✅ Includes non-endorsement clause
- ✅ Good for academic projects

**My Strong Recommendation: MIT License**
- Perfect for a head tracking project
- Allows integration with OpenTrack (already uses permissive licenses)
- Maximum community adoption potential
- Simple and clear for contributors

---

## Next Steps (Prioritized)

1. **Phase 1 (Today/Tomorrow - 2-4 hours)**
   - [ ] Create .gitignore
   - [ ] Add MIT LICENSE file
   - [ ] Write basic README.md (use template from review)
   - [ ] Decide on GUI version (keep gui_wrk_v2.py, remove old?)
   - [ ] Create requirements.txt

2. **Phase 2 (This Week - 2-3 hours)**
   - [ ] Fix hardcoded values
   - [ ] Add shutdown lock
   - [ ] Add missing __init__.py files
   - [ ] Test on clean environment

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
- Mention Python 3.8+ requirement in README
