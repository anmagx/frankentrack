# Frankentrack Infrastructure Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Worker Processes](#worker-processes)
4. [Communication Layer](#communication-layer)
5. [Configuration System](#configuration-system)
6. [Data Flow](#data-flow)
7. [Error Handling & Monitoring](#error-handling--monitoring)
8. [Hardware Integration](#hardware-integration)
9. [GUI Architecture](#gui-architecture)
10. [Deployment & Execution](#deployment--execution)

---

## System Overview

Frankentrack is a sophisticated multiprocess Python application for 3DOF (Yaw/Pitch/Roll) headtracking using IMU sensor fusion. The system is designed for real-time performance, robustness, and extensibility.

**Key Characteristics:**
- **Language**: Python 3.8 - 3.13 (Windows only)
- **Architecture**: Multiprocess with IPC via queues
- **GUI Framework**: PyQt5 (tabbed interface with light/dark themes)
- **Target Performance**: 120Hz sensor fusion and UDP output
- **Real-time Constraints**: Sub-millisecond queue timeouts, minimal sleep intervals

**Version**: 0.13-alpha

---

## Architecture

### Design Philosophy

Frankentrack uses a **process-based parallelism** approach rather than threading to:
- Achieve true concurrent execution on multi-core CPUs
- Isolate worker failures (crashed workers don't affect others)
- Avoid Python's Global Interpreter Lock (GIL) limitations
- Enable independent restart of failed components

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Main Process                                │
│                   (frankentrack.py)                              │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            ProcessHandler                                 │  │
│  │  - Creates all queues                                     │  │
│  │  - Starts worker processes                                │  │
│  │  - Manages shutdown                                       │  │
│  │  - Runs log writer thread                                 │  │
│  │  - Monitors worker health                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│ Serial       │      │ Fusion       │     │ UDP          │
│ Worker       │─────▶│ Worker       │────▶│ Worker       │
│ Process      │      │ Process      │     │ Process      │
└──────────────┘      └──────────────┘     └──────────────┘
        │                     │                     │
        ▼                     ▼                     │
┌──────────────┐      ┌──────────────┐             │
│ Input        │      │ GUI          │◀────────────┘
│ Worker       │      │ Worker       │
│ Process      │      │ Process      │
└──────────────┘      └──────────────┘
```

### Process Communication

All inter-process communication uses `multiprocessing.Queue` objects with bounded capacity:

| Queue Type | Size | Purpose |
|------------|------|---------|
| Data Pipelines | 300 | High-throughput sensor data (2.5s @ 120Hz) |
| Display Queues | 60 | GUI updates (500ms buffer) |
| Control Queues | 10 | Command messages |

---

## Worker Processes

### 1. Serial Worker (`serial_wrk.py`)

**Responsibility**: Read IMU sensor data from Arduino/microcontroller via serial port.

**Key Features:**
- Automatic reconnection with configurable retry delay
- Dynamic port/baud configuration via control queue
- Non-blocking queue puts to avoid blocking reads
- FPS (frames per second) reporting

**Control Commands:**
- `('start', port, baud)` - Open serial connection
- `('stop',)` - Close serial connection

**Output Queues:**
- `serialQueue` - Raw CSV sensor data for fusion
- `serialDisplayQueue` - Data for GUI display
- `statusQueue` - Connection status updates

**Data Format (CSV):**
```
time(seconds), accelX, accelY, accelZ, gyroX, gyroY, gyroZ
```

**Configuration:**
```python
DEFAULT_SERIAL_PORT = 'COM3'
DEFAULT_SERIAL_BAUD = 115200
SERIAL_RETRY_DELAY = 2.0  # seconds
SERIAL_TIMEOUT = 1.0  # seconds
```

---

### 2. Fusion Worker (`fusion_wrk.py`)

**Responsibility**: Sensor fusion to compute orientation angles from IMU data.

**Key Features:**
- Two complementary filter implementations:
  - Classic Euler-based filter (default)
  - Quaternion-based filter (smoother, gimbal-lock free)
- Gyro bias calibration (400 samples at startup)
- Level calibration for pitch/roll zeroing
- Stationary detection for drift correction
- Gradual drift correction with configurable curves (cosine, linear, quadratic)

**Filter Algorithm:**
The complementary filter combines:
- **Accelerometer** → Gravity-based pitch/roll (slow, stable)
- **Gyroscope** → Fast angular velocity integration (fast, drifts)

Formula (simplified):
```
angle = α × (angle + gyro × dt) + (1 - α) × accel_angle
```

Where:
- `α = 0.98` (ALPHA_PITCH, ALPHA_ROLL, ALPHA_YAW)
- Higher α = more gyro influence, faster response
- Lower α = more accel influence, more stable but sluggish

**Drift Correction:**
1. **Gyro Bias Calibration**: Collects samples while stationary to estimate drift rate
2. **Center Threshold**: When within threshold angles, gradually pulls view to center

**Control Commands:**
- `('calibrate_gyro_bias',)` - Start gyro bias calibration
- `('calibrate_level',)` - Calibrate pitch/roll to current level
- `('reset_center',)` - Instant center reset
- `('set_filter_type', 'euler'|'quaternion')` - Switch filter algorithm
- `('set_alpha', 'pitch'|'roll'|'yaw', value)` - Adjust filter responsiveness
- `('set_threshold', angle_yaw, angle_pitch, angle_roll)` - Set drift correction thresholds

**Output Queues:**
- `eulerQueue` - Orientation angles [yaw, pitch, roll, 0, 0, 0]
- `eulerDisplayQueue` - Copy for GUI visualization
- `statusQueue` - Calibration and drift status updates

**Configuration:**
```python
ALPHA_YAW = 0.98
ALPHA_PITCH = 0.98
ALPHA_ROLL = 0.98
GYRO_BIAS_CAL_SAMPLES = 400
LEVEL_CAL_SAMPLES = 20
DEFAULT_CENTER_THRESHOLD = 5.0  # degrees
DRIFT_SMOOTHING_TIME = 2.0  # seconds
```

---

### 3. UDP Worker (`udp_wrk.py`)

**Responsibility**: Send orientation data to OpenTrack via UDP.

**Key Features:**
- OpenTrack-compatible packet format (6 doubles: TX, TY, TZ, RX, RY, RZ)
- Rate-limited sending (configurable 10-250 Hz)
- Optional translation data support (for camera tracking)
- Stale data detection (2 second timeout)

**Control Commands:**
- `('set_udp', ip, port)` - Update UDP target
- `('udp_enable', True|False)` - Toggle sending

**Input Queues:**
- `eulerQueue` - Orientation angles [yaw, pitch, roll, ...]
- `translationQueue` - Optional position data [x, y, z]

**Output:**
- UDP packets to OpenTrack (struct format: `<6d` little-endian doubles)

**Packet Structure:**
```python
struct.pack('<6d', tx, ty, tz, yaw, pitch, roll)
# 48 bytes total (6 × 8-byte doubles)
```

**Configuration:**
```python
DEFAULT_UDP_IP = '127.0.0.1'
DEFAULT_UDP_PORT = 4243
DEFAULT_OUTPUT_RATE_HZ = 120
OUTPUT_RATE_MIN_HZ = 10
OUTPUT_RATE_MAX_HZ = 250
```

---

### 4. GUI Worker (`gui_wrk.py`)

**Responsibility**: PyQt5-based graphical user interface with tabbed layout.

**Key Features:**
- Multi-tab interface (Orientation, Diagnostics, Messages, Preferences, About)
- Real-time orientation visualization (pitch/roll/yaw indicators)
- Live serial data display with scrollback
- Calibration controls with progress feedback
- Theme support (light/dark with QSS stylesheets)
- Preferences persistence (config.cfg)
- Status bar with connection indicators

**Tabs:**
1. **Orientation Tracking** - Serial config, message log, calibration controls, live angles, network settings
2. **Diagnostics** - Queue health monitoring, performance metrics, system info
3. **Messages** - Collapsible message log panel
4. **Preferences** - Theme selection, advanced settings
5. **About** - Version info, credits

**Update Timers:**
- GUI refresh: 16ms (~60 FPS)
- Queue polling: 25ms (40Hz checks)

**Panels:**
- `SerialPanelQt` - Serial port configuration and connection
- `CalibrationPanelQt` - Gyro bias, level calibration, drift settings
- `OrientationPanelQt` - Live angle display and visualization
- `NetworkPanelQt` - UDP configuration and output rate
- `DiagnosticsPanelQt` - Queue health, worker monitoring
- `StatusBarQt` - Connection status indicators
- `HoldPanelQt` - Visual calibration reminder overlay

**Configuration:**
```python
GUI_UPDATE_INTERVAL_MS = 16  # ~60 FPS
WORKER_QUEUE_CHECK_INTERVAL_MS = 25  # 40Hz
MAX_TEXT_BUFFER_LINES = 500  # Display scrollback
```

---

### 5. Input Worker (`input_wrk.py`)

**Responsibility**: Handle keyboard and gamepad input for shortcuts (e.g., recenter).

**Key Features:**
- Pygame-based gamepad/joystick support
- Multi-device support (joysticks, gamepads)
- Shortcut capture mode for configuration
- Background monitoring thread for hotkey detection

**Control Commands:**
- `('start_monitoring', shortcut_config)` - Begin monitoring for shortcut
- `('stop_monitoring',)` - Stop monitoring
- `('capture_input',)` - Enter capture mode for shortcut configuration

**Input Format:**
```python
# Keyboard: 'key_space', 'key_enter'
# Gamepad: 'joy0_button10', 'joy1_axis3'
```

**Dependencies:**
- `pygame` (optional, gracefully degrades if not available)
- Manages pygame initialization/cleanup lifecycle

---

## Communication Layer

### Queue Architecture

#### Data Flow Queues
These queues carry high-frequency sensor data:

```python
serialQueue (300)      # Serial → Fusion
  ↓
eulerQueue (300)       # Fusion → UDP
  ↓
UDP Sender
```

#### Display Queues
Separate queues for GUI to avoid blocking data pipeline:

```python
serialDisplayQueue (60)  # Serial → GUI
eulerDisplayQueue (60)   # Fusion → GUI
messageQueue (60)        # All → GUI
```

#### Control Queues
Bidirectional command/response:

```python
serialControlQueue (10)  # GUI → Serial
fusionControlQueue (10)  # GUI → Fusion
udpControlQueue (10)     # GUI → UDP
statusQueue (10)         # Workers → GUI
uiStatusQueue (10)       # Workers → GUI (UI-specific)
inputCommandQueue (10)   # GUI → Input Worker
inputResponseQueue (10)  # Input Worker → GUI
```

### Queue Safety Utilities

**`safe_queue_put()`** - Non-blocking with timeout fallback:
```python
def safe_queue_put(queue, item, timeout=0.1, context="", 
                   log_failures=False, queue_name=None) -> bool:
    # Try non-blocking first
    queue.put_nowait(item)
    # Falls back to blocking with timeout
    # Returns True if successful, False if full
```

**`safe_queue_get()`** - Non-blocking with default return:
```python
def safe_queue_get(queue, timeout=0.0, default=None):
    # Returns item or default if empty/timeout
```

### Queue Health Monitoring

The ProcessHandler runs background monitoring:

```python
# Three-tier health status
Healthy:   < 70% full
Warning:   70-90% full  
Critical:  > 90% full

# Automatic logging every 10 seconds
if fill_ratio > QUEUE_WARNING_THRESHOLD:
    log_warning(f"Queue '{name}' is {fill_ratio:.1%} full")
```

---

## Configuration System

### Two-Tier Configuration

#### 1. System Configuration (`config/config.py`)
**Read-only constants** for system defaults:

```python
# Application metadata
APP_NAME = "frankentrack"
APP_VERSION = "0.13-alpha"

# Performance tuning
GUI_UPDATE_INTERVAL_MS = 16
WORKER_QUEUE_CHECK_INTERVAL_MS = 25
QUEUE_SIZE_DATA = 300
QUEUE_SIZE_DISPLAY = 60

# Sensor fusion
ALPHA_YAW = 0.98
ALPHA_PITCH = 0.98
ALPHA_ROLL = 0.98
GYRO_BIAS_CAL_SAMPLES = 400

# Network
DEFAULT_UDP_IP = '127.0.0.1'
DEFAULT_UDP_PORT = 4243
DEFAULT_OUTPUT_RATE_HZ = 120
```

#### 2. User Preferences (`config/config.cfg`)
**INI-format file** for persistent user settings:

```ini
[serial]
com_port = COM8
baud_rate = 500000

[network]
udp_ip = 127.0.0.1
udp_port = 4243

[calibration]
drift_angle_yaw = 3.0
drift_angle_pitch = 3.0
drift_angle_roll = 5.0
reset_shortcut = joy0_button10
alpha_pitch = 0.975
gyro_bias_cal_samples = 2000

[gui]
theme = dark
selected_tab = 0

[diagnostics]
enabled = False
max_data_points = 1000
```

**Management:**
- `PreferencesManager` class handles load/save operations
- Atomic writes prevent corruption during save
- Auto-migration of missing keys with defaults

---

## Data Flow

### Complete Data Pipeline

```
┌─────────────┐
│  Arduino    │ IMU Sensor (MPU6500)
│  Nano       │ 250Hz @ 500000 baud
└──────┬──────┘
       │ USB Serial
       │ CSV: time,ax,ay,az,gx,gy,gz
       ▼
┌─────────────┐
│   Serial    │ Parse CSV
│   Worker    │ Queue monitoring
└──────┬──────┘
       │ serialQueue (raw data)
       │ serialDisplayQueue (GUI display)
       ▼
┌─────────────┐
│   Fusion    │ Complementary Filter
│   Worker    │ - Gyro integration
│             │ - Accel correction
│             │ - Drift compensation
└──────┬──────┘
       │ eulerQueue [yaw, pitch, roll, 0, 0, 0]
       │ eulerDisplayQueue (GUI display)
       ▼
┌─────────────┐
│     UDP     │ Pack to OpenTrack format
│   Worker    │ struct.pack('<6d', ...)
└──────┬──────┘
       │ UDP Socket
       ▼
┌─────────────┐
│  OpenTrack  │ 127.0.0.1:4243
│  (Games)    │
└─────────────┘
```

### Timing Analysis

**Latency Budget (120Hz = 8.33ms per cycle):**

| Stage | Time | Notes |
|-------|------|-------|
| Arduino sampling | 4ms | 250Hz sensor rate |
| Serial transmission | <1ms | 500000 baud |
| Serial queue | <0.1ms | Non-blocking put |
| Fusion calculation | 1-2ms | Complementary filter |
| Euler queue | <0.1ms | Non-blocking put |
| UDP transmission | <0.5ms | Local loopback |
| **Total** | **~6-8ms** | Well within budget |

---

## Error Handling & Monitoring

### Robustness Features

#### 1. Worker Process Monitoring
```python
class ProcessHandler:
    def _worker_monitor(self):
        # Check worker health every second
        for worker in self.workers:
            if not worker.is_alive():
                # Automatic restart (up to 3 attempts)
                restart_worker(worker)
```

**Restart Policy:**
- Maximum 3 restart attempts per worker
- 1 second delay between restarts
- Configuration preserved across restarts

#### 2. Queue Overflow Protection
```python
# Non-blocking puts with immediate fallback
if not safe_queue_put(queue, data, timeout=QUEUE_PUT_TIMEOUT):
    # Log drop and continue - don't block pipeline
    log_error(f"Dropped frame, queue full")
```

**Drop Tracking:**
- Count drops per queue
- Log every 50 drops
- Include in diagnostics panel

#### 3. Serial Connection Recovery
```python
def open_serial(port, baud, retry_delay, ...):
    # Infinite retry loop with cancellation support
    while True:
        if stop_event.is_set():
            return None  # Graceful cancel
        try:
            ser = serial.Serial(port, baud)
            return ser
        except SerialException:
            time.sleep(retry_delay)
```

#### 4. Logging System
Centralized log writer thread in ProcessHandler:

```python
# All workers send to logQueue
logQueue.put(('INFO', 'SerialWorker', 'Connected'))

# Main process writes to file
frankentrack.log  # Timestamped entries
```

**Log Format:**
```
[2024-12-20 14:32:15] [INFO ] [Serial Worker  ] Connected to COM8 at 500000 baud
[2024-12-20 14:32:16] [WARN ] [Fusion Worker  ] Queue 'eulerQueue' is 75% full
[2024-12-20 14:32:20] [ERROR] [UDP Worker     ] Send failed: Connection refused
```

**Log Rotation:**
- Max size: 5 MB
- Automatic backup with timestamp on rollover

---

## Hardware Integration

### Arduino/Microcontroller

**Supported IMUs** (via FastIMU library):
- MPU6050, MPU6500, MPU9250, MPU9255
- ICM20689, ICM20690
- BMI055, BMX055, BMI160
- LSM6DS3, LSM6DSL
- QMI8658

**Example Hardware (in video demo):**
- Arduino Nano
- MPU6500 IMU
- Single 940nm IR-LED (optional, for position tracking)
- PS3 Eye camera (optional)

**Required Arduino Code:**
```cpp
// Calibrated_sensor_output_timestamped.ino
#include "FastIMU.h"

MPU6500 IMU;

void loop() {
  // 250Hz update rate (4ms intervals)
  IMU.update();
  IMU.getAccel(&accelData);
  IMU.getGyro(&gyroData);
  
  // Output CSV format
  Serial.println("time,ax,ay,az,gx,gy,gz");
}
```

**Communication:**
- **Baud Rate**: 115200 - 500000 (configurable)
- **Update Rate**: 120-250 Hz recommended
- **Protocol**: Simple CSV over serial

### Camera Tracking (Optional)

**Camera Worker** (`camera_wrk.py`):
- Processes camera frames for position tracking
- Detects bright IR-LED marker via blob detection
- Outputs X/Y/Z translation data (Z currently fixed at 0.0)
- Sends preview JPEG frames to GUI on request

**PSEye Camera Provider** (`pseyepy_prov.py`):
- Subprocess-based pseyepy wrapper for crash isolation
- Runs camera capture in separate process
- Streams JPEG-encoded frames via stdout
- Configurable resolution and FPS
- Clean interface: `read()`, `set_params()`, `set_setting()`, `close()`

**Frame Pipeline:**
```
┌──────────────────┐
│  PS3 Eye Camera  │ 
│  (pseyepy)       │
└────────┬─────────┘
         │ Subprocess
         ▼
┌──────────────────┐
│  PSEyeProvider   │ JPEG encoding
│  (subprocess)    │ Frame streaming
└────────┬─────────┘
         │ Binary protocol:
         │ [size][timestamp][jpeg_data]
         ▼
┌──────────────────┐
│  Camera Worker   │ Blob detection
│  (camera_wrk.py) │ Position calc
└────────┬─────────┘
         │
         ├──→ translationQueue → Fusion/UDP
         │
         └──→ cameraPreviewQueue → GUI
```

**Key Features:**
- **Crash Isolation**: Native pseyepy code runs in subprocess
- **Efficient Streaming**: JPEG compression reduces IPC overhead
- **Dynamic Configuration**: Resolution/FPS/exposure adjustable at runtime
- **Graceful Shutdown**: Proper camera release on exit
- **Stale Detection**: 2s timeout before declaring marker lost

**Supported Hardware:**
- PS3 Eye camera (recommended, 60-120 FPS capable)
- Single 940nm IR-LED marker for position tracking
- OpenCV-based blob detection with configurable threshold

---

## GUI Architecture

### PyQt5 Component Hierarchy

```
TabbedGUIWorker (QMainWindow)
│
├─ HoldPanelQt (top overlay)
│
├─ QTabWidget
│  ├─ Orientation Tab
│  │  ├─ SerialPanelQt
│  │  ├─ MessagePanelQt (collapsible)
│  │  ├─ CalibrationPanelQt
│  │  ├─ OrientationPanelQt
│  │  └─ NetworkPanelQt
│  │
│  ├─ Diagnostics Tab
│  │  └─ DiagnosticsPanelQt
│  │
│  ├─ Messages Tab
│  │  └─ MessagePanelQt (expanded)
│  │
│  ├─ Preferences Tab
│  │  └─ PreferencesPanel
│  │
│  └─ About Tab
│     └─ AboutPanel
│
└─ StatusBarQt (bottom)
```

### Key GUI Components

#### 1. OrientationPanelQt
Real-time angle visualization:
- Circular pitch/roll indicator with crosshair
- Yaw arc with pointer
- Configurable range (±15° default)
- Color-coded drift correction zones

#### 2. CalibrationPanelQt
Calibration controls:
- Gyro bias calibration (progress bar)
- Level calibration (pitch/roll zero)
- Drift threshold sliders (separate for yaw/pitch/roll)
- Alpha filter adjustment (responsiveness)
- Stationary detection tuning

#### 3. DiagnosticsPanelQt
System monitoring:
- Queue health table (name, size, fill %, status)
- Worker status indicators
- Performance metrics (FPS, send rate)
- Queue health refresh (auto/manual)

#### 4. StatusBarQt
Connection indicators:
- Serial: 🟢 Connected / 🔴 Disconnected / 🟡 Error
- UDP: 🟢 Sending / ⚪ Idle
- Calibration: 🟡 In Progress / 🟢 Complete

### Theme System

**ThemeManager** (`workers/gui_qt/managers/theme_manager.py`):
- Loads QSS stylesheets from `themes/` directory
- Supports `light.qss` and `dark.qss`
- Hot-reload capability (apply without restart)

**Example Theme (dark.qss):**
```css
QMainWindow {
    background-color: #2b2b2b;
    color: #ffffff;
}

QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    padding: 5px;
    border-radius: 3px;
}
```

### Preferences Persistence

**PreferencesManager** handles atomic saves:

```python
# Read
prefs = preferences_manager.load_preferences()
com_port = prefs['serial']['com_port']

# Write (atomic)
preferences_manager.save_preference('serial', 'com_port', 'COM8')
```

**Atomic Write Strategy:**
1. Write to temporary file (`.cfg.tmp`)
2. Flush to disk
3. Rename to final filename (atomic operation)

---

## Deployment & Execution

### Installation

**Automated Setup (`install.bat`):**
```batch
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
# Creates desktop shortcut (launch_frankentrack.bat)
```

**Manual Setup:**
```bash
git clone https://github.com/anmagx/frankentrack
cd frankentrack
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Dependencies

**requirements.txt:**
```
numpy>=1.26.0
opencv-python>=4.8.0
pyserial>=3.5
Pillow>=10.0.0
keyboard>=0.13.5
h5py
PyQt5>=5.15.0,<6.0.0
```

**Python Version Support:**
- ✅ 3.8 - 3.13 (binary wheels available)
- ⚠️ 3.14+ (experimental, NumPy may be unstable)

### Launch

**Using Launcher (`launch_frankentrack.bat`):**
```batch
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python frankentrack.py
pause
```

**Direct Execution:**
```bash
python frankentrack.py
```

### Execution Flow

```python
# frankentrack.py
def main():
    # 1. Create process handler
    handler = ProcessHandler()
    
    # 2. Start all workers
    handler.start_workers()
    
    # 3. Main loop (waits for stop_event)
    while not handler.stop_event.wait(timeout=0.5):
        pass
    
    # 4. Cleanup
    handler.stop_workers()
```

**Startup Sequence:**
1. ProcessHandler creates all queues
2. Workers spawn as separate processes
3. Log writer thread starts
4. Worker monitoring thread starts
5. GUI window appears
6. User initiates serial connection
7. Fusion worker calibrates (gyro bias)
8. UDP sender enabled when ready

**Shutdown Sequence:**
1. User closes GUI or Ctrl+C
2. `stop_event.set()` signals all workers
3. Workers drain queues and exit gracefully
4. Main waits for worker joins (2s timeout each)
5. Log writer flushes and closes file
6. Process exits

---

## Performance Considerations

### Optimization Techniques

1. **Non-blocking Queue Operations**
   - Use `put_nowait()` with `Full` exception handling
   - Prefer dropping frames over blocking the pipeline

2. **Queue Draining**
   - UDP worker drains euler queue to get latest frame
   - Prevents backlog from slowing down processing

3. **Minimal Sleep Intervals**
   - Fusion loop: 1ms sleep (`FUSION_LOOP_SLEEP_MS`)
   - Serial: ~0 sleep (event-driven by `in_waiting`)

4. **Separate Display Queues**
   - GUI display doesn't compete with data pipeline
   - GUI drop != data loss

5. **Process Isolation**
   - Each worker uses separate CPU core
   - GIL doesn't affect multi-process parallelism

### Bottleneck Analysis

**Potential Bottlenecks:**
1. **Serial Read** - Limited by baud rate and Arduino speed
   - Solution: 500000 baud, 250Hz Arduino sampling
   
2. **Queue Overflow** - Too much data, too slow consumer
   - Solution: Queue health monitoring, adaptive dropping
   
3. **GUI Updates** - Qt event loop can't keep up
   - Solution: Separate display queues, 60 FPS cap

4. **Fusion Calculation** - Complex math per frame
   - Solution: NumPy vectorization, minimal sleep

**Profiling Hooks:**
- FPS reporting in serial/fusion workers
- Queue fill ratios in diagnostics
- Send rate tracking in UDP worker

---

## Troubleshooting

### Common Issues

**1. No Serial Data**
- Check COM port in Device Manager
- Verify baud rate matches Arduino (115200 or 500000)
- Ensure Arduino sketch is uploaded and running
- Check USB cable (some are power-only)

**2. High Queue Fill Ratios**
- Reduce Arduino output rate
- Increase queue sizes in `config/config.py`
- Check if fusion worker is running (should show in diagnostics)

**3. Drift Not Correcting**
- Ensure gyro bias calibration was performed (device stationary)
- Check drift threshold angles (too large = no correction)
- Verify device is within threshold zone (GUI visualization)

**4. GUI Not Responding**
- Check if GUI worker is alive (process monitor)
- Restart application (automatic worker restart may help)
- Check log file for errors (`frankentrack.log`)

**5. UDP Not Sending**
- Ensure UDP is enabled (checkbox in Network panel)
- Verify IP:Port matches OpenTrack configuration
- Check firewall (Windows may block local UDP)

### Diagnostic Tools

**1. Diagnostics Tab**
- Real-time queue health
- Worker status
- Performance metrics

**2. Log File (`frankentrack.log`)**
- Timestamped entries from all workers
- Error traces with full stack
- Connection events

**3. Status Bar**
- Quick glance at connection status
- Color-coded indicators

---

## Future Enhancements

### Planned Features
1. **Camera-based Position Tracking** (X/Y/Z)
2. **Multiple Fusion Algorithms** (Madgwick, Mahony)
3. **9DOF Support** (magnetometer for true yaw reference)
4. **Recording/Playback** (capture sessions for analysis)
5. **Multi-platform Support** (Linux, macOS)
6. **Bluetooth LE** (wireless IMU connection)

### Architecture Improvements
1. **Plugin System** (hot-loadable workers)
2. **REST API** (external control)
3. **WebSocket GUI** (browser-based interface)
4. **Configuration Profiles** (quick switching)

---

## Contributing

### Code Style
- Follow PEP 8 conventions
- Use type hints where possible
- Document complex algorithms
- Add logging for significant events

### Testing
- Test with multiple IMU types
- Verify queue health under load
- Check GUI responsiveness at various rates
- Validate calibration accuracy

### Pull Request Guidelines
1. Create feature branch from `main`
2. Include descriptive commit messages
3. Update documentation (this file!)
4. Test on Windows (primary target)
5. Submit PR with detailed description

---

## License

MIT License - See [LICENSE](LICENSE) file for details.

---

## Credits

**Author**: anmagx  
**AI Assistant**: Claude (Anthropic) - Heavy usage in development  
**IMU Library**: FastIMU (Arduino)  
**GUI Framework**: PyQt5  
**Sensor Fusion**: Custom complementary filter implementation  

---

## Appendix

### A. Configuration Reference

See [config/config.py](config/config.py) for complete list of constants.

### B. Queue Reference

| Queue Name | Size | Type | Producer | Consumer |
|------------|------|------|----------|----------|
| serialQueue | 300 | Data | Serial | Fusion |
| eulerQueue | 300 | Data | Fusion | UDP |
| serialDisplayQueue | 60 | Display | Serial | GUI |
| eulerDisplayQueue | 60 | Display | Fusion | GUI |
| messageQueue | 60 | Display | All | GUI |
| serialControlQueue | 10 | Control | GUI | Serial |
| fusionControlQueue | 10 | Control | GUI | Fusion |
| udpControlQueue | 10 | Control | GUI | UDP |
| statusQueue | 10 | Status | All | GUI |
| uiStatusQueue | 10 | Status | All | GUI |
| logQueue | 60 | Log | All | Main |
| inputCommandQueue | 10 | Control | GUI | Input |
| inputResponseQueue | 10 | Response | Input | GUI |

### C. Shortcut Format

**Keyboard:**
- Format: `key_<name>`
- Example: `key_space`, `key_r`, `key_f5`

**Gamepad:**
- Button: `joy<N>_button<M>`
- Axis: `joy<N>_axis<M>`
- Example: `joy0_button10`, `joy1_axis3`

**Configuration:**
```ini
[calibration]
reset_shortcut = joy0_button10
reset_shortcut_display_name = X56 H.O.T.A.S. Throttle Button 10
```

---

**Document Version**: 1.0  
**Last Updated**: December 20, 2024  
**Application Version**: 0.13-alpha
