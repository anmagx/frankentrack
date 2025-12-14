# FrankenTrack Shortcut System - Bug Fix Documentation

## Problem Summary
After refactoring keyboard capture from `calibration_panel.py` to `input_wrk.py`, the keyboard shortcut behavior became inconsistent. The shortcut should trigger the "Reset Orientation" command globally (even when the window is not in focus).

## Root Causes Identified

### 1. Key Name Format Mismatch
**Problem**: The keyboard library expects different key names than what Qt's `QKeySequence` provides.

**Examples**:
- Qt provides: `"Space"`, `"Return"`, `"F1"`
- Keyboard library expects: `"space"`, `"enter"`, `"f1"`

**Solution**: Added `_convert_qt_key_to_keyboard()` method to map Qt key names to keyboard library format.

### 2. Wrong API Method
**Problem**: The code was using `keyboard.on_press_key()` which is designed for specific key monitoring, not global hotkeys.

**Solution**: Changed to `keyboard.add_hotkey()` which properly registers global hotkeys.

### 3. Insufficient Error Handling
**Problem**: Errors were silently caught without detailed logging, making debugging difficult.

**Solution**: Added comprehensive logging with traceback printing for all keyboard operations.

### 4. Administrator Privileges (Windows)
**Important Note**: The Python `keyboard` library requires administrator privileges on Windows for global hotkeys. If the application is not run as administrator, keyboard shortcuts may not work consistently.

## Changes Made to `input_wrk.py`

### 1. Added `traceback` import
```python
import traceback
```

### 2. Enhanced `_start_keyboard_monitoring()` method
- Added conversion of Qt key names to keyboard library format
- Changed from `on_press_key()` to `add_hotkey()` for global hotkey support
- Added detailed logging for debugging
- Added traceback printing on errors

### 3. Added `_convert_qt_key_to_keyboard()` method
Maps common Qt key names to keyboard library format:
- Special keys: return→enter, escape→esc, control→ctrl, etc.
- Numpad keys: kp_0→num 0, kp_enter→num enter, etc.
- Function keys: F1-F12 (lowercase)
- Single characters: lowercase conversion

### 4. Enhanced `_on_keyboard_shortcut()` method
- Added logging to confirm when shortcuts are triggered

### 5. Enhanced `_stop_monitoring()` method
- Added logging for hook clearing
- Improved error messages

## Testing Recommendations

### Test Case 1: Keyboard Shortcuts
1. Open Preferences panel
2. Click "Set Shortcut..."
3. Press a key (e.g., F5, Space, Numpad 1)
4. Verify shortcut is saved
5. Test shortcut triggers reset (watch console for logs)

### Test Case 2: Gamepad Shortcuts
1. Connect a gamepad
2. Open Preferences panel
3. Click "Set Shortcut..."
4. Press a gamepad button
5. Verify shortcut is saved
6. Test shortcut triggers reset

### Test Case 3: Global Hotkey (requires admin)
1. **Run application as administrator**
2. Set a keyboard shortcut
3. Switch to another application (lose focus)
4. Press the shortcut key
5. Verify reset is triggered even without focus

## Console Output to Expect

**When setting a shortcut**:
```
[InputWorker] Shortcut set to: Space (key=space)
[InputWorker] Converted key 'space' to 'space' for keyboard library
[InputWorker] Successfully registered keyboard shortcut: space
```

**When shortcut is triggered**:
```
[InputWorker] Keyboard shortcut triggered: space
```

**When clearing shortcuts**:
```
[InputWorker] Cleared keyboard hooks
[InputWorker] Shortcut cleared
```

## Common Issues and Solutions

### Issue: Shortcut not working
**Possible Causes**:
1. Application not run as administrator (Windows requirement)
2. Key name conversion failed
3. Keyboard library not installed

**Debugging Steps**:
1. Check console for error messages
2. Look for "Successfully registered keyboard shortcut" message
3. Verify keyboard library is installed: `pip install keyboard`
4. Run as administrator

### Issue: Gamepad working but keyboard not
**Solution**: Run application as administrator on Windows

### Issue: Error "Failed to set keyboard shortcut"
**Check**:
1. Console for detailed traceback
2. Keyboard library installed
3. Administrator privileges
4. Key name conversion in logs

## Additional Notes

- Gamepad shortcuts work without administrator privileges
- Keyboard shortcuts require admin on Windows for global hotkey functionality
- All operations are logged to console for debugging
- The input worker runs in a separate thread to avoid blocking the GUI
