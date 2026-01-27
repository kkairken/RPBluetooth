"""
Lock controller module.
Controls door lock via GPIO relay using libgpiod (modern GPIO interface).
Supports both libgpiod v1.x and v2.x APIs.
Includes exit button support for manual door release.
"""
import logging
import time
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class LockController:
    """Controls door lock via GPIO relay using libgpiod."""

    def __init__(
        self,
        gpio_pin: int = 17,
        active_high: bool = True,
        mock_mode: bool = False,
        unlock_duration: float = 3.0,
        gpio_chip: str = "gpiochip0",
        button_pin: Optional[int] = None,
        button_active_low: bool = True,
        button_debounce_ms: int = 50
    ):
        """
        Initialize lock controller.

        Args:
            gpio_pin: GPIO line number for lock relay (BCM numbering, e.g., 17)
            active_high: True if relay is active-high, False if active-low
            mock_mode: If True, don't use actual GPIO (for testing)
            unlock_duration: How long to keep lock open (seconds)
            gpio_chip: GPIO chip device name (default: gpiochip0)
            button_pin: GPIO line number for exit button (None to disable)
            button_active_low: True if button connects to GND (use internal pull-up)
            button_debounce_ms: Debounce time in milliseconds
        """
        self.gpio_pin = gpio_pin
        self.active_high = active_high
        self.mock_mode = mock_mode
        self.unlock_duration = unlock_duration
        self.gpio_chip_name = gpio_chip

        # Button configuration
        self.button_pin = button_pin
        self.button_active_low = button_active_low
        self.button_debounce_ms = button_debounce_ms

        # gpiod objects (for v1.x)
        self.chip = None
        self.line = None
        # gpiod objects (for v2.x)
        self._request = None
        self._gpiod_version = None
        self.gpio_initialized = False

        # Button state
        self._button_request = None  # v2.x
        self._button_line = None     # v1.x
        self._button_thread = None
        self._button_running = False
        self._last_button_time = 0
        self._button_callback: Optional[Callable[[], None]] = None

        # Lock state tracking (prevents multiple unlock calls while already unlocking)
        self._is_unlocking = False
        self._unlock_lock = threading.Lock()

        if not mock_mode:
            self._init_gpio()
        else:
            logger.info("Lock controller in MOCK mode (no actual GPIO)")

    def _detect_gpiod_version(self, gpiod) -> int:
        """Detect libgpiod version (1 or 2)."""
        # v2.x has 'request_lines' on Chip, v1.x has 'get_line'
        if hasattr(gpiod, 'Chip'):
            # Check if Chip has get_line (v1) or request_lines (v2)
            chip_class = gpiod.Chip
            if hasattr(chip_class, 'request_lines') or hasattr(gpiod, 'LineSettings'):
                return 2
            else:
                return 1
        return 1

    def _init_gpio(self):
        """Initialize GPIO using libgpiod (auto-detects v1.x or v2.x)."""
        try:
            import gpiod
            self.gpiod = gpiod

            self._gpiod_version = self._detect_gpiod_version(gpiod)
            logger.info(f"Detected libgpiod version: {self._gpiod_version}.x")

            if self._gpiod_version == 2:
                self._init_gpio_v2(gpiod)
            else:
                self._init_gpio_v1(gpiod)

            # Initialize to locked state
            self._set_lock_state(False)

            self.gpio_initialized = True
            logger.info(
                f"GPIO initialized via libgpiod v{self._gpiod_version}: "
                f"chip={self.gpio_chip_name}, line={self.gpio_pin}, active_high={self.active_high}"
            )

        except ImportError:
            logger.warning("libgpiod not available, switching to mock mode")
            logger.info("Install with: sudo apt install python3-libgpiod")
            self.mock_mode = True
        except FileNotFoundError as e:
            logger.error(f"GPIO chip not found: {e}")
            logger.warning("Switching to mock mode")
            self.mock_mode = True
        except PermissionError:
            logger.error("Permission denied accessing GPIO. Add user to gpio group:")
            logger.error("  sudo usermod -a -G gpio $USER")
            logger.warning("Switching to mock mode")
            self.mock_mode = True
        except Exception as e:
            logger.error(f"GPIO initialization failed: {type(e).__name__}: {e}")
            logger.warning("Switching to mock mode")
            self.mock_mode = True

    def _init_gpio_v1(self, gpiod):
        """Initialize GPIO using libgpiod v1.x API."""
        # Open GPIO chip
        self.chip = gpiod.Chip(self.gpio_chip_name)

        # Get GPIO line
        self.line = self.chip.get_line(self.gpio_pin)

        # Request line as output
        self.line.request(
            consumer="face_access_lock",
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[0]  # Start with 0 (locked)
        )

    def _init_gpio_v2(self, gpiod):
        """Initialize GPIO using libgpiod v2.x API."""
        # In v2.x, we use request_lines() instead of get_line()
        chip_path = f"/dev/{self.gpio_chip_name}"

        # Create line settings for output
        settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE
        )

        # Request the line
        self._request = gpiod.request_lines(
            chip_path,
            consumer="face_access_lock",
            config={self.gpio_pin: settings}
        )

    def _init_button_v1(self, gpiod):
        """Initialize exit button using libgpiod v1.x API."""
        # Get button line from existing chip
        self._button_line = self.chip.get_line(self.button_pin)

        # Request as input with pull-up or pull-down
        flags = gpiod.LINE_REQ_FLAG_BIAS_PULL_UP if self.button_active_low else gpiod.LINE_REQ_FLAG_BIAS_PULL_DOWN
        self._button_line.request(
            consumer="face_access_button",
            type=gpiod.LINE_REQ_DIR_IN,
            flags=flags
        )

    def _init_button_v2(self, gpiod):
        """Initialize exit button using libgpiod v2.x API."""
        chip_path = f"/dev/{self.gpio_chip_name}"

        # Create line settings for input with bias
        if self.button_active_low:
            bias = gpiod.line.Bias.PULL_UP
        else:
            bias = gpiod.line.Bias.PULL_DOWN

        settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT,
            bias=bias
        )

        # Request the button line
        self._button_request = gpiod.request_lines(
            chip_path,
            consumer="face_access_button",
            config={self.button_pin: settings}
        )

    def start_button_monitor(self, callback: Optional[Callable[[], None]] = None):
        """
        Start monitoring the exit button in a background thread.

        Args:
            callback: Optional callback to run on button press.
                     If None, will call self.unlock() directly.
        """
        if self.button_pin is None:
            logger.warning("No button pin configured, cannot start monitor")
            return

        if self._button_thread and self._button_thread.is_alive():
            logger.warning("Button monitor already running")
            return

        # Initialize button GPIO if not done yet
        if not self.mock_mode and self._button_line is None and self._button_request is None:
            try:
                if self._gpiod_version == 2:
                    self._init_button_v2(self.gpiod)
                else:
                    self._init_button_v1(self.gpiod)
                logger.info(f"Exit button initialized on GPIO {self.button_pin}")
            except Exception as e:
                logger.error(f"Failed to initialize button: {e}")
                return

        self._button_callback = callback
        self._button_running = True
        self._button_thread = threading.Thread(
            target=self._button_monitor_loop,
            daemon=True,
            name="ExitButtonMonitor"
        )
        self._button_thread.start()
        logger.info(f"Exit button monitor started (pin={self.button_pin}, active_low={self.button_active_low})")

    def stop_button_monitor(self):
        """Stop the button monitoring thread."""
        self._button_running = False
        if self._button_thread:
            self._button_thread.join(timeout=1.0)
            self._button_thread = None
        logger.info("Exit button monitor stopped")

    def _read_button(self) -> bool:
        """Read current button state. Returns True if pressed."""
        if self.mock_mode:
            return False

        try:
            if self._gpiod_version == 2:
                value = self._button_request.get_value(self.button_pin)
                raw_value = (value == self.gpiod.line.Value.ACTIVE)
            else:
                raw_value = bool(self._button_line.get_value())

            # Invert if active_low (button pressed = line goes LOW)
            return not raw_value if self.button_active_low else raw_value

        except Exception as e:
            logger.error(f"Error reading button: {e}")
            return False

    def _button_monitor_loop(self):
        """Background thread loop for monitoring button presses."""
        logger.debug("Button monitor loop started")
        was_pressed = False

        while self._button_running:
            try:
                is_pressed = self._read_button()
                current_time = time.time() * 1000  # ms

                # Detect rising edge (button just pressed) with debounce
                if is_pressed and not was_pressed:
                    if current_time - self._last_button_time > self.button_debounce_ms:
                        self._last_button_time = current_time
                        logger.info("Exit button pressed!")

                        # Run callback or default unlock
                        if self._button_callback:
                            try:
                                self._button_callback()
                            except Exception as e:
                                logger.error(f"Button callback error: {e}")
                        else:
                            # Default: unlock the door
                            self.unlock()

                was_pressed = is_pressed

                # Poll interval (10ms for responsive button detection)
                time.sleep(0.01)

            except Exception as e:
                logger.error(f"Button monitor error: {e}")
                time.sleep(0.1)

    def _set_lock_state(self, unlock: bool):
        """
        Set physical lock state.

        Args:
            unlock: True to unlock, False to lock
        """
        if self.mock_mode:
            state_str = "UNLOCKED" if unlock else "LOCKED"
            logger.info(f"[MOCK] Lock state: {state_str}")
            return

        try:
            # Determine GPIO value based on active_high setting
            if self.active_high:
                gpio_value = 1 if unlock else 0
            else:
                gpio_value = 0 if unlock else 1

            # Set GPIO line value based on version
            if self._gpiod_version == 2:
                # v2.x API
                value = self.gpiod.line.Value.ACTIVE if gpio_value else self.gpiod.line.Value.INACTIVE
                self._request.set_value(self.gpio_pin, value)
            else:
                # v1.x API
                self.line.set_value(gpio_value)

            state_str = "UNLOCKED" if unlock else "LOCKED"
            logger.info(
                f"Lock state: {state_str} "
                f"(line {self.gpio_pin} = {gpio_value})"
            )

        except Exception as e:
            logger.error(f"Failed to set lock state: {e}")

    def unlock(self, duration: Optional[float] = None):
        """
        Unlock the door for a specified duration (non-blocking).
        Runs in a separate thread to avoid blocking the main event loop.
        Prevents multiple simultaneous unlock calls.

        Args:
            duration: Override default unlock duration (seconds)
        """
        # Prevent multiple unlock calls while already unlocking
        with self._unlock_lock:
            if self._is_unlocking:
                logger.debug("Unlock already in progress, skipping duplicate call")
                return
            self._is_unlocking = True

        if duration is None:
            duration = self.unlock_duration

        # Run unlock in a separate thread to avoid blocking asyncio event loop
        def _do_unlock():
            try:
                logger.info(f"Unlocking for {duration} seconds")

                # Unlock
                self._set_lock_state(True)

                # Wait
                time.sleep(duration)

                # Lock again
                self._set_lock_state(False)

                logger.info("Lock re-engaged")
            finally:
                with self._unlock_lock:
                    self._is_unlocking = False

        unlock_thread = threading.Thread(target=_do_unlock, daemon=True)
        unlock_thread.start()

    def lock(self):
        """Immediately lock the door."""
        logger.info("Locking door")
        self._set_lock_state(False)

    def is_unlocking(self) -> bool:
        """Check if unlock is currently in progress."""
        with self._unlock_lock:
            return self._is_unlocking

    def cleanup(self):
        """Clean up GPIO resources."""
        # Stop button monitor first
        if self._button_running:
            self.stop_button_monitor()

        if not self.mock_mode and self.gpio_initialized:
            try:
                # Ensure locked state before cleanup
                self._set_lock_state(False)

                if self._gpiod_version == 2:
                    # v2.x API - release requests
                    if self._button_request:
                        self._button_request.release()
                        self._button_request = None
                        logger.info("Button GPIO released (v2)")

                    if self._request:
                        self._request.release()
                        self._request = None
                        logger.info("Lock GPIO released (v2)")
                else:
                    # v1.x API
                    # Release button line
                    if self._button_line:
                        self._button_line.release()
                        self._button_line = None
                        logger.info("Button GPIO line released")

                    # Release lock line
                    if self.line:
                        self.line.release()
                        logger.info("Lock GPIO line released")

                    # Close chip
                    if self.chip:
                        self.chip.close()
                        logger.info("GPIO chip closed")

            except Exception as e:
                logger.error(f"GPIO cleanup error: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
