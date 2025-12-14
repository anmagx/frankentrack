"""
Input worker for frankentrack.

Handles all keyboard and gamepad input operations including:
- Shortcut monitoring for recenter operations
- Input capture during shortcut configuration
- Pygame management and gamepad state
"""

import threading
import time
import queue
import traceback
from util.error_utils import safe_queue_put
from config.config import QUEUE_PUT_TIMEOUT

# Try to import pygame for gamepad/joystick support
try:
    import os
    # Suppress pygame welcome message
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# Global pygame state manager to avoid conflicts
class PygameManager:
    _instance = None
    _initialized = False
    _joysticks = []
    _display_surface = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self):
        """Initialize pygame and joysticks safely."""
        if not PYGAME_AVAILABLE:
            return False
            
        try:
            if not self._initialized:
                # Clean slate
                pygame.quit()
                
                # Disable audio to reduce conflicts (like old implementation)
                pygame.mixer.quit()
                
                # Initialize pygame fully (required for joystick state updates)
                pygame.init()
                
                # Initialize joystick subsystem
                if pygame.get_init():
                    pygame.joystick.init()
                else:
                    return False
                
                # Initialize all joysticks once (only on first call)
                joystick_count = pygame.joystick.get_count()
                
                for i in range(joystick_count):
                    try:
                        joy = pygame.joystick.Joystick(i)
                        joy.init()
                        self._joysticks.append(joy)
                    except Exception as e:
                        # Skip joysticks that fail to initialize
                        continue
                
                self._initialized = True
                if len(self._joysticks) > 0:
                    print(f"[InputWorker] Initialized {len(self._joysticks)} gamepad(s)")
                    
            if len(self._joysticks) == 0:
                print(f"[InputWorker][PygameManager] WARNING: No joysticks could be initialized")
                return False
                
            return True
            
        except Exception as e:
            print(f"[InputWorker][PygameManager] Failed to initialize pygame: {e}")
            traceback.print_exc()
            self._initialized = False
            return False
    
    def get_joysticks(self):
        """Get list of initialized joysticks."""
        return self._joysticks if self._initialized else []
    
    def cleanup(self):
        """Clean up pygame resources (does not fully deinitialize - keeps pygame ready for reuse)."""
        # Don't fully cleanup - just stop using joysticks but keep pygame initialized
        # This prevents duplicate initialization messages on shortcut changes
        if self._initialized:
            try:
                # Note: We don't call quit() on pygame or joysticks anymore
                # This keeps pygame initialized and avoids duplicate "pygame 2.6.1..." messages
                # Joysticks will be reused when listener restarts
                pass
            except Exception as e:
                print(f"[InputWorker][PygameManager] Error during cleanup: {e}")


