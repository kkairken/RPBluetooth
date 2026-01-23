# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2025-01-22

### Changed
- **BREAKING**: Migrated from RPi.GPIO to libgpiod for GPIO control
  - Modern character device interface (`/dev/gpiochipX`)
  - Better resource isolation and permissions
  - Works on all Linux systems, not just Raspberry Pi
  - Added `gpio_chip` parameter to lock configuration

### Added
- New configuration parameter: `lock.gpio_chip` (default: "gpiochip0")
- Comprehensive GPIO setup guide: `docs/GPIO_SETUP.md`
- GPIO testing tool: `tools/test_gpio.py`
- Context manager support for LockController (`with` statement)

### Migration Guide

**Configuration changes:**

Old config:
```yaml
lock:
  gpio_pin: 17
  active_high: true
  mock_mode: false
```

New config (add gpio_chip):
```yaml
lock:
  gpio_pin: 17
  gpio_chip: "gpiochip0"  # NEW PARAMETER
  active_high: true
  mock_mode: false
```

**Installation changes:**

Old:
```bash
sudo apt install python3-rpi.gpio
# or
pip install RPi.GPIO
```

New:
```bash
# Install libgpiod system packages
sudo apt install gpiod libgpiod2 python3-libgpiod

# Set up permissions
sudo usermod -a -G gpio $USER
sudo reboot
```

**Code changes:**

No code changes required in user applications. The system handles the migration automatically. If you have custom code using RPi.GPIO, see `docs/GPIO_SETUP.md` for migration examples.

**Benefits:**
- More stable GPIO access
- Better compatibility with modern kernels
- Proper permission model
- Works on Raspberry Pi 5 (which has issues with RPi.GPIO)
- Standard across all Linux SBCs

### Fixed
- Improved GPIO cleanup on shutdown
- Better error messages for GPIO permission issues
- Automatic fallback to mock mode if GPIO unavailable

## [1.0.0] - 2025-01-22

### Added
- Initial release
- Offline face recognition system
- BLE GATT server for registration
- USB and RTSP camera support
- SQLite database with audit logging
- HMAC-SHA256 authentication
- GPIO lock control with RPi.GPIO
- Production-ready documentation
- Comprehensive unit tests
