# What's New in v1.1.0

## GPIO Migration: RPi.GPIO → libgpiod

The system now uses **libgpiod** instead of RPi.GPIO for GPIO control.

### What This Means for You

✅ **Better compatibility** - Works on Raspberry Pi 5 and other Linux boards
✅ **Modern interface** - Uses `/dev/gpiochipX` character devices
✅ **Proper permissions** - Clean group-based access control
✅ **More stable** - Better resource isolation

### What You Need to Do

#### 1. Install libgpiod (One-time setup)

```bash
sudo apt install gpiod libgpiod2 python3-libgpiod
sudo usermod -a -G gpio $USER
sudo reboot
```

#### 2. Update Your Config

Add one line to your `config/my_config.yaml`:

```yaml
lock:
  gpio_pin: 17
  gpio_chip: "gpiochip0"  # ADD THIS LINE
  active_high: true
  mock_mode: false
```

#### 3. Test GPIO

```bash
# Verify installation
gpiodetect

# Test your GPIO
python3 tools/test_gpio.py --line 17
```

That's it! Everything else works the same.

### Quick Start

```bash
# Install
sudo apt install gpiod libgpiod2 python3-libgpiod
sudo usermod -a -G gpio $USER
sudo reboot

# Update config (add gpio_chip line)
nano config/my_config.yaml

# Test
python3 tools/test_gpio.py --line 17

# Run system
python src/main.py --config config/my_config.yaml
```

### Need Help?

- **Detailed guide**: `docs/GPIO_SETUP.md`
- **Migration guide**: `MIGRATION_GPIOD.md`
- **Test tool**: `tools/test_gpio.py`
- **Troubleshooting**: README.md → GPIO Issues

### Compatibility

- ✅ Raspberry Pi 3 Model B/B+
- ✅ Raspberry Pi 4
- ✅ Raspberry Pi 5 (improved support!)
- ✅ Other Linux SBCs (Orange Pi, Banana Pi, etc.)

### Breaking Changes

**Only one**: You must add `gpio_chip: "gpiochip0"` to your lock configuration.

Everything else remains the same:
- Same pin numbering (BCM)
- Same `active_high` logic
- Same `mock_mode` for testing
- No code changes needed

### Rollback

If you experience issues, you can temporarily use mock mode:

```yaml
lock:
  mock_mode: true  # Bypass GPIO temporarily
```

Then check `docs/GPIO_SETUP.md` for troubleshooting.

---

**Version**: 1.1.0
**Date**: 2025-01-22
**Status**: Stable and production-ready