class InputWorker:
    """Worker that handles all input operations for shortcuts and monitoring."""
    
    def __init__(self, command_queue=None, response_queue=None):
        """
        Initialize the input worker.
        
        Args:
            command_queue: Queue to receive commands from GUI
            response_queue: Queue to send responses back to GUI
        """
        self.command_queue = command_queue or queue.Queue()
        self.response_queue = response_queue or queue.Queue()
        
        self.running = False
        self.worker_thread = None
        
        # Pygame management
        self.pygame_manager = PygameManager()
        
        # Current shortcut being monitored for triggering
        self.current_shortcut = None
        self.current_shortcut_display = None
        
        # Listener control - start/stop on demand
        self.keyboard_listener_active = False
        self.gamepad_listener_active = False
        self.keyboard_thread = None
        self.gamepad_thread = None
        
        # Capture mode - when true, both listeners report ANY input
        self.capture_mode = False
        
        # Track last button/hat states to detect transitions
        self._last_button_states = {}
        self._last_hat_states = {}

        # Keyboard support
        self.keyboard_available = False
        try:
            import keyboard
            self.keyboard_available = True
            self.keyboard = keyboard
        except ImportError:
            pass
    
    def start(self):
        """Start the input worker (listeners started on demand)."""
        if self.running:
            return
            
        self.running = True
        
        # Start command processing thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        print("[InputWorker] Started (listeners will start on demand)")
    
    def stop(self):
        """Stop the input worker and all listeners."""
        if not self.running:
            return
            
        self.running = False
        
        # Stop any active listeners
        self._stop_keyboard_listener()
        self._stop_gamepad_listener()
        
        # Wait for threads to finish
        for thread in [self.worker_thread, self.keyboard_thread, self.gamepad_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=1.0)
            
        print("[InputWorker] Stopped")
    
    def _worker_loop(self):
        """Main worker loop that processes commands."""
        while self.running:
            try:
                # Check for commands with a timeout
                try:
                    command = self.command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                self._process_command(command)
                
            except Exception as e:
                print(f"[InputWorker] Error in worker loop: {e}")
                time.sleep(0.1)
    
    def _process_command(self, command):
        """Process a command from the GUI."""
        if not isinstance(command, (list, tuple)) or len(command) < 1:
            return
            
        cmd_type = command[0]
        
        if cmd_type == 'set_shortcut':
            # Set the shortcut to monitor: ('set_shortcut', key, display_name)
            if len(command) >= 3:
                self._set_shortcut(command[1], command[2])
                
        elif cmd_type == 'clear_shortcut':
            # Clear any active shortcut monitoring
            self._clear_shortcut()
            
        elif cmd_type == 'start_capture':
            # Start input capture mode: ('start_capture',)
            self._start_capture()
            
        elif cmd_type == 'stop_capture':
            # Stop input capture mode: ('stop_capture',)
            self._stop_capture()
            
        elif cmd_type == 'trigger_reset':
            # Manually trigger reset (for testing): ('trigger_reset',)
            self._send_response(('shortcut_triggered', 'manual_trigger', 'reset_orientation'))
    
    def _set_shortcut(self, key, display_name):
        """Set the shortcut to monitor for reset operations."""
        # Stop any existing listeners
        self._stop_keyboard_listener()
        self._stop_gamepad_listener()
        
        self.current_shortcut = key
        self.current_shortcut_display = display_name
        
        if not key or key == 'None':
            print(f"[InputWorker] Shortcut cleared")
            return
        
        # Start appropriate listener based on key type
        if key.startswith('joy'):
            # Gamepad shortcut
            self._start_gamepad_listener()
        else:
            # Keyboard shortcut
            self._start_keyboard_listener()
    
    def _clear_shortcut(self):
        """Clear the current shortcut and stop listeners."""
        self._stop_keyboard_listener()
        self._stop_gamepad_listener()
        self.current_shortcut = None
        self.current_shortcut_display = None
        print("[InputWorker] Shortcut cleared, listeners stopped")
    
    def _start_capture(self):
        """Start input capture mode - both listeners active temporarily."""
        if self.capture_mode:
            return
        
        self.capture_mode = True
        # Reset state tracking to avoid stale transitions
        self._last_button_states.clear()
        self._last_hat_states.clear()
        
        # Start both listeners for capture
        self._start_keyboard_listener()
        self._start_gamepad_listener()
        
        print("[InputWorker] Capture mode enabled (both listeners active)")
    
    def _stop_capture(self):
        """Stop input capture mode and stop both listeners."""
        if not self.capture_mode:
            return
        
        self.capture_mode = False
        
        # Stop both listeners after capture
        self._stop_keyboard_listener()
        self._stop_gamepad_listener()
        
        print("[InputWorker] Capture mode disabled (both listeners stopped)")
    
    def _start_keyboard_listener(self):
        """Start keyboard listener thread."""
        if not self.keyboard_available:
            return
        
        if self.keyboard_listener_active:
            return  # Already running
        
        self.keyboard_listener_active = True
        self.keyboard_thread = threading.Thread(target=self._keyboard_listener_loop, daemon=True)
        self.keyboard_thread.start()
    
    def _stop_keyboard_listener(self):
        """Stop keyboard listener thread."""
        if not self.keyboard_listener_active:
            return
        
        self.keyboard_listener_active = False
        
        # Clear keyboard hooks
        if self.keyboard_available:
            try:
                self.keyboard.unhook_all()
            except Exception:
                pass
        
        # Wait for thread
        if self.keyboard_thread and self.keyboard_thread.is_alive():
            self.keyboard_thread.join(timeout=0.5)
        
        self.keyboard_thread = None
    
    def _keyboard_listener_loop(self):
        """Keyboard listener thread loop."""
        if not self.keyboard_available:
            return
        
        print("[InputWorker] Keyboard listener started")
        
        def on_key_event(event):
            """Handle any keyboard event."""
            if not self.keyboard_listener_active:
                return
                
            if not event.event_type == 'down':  # Only respond to key down events
                return
                
            key_name = event.name
            
            # In capture mode, report the key
            if self.capture_mode:
                display_name = key_name.upper() if len(key_name) == 1 else key_name.title()
                print(f"[InputWorker] Keyboard captured: {key_name} (display: {display_name})")
                self._send_response(('input_captured', key_name, display_name))
                return
            
            # In monitoring mode, check if it matches current shortcut
            if self.current_shortcut and self.current_shortcut == key_name:
                print(f"[InputWorker] Keyboard shortcut triggered: {self.current_shortcut}")
                self._send_response(('shortcut_triggered', self.current_shortcut, 'reset_orientation'))
        
        try:
            # Hook all keyboard events
            self.keyboard.hook(on_key_event)
            
            # Keep thread alive while listener is active
            while self.keyboard_listener_active and self.running:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"[InputWorker] Keyboard listener error: {e}")
            traceback.print_exc()
        finally:
            try:
                self.keyboard.unhook_all()
            except Exception:
                pass
            print("[InputWorker] Keyboard listener stopped")
    
    def _start_gamepad_listener(self):
        """Start gamepad listener thread."""
        if not PYGAME_AVAILABLE:
            return
        
        if self.gamepad_listener_active:
            return  # Already running
        
        # Initialize pygame if needed
        if not self.pygame_manager.initialize():
            print("[InputWorker] Failed to initialize pygame for gamepad")
            return
        
        self.gamepad_listener_active = True
        self.gamepad_thread = threading.Thread(target=self._gamepad_listener_loop, daemon=True)
        self.gamepad_thread.start()
    
    def _stop_gamepad_listener(self):
        """Stop gamepad listener thread."""
        if not self.gamepad_listener_active:
            return
        
        self.gamepad_listener_active = False
        
        # Wait for thread
        if self.gamepad_thread and self.gamepad_thread.is_alive():
            self.gamepad_thread.join(timeout=0.5)
        
        self.gamepad_thread = None
    
    def _gamepad_listener_loop(self):
        """Gamepad listener thread loop."""
        if not PYGAME_AVAILABLE:
            return
        
        joysticks = self.pygame_manager.get_joysticks()
        
        if not joysticks:
            self.gamepad_listener_active = False
            return
        
        try:
            check_interval = 1.0 / 30.0  # 30 FPS
            last_check = time.time()
            
            while self.gamepad_listener_active and self.running:
                current_time = time.time()
                
                if current_time - last_check >= check_interval:
                    last_check = current_time
                    
                    try:
                        # Update pygame state without processing events
                        pygame.event.pump()
                        
                        # Check all joysticks for input
                        for i, joystick in enumerate(joysticks):
                            if not joystick.get_init():
                                continue
                            
                            # Check all buttons
                            for button_id in range(joystick.get_numbuttons()):
                                try:
                                    pressed = bool(joystick.get_button(button_id))
                                    btn_key = (i, 'b', button_id)
                                    last_state = self._last_button_states.get(btn_key, False)
                                    
                                    # Button press detected (transition from False to True)
                                    if pressed and not last_state:
                                        key_id = f"joy{i}_button{button_id}"
                                        
                                        # In capture mode, report the button
                                        if self.capture_mode:
                                            try:
                                                joy_name = joystick.get_name()
                                                display_name = f"{joy_name} Button {button_id}"
                                            except Exception:
                                                display_name = f"Joystick {i} Button {button_id}"
                                            
                                            print(f"[InputWorker] Gamepad captured: {key_id} (display: {display_name})")
                                            self._send_response(('input_captured', key_id, display_name))
                                        
                                        # In monitoring mode, check if it matches current shortcut
                                        elif self.current_shortcut == key_id:
                                            print(f"[InputWorker] Gamepad shortcut triggered: {key_id}")
                                            self._send_response(('shortcut_triggered', key_id, 'reset_orientation'))
                                    
                                    self._last_button_states[btn_key] = pressed
                                    
                                except Exception as e:
                                    print(f"[InputWorker] Error checking button {button_id} on joystick {i}: {e}")
                            
                            # Check all hats (D-pads)
                            for hat_id in range(joystick.get_numhats()):
                                try:
                                    hat_value = joystick.get_hat(hat_id)
                                    hat_key = (i, 'h', hat_id)
                                    last_hat = self._last_hat_states.get(hat_key, (0, 0))
                                    
                                    # Hat moved (and not centered)
                                    if hat_value != (0, 0) and hat_value != last_hat:
                                        key_id = f"joy{i}_hat{hat_id}_{hat_value[0]}_{hat_value[1]}"
                                        
                                        # In capture mode, report the hat
                                        if self.capture_mode:
                                            try:
                                                joy_name = joystick.get_name()
                                                hat_dir = []
                                                if hat_value[1] == 1: hat_dir.append("Up")
                                                elif hat_value[1] == -1: hat_dir.append("Down")
                                                if hat_value[0] == 1: hat_dir.append("Right")
                                                elif hat_value[0] == -1: hat_dir.append("Left")
                                                display_name = f"{joy_name} D-Pad {' '.join(hat_dir)}"
                                            except Exception:
                                                display_name = f"Joystick {i} Hat {hat_id} {hat_value}"
                                            
                                            print(f"[InputWorker] Gamepad captured: {key_id} (display: {display_name})")
                                            self._send_response(('input_captured', key_id, display_name))
                                        
                                        # In monitoring mode, check if it matches current shortcut
                                        elif self.current_shortcut == key_id:
                                            print(f"[InputWorker] Gamepad shortcut triggered: {key_id}")
                                            self._send_response(('shortcut_triggered', key_id, 'reset_orientation'))
                                    
                                    self._last_hat_states[hat_key] = hat_value
                                    
                                except Exception as e:
                                    print(f"[InputWorker] Error checking hat {hat_id} on joystick {i}: {e}")
                    
                    except Exception as e:
                        print(f"[InputWorker] Gamepad listener error: {e}")
                        traceback.print_exc()
                
                time.sleep(0.033)  # ~30 FPS
                
        except Exception as e:
            print(f"[InputWorker] Gamepad listener fatal error: {e}")
            traceback.print_exc()
    
    def _send_response(self, response):
        """Send a response back to the GUI."""
        try:
            self.response_queue.put(response, timeout=QUEUE_PUT_TIMEOUT)
            print(f"[InputWorker] Response sent successfully: {response[0]}")
        except queue.Full:
            print(f"[InputWorker] ERROR: Response queue full, dropping response: {response[0]}")
        except Exception as e:
            print(f"[InputWorker] ERROR sending response: {e}")


def run_worker(command_queue, response_queue, stop_event, log_queue):
    """Entry point for the input worker process."""
    try:
        worker = InputWorker(command_queue, response_queue)
        worker.start()
        
        # Keep worker running until stop event is set
        while not stop_event.is_set():
            try:
                stop_event.wait(timeout=1.0)
            except KeyboardInterrupt:
                break
        
        worker.stop()
        
    except Exception as e:
        print(f"[InputWorker] Fatal error: {e}")
        import traceback
        traceback.print_exc()
