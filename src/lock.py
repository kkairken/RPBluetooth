"""
Lock controller module.
Controls door lock via GPIO relay using libgpiod (modern GPIO interface).
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class LockController:
    """Controls door lock via GPIO relay using libgpiod."""

    def __init__(
        self,
        gpio_pin: int = 17,
        active_high: bool = True,
        mock_mode: bool = False,
        unlock_duration: float = 3.0,
        gpio_chip: str = "gpiochip0"
    ):
        """
        Initialize lock controller.

        Args:
            gpio_pin: GPIO line number (BCM numbering, e.g., 17)
            active_high: True if relay is active-high, False if active-low
            mock_mode: If True, don't use actual GPIO (for testing)
            unlock_duration: How long to keep lock open (seconds)
            gpio_chip: GPIO chip device name (default: gpiochip0)
        """
        self.gpio_pin = gpio_pin
        self.active_high = active_high
        self.mock_mode = mock_mode
        self.unlock_duration = unlock_duration
        self.gpio_chip_name = gpio_chip

        # gpiod objects
        self.chip = None
        self.line = None
        self.gpio_initialized = False

        if not mock_mode:
            self._init_gpio()
        else:
            logger.info("Lock controller in MOCK mode (no actual GPIO)")

    def _init_gpio(self):
        """Initialize GPIO using libgpiod."""
        try:
            import gpiod
            self.gpiod = gpiod

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

            # Initialize to locked state
            self._set_lock_state(False)

            self.gpio_initialized = True
            logger.info(
                f"GPIO initialized via libgpiod: chip={self.gpio_chip_name}, "
                f"line={self.gpio_pin}, active_high={self.active_high}"
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
            logger.error(f"GPIO initialization failed: {e}")
            logger.warning("Switching to mock mode")
            self.mock_mode = True

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

            # Set GPIO line value
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
        Unlock the door for a specified duration.

        Args:
            duration: Override default unlock duration (seconds)
        """
        if duration is None:
            duration = self.unlock_duration

        logger.info(f"Unlocking for {duration} seconds")

        # Unlock
        self._set_lock_state(True)

        # Wait
        time.sleep(duration)

        # Lock again
        self._set_lock_state(False)

        logger.info("Lock re-engaged")

    def lock(self):
        """Immediately lock the door."""
        logger.info("Locking door")
        self._set_lock_state(False)

    def cleanup(self):
        """Clean up GPIO resources."""
        if not self.mock_mode and self.gpio_initialized:
            try:
                # Ensure locked state before cleanup
                self._set_lock_state(False)

                # Release GPIO line
                if self.line:
                    self.line.release()
                    logger.info("GPIO line released")

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
