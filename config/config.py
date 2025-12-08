"""
System-wide configuration constants for frankentrack.

These are DEFAULT values used for initialization. Many can be overridden
at runtime via GUI controls and saved to config.cfg as user preferences.

Do NOT store runtime state here - this module only defines initial defaults.
"""

# ============================================================================
# Application Information
# ============================================================================
APP_NAME = "frankentrack"
APP_VERSION = "0.13-alpha"

# ============================================================================
# GUI Timing and Updates  
# ============================================================================
GUI_UPDATE_INTERVAL_MS = 16          # How often GUI updates displays (milliseconds) - ~60 FPS for real-time
WORKER_QUEUE_CHECK_INTERVAL_MS = 50   # How often GUI checks queues (milliseconds) - balanced for responsiveness

# Worker timing constants
CAMERA_FRAME_SLEEP_MS = 33  # ~30 FPS camera capture (was hardcoded 0.01)
FUSION_LOOP_SLEEP_MS = 1    # Minimal sleep in fusion loop (was hardcoded)
FUSION_DT_MAX_THRESHOLD = 0.1  # Max delta time before reset (was hardcoded)

# ============================================================================
# GUI Backend (PyQt5 only)
# ============================================================================
# Application uses PyQt5 for all GUI functionality

# ============================================================================
# Serial Communication
# ============================================================================
DEFAULT_SERIAL_PORT = 'COM3'
DEFAULT_SERIAL_BAUD = 115200
SERIAL_RETRY_DELAY = 2.0  # seconds between connection attempts
SERIAL_TIMEOUT = 1.0  # seconds

# ============================================================================
# Queue Configuration  
# ============================================================================
QUEUE_SIZE_DATA = 300  # For data pipelines (serial, euler, translation) - 2.5s buffer at 120Hz
QUEUE_SIZE_DISPLAY = 60  # For display-only queues - 500ms buffer for smooth updates
QUEUE_SIZE_CONTROL = 10  # For control command queues
QUEUE_SIZE_PREVIEW = 12  # For camera preview (larger buffer to reduce dropped frames)

# Queue monitoring thresholds
QUEUE_HIGH_WATERMARK = 0.8  # Trigger adaptive sampling when queue is 80% full
QUEUE_CRITICAL_WATERMARK = 0.9  # Critical queue level
QUEUE_MONITOR_INTERVAL_S = 5.0  # How often to check queue health
QUEUE_WARNING_THRESHOLD = 0.7   # Log warning when queue >70% full
QUEUE_DROP_COUNT_THRESHOLD = 10  # Log warning after this many drops

# ============================================================================
# Timeout Values
# ============================================================================
QUEUE_PUT_TIMEOUT = 0.001  # seconds - very fast timeout for real-time performance
QUEUE_GET_TIMEOUT = 0.5  # seconds
WORKER_JOIN_TIMEOUT = 2.0  # seconds to wait for worker shutdown
STALE_DETECTION_TIMEOUT = 2.0  # seconds before considering detection stale

# Error recovery timeouts
WORKER_RESTART_DELAY = 1.0  # seconds to wait before restarting failed worker
MAX_WORKER_RESTART_ATTEMPTS = 3  # maximum restart attempts per worker

# ============================================================================
# Fusion / Complementary Filter
# ============================================================================
ACCEL_THRESHOLD = 0.15  # g-units: threshold for stationary detection
DEFAULT_CENTER_THRESHOLD = 5.0  # degrees: threshold for "near center" detection
ALPHA_YAW = 0.98   # Complementary filter alpha for yaw (higher = more gyro dominance)
ALPHA_ROLL = 0.98  # Complementary filter alpha for roll (higher = smoother accel correction)
ALPHA_PITCH = 0.98 # Complementary filter alpha for pitch (higher = smoother accel correction)
ALPHA_DRIFT_CORRECTION = 0.99  # Alpha for drift correction when stationary

# Time delta validation
DT_MIN = 0.001  # seconds: reject dt smaller than this (likely duplicate)
DT_MAX = 0.1  # seconds: reject dt larger than this (likely gap/reset)

# Stationarity detection
# Gyro magnitude threshold (deg/s) below which we consider the device "quiet"
STATIONARY_GYRO_THRESHOLD = 5.0
# Debounce time (seconds) the stationary condition must persist before
# declaring the device stationary (prevents jitter/false positives)
STATIONARY_DEBOUNCE_S = 0.15

# ============================================================================
# Gyro bias calibration
# ============================================================================
# Number of gyro gz samples to collect at startup for initial bias calibration.
# Set to 0 to disable startup calibration and rely solely on online estimator.
GYRO_BIAS_CAL_SAMPLES = 400

# ============================================================================
# Camera / Computer Vision
# ============================================================================
DEFAULT_CAMERA_INDEX = 0
DEFAULT_CAMERA_FPS = 30
DEFAULT_CAMERA_WIDTH = 640
DEFAULT_CAMERA_HEIGHT = 480
CAMERA_LOOP_DELAY = 0.02  # seconds between frame captures
CAPTURE_RETRY_DELAY = 0.05  # seconds between camera open attempts
# How long to wait for `cv2.VideoCapture` to report open before giving up.
# This is polled with `cap.isOpened()`; the constructor itself may still
# block in some backends, but this prevents long waits after construction.
CAMERA_OPEN_TIMEOUT = 2.0  # seconds to wait for camera to open

# Detection thresholds
DEFAULT_DETECTION_THRESHOLD = 220  # 0-255 brightness threshold
MIN_BLOB_AREA = 6  # pixels: minimum contour area to consider

# Preview settings
PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240
JPEG_QUALITY = 60  # 0-100

# Position smoothing
LOWPASS_ALPHA = 0.18  # smoothing factor for position tracking

# Position output clamping
POSITION_CLAMP_MIN = -30.0  # cm or arbitrary units
POSITION_CLAMP_MAX = 30.0

# ============================================================================
# Network / UDP
# ============================================================================
DEFAULT_UDP_IP = '127.0.0.1'
DEFAULT_UDP_PORT = 4243

# ============================================================================
# GUI / Display
# ============================================================================
GUI_POLL_INTERVAL_MS = 100  # milliseconds
MAX_TEXT_BUFFER_LINES = 500  # lines to keep in message/serial displays
FPS_REPORT_INTERVAL = 1.0  # seconds between FPS updates
THRESH_DEBOUNCE_MS = 150  # milliseconds to debounce threshold slider

# Orientation visualization
VISUALIZATION_RANGE = 15.0  # degrees: +/- range for pitch/yaw axes
VISUALIZATION_SIZE = 160  # pixels: width and height of visualization widget

# Theme settings
DEFAULT_THEME = 'light'  # 'light', 'dark'
THEMES_ENABLED = True

# ============================================================================
# Logging
# ============================================================================
LOG_FILE_NAME = 'frankentrack.log'
LOG_FILE_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
LOG_QUEUE_TIMEOUT = 0.5  # seconds

# ============================================================================
# Preferences File
# ============================================================================
PREFS_FILE_NAME = 'config.cfg'
