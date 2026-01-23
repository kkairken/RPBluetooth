# Migration to libgpiod

Quick guide for migrating from RPi.GPIO to libgpiod.

## Why Migrate?

✅ **Modern Interface**: Uses character device (`/dev/gpiochipX`) instead of deprecated sysfs
✅ **Better Isolation**: Proper resource management between processes
✅ **Universal**: Works on all Linux systems, not just Raspberry Pi
✅ **Future-Proof**: Active kernel development and maintenance
✅ **Raspberry Pi 5**: Better compatibility with latest hardware

## Quick Start

### 1. Install libgpiod

```bash
# Remove old library (optional)
sudo apt remove python3-rpi.gpio

# Install libgpiod
sudo apt install gpiod libgpiod2 python3-libgpiod

# Set up permissions
sudo usermod -a -G gpio $USER

# Reboot (required for group membership)
sudo reboot
```

### 2. Update Configuration

Edit your config file:

```yaml
lock:
  gpio_pin: 17
  gpio_chip: "gpiochip0"  # ADD THIS LINE
  active_high: true
  mock_mode: false
```

### 3. Test GPIO

```bash
# List available chips
gpiodetect

# Test GPIO 17
python3 tools/test_gpio.py --line 17

# Or use command line tools
gpioset gpiochip0 17=1  # Set HIGH
gpioset gpiochip0 17=0  # Set LOW
```

## Configuration Changes

| Setting | Old | New |
|---------|-----|-----|
| **Required** | `gpio_pin` | `gpio_pin` + `gpio_chip` |
| **Default chip** | N/A | `gpiochip0` |
| **Pin numbering** | BCM | BCM (same) |

**Example:**

```yaml
# Before
lock:
  gpio_pin: 17
  active_high: true

# After
lock:
  gpio_pin: 17
  gpio_chip: "gpiochip0"  # Added
  active_high: true
```

## Code Changes

### No changes needed for this project

The system automatically uses libgpiod. Your existing configuration just needs the `gpio_chip` parameter added.

### If you have custom GPIO code

**Before (RPi.GPIO):**
```python
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)
GPIO.output(17, GPIO.HIGH)
time.sleep(2)
GPIO.output(17, GPIO.LOW)
GPIO.cleanup()
```

**After (libgpiod):**
```python
import gpiod

chip = gpiod.Chip('gpiochip0')
line = chip.get_line(17)
line.request(consumer='myapp', type=gpiod.LINE_REQ_DIR_OUT)
line.set_value(1)
time.sleep(2)
line.set_value(0)
line.release()
chip.close()
```

## Troubleshooting

### Error: "Permission denied"

```bash
# Check permissions
ls -l /dev/gpiochip0

# Should show: crw-rw---- 1 root gpio

# Add user to gpio group
sudo usermod -a -G gpio $USER

# Reboot
sudo reboot
```

### Error: "No such file: gpiochip0"

```bash
# List available chips
gpiodetect

# Or check /dev
ls -l /dev/gpiochip*

# Update config with correct chip name
```

### Error: "Device or resource busy"

```bash
# Check what's using the GPIO
sudo lsof | grep gpio

# Or check specific line
gpioinfo gpiochip0 | grep "line  17"

# Reboot to release all
sudo reboot
```

### GPIO not working but no errors

1. **Check wiring**: Multimeter test
2. **Verify relay type**: `active_high` setting correct?
3. **Test isolation**: Use `tools/test_gpio.py`
4. **Check logs**: `tail -f face_access.log | grep -i gpio`

## Testing Checklist

- [ ] Install libgpiod packages
- [ ] Add user to gpio group
- [ ] Reboot system
- [ ] Update config with `gpio_chip`
- [ ] Run `gpiodetect` to verify chip
- [ ] Run `tools/test_gpio.py --line 17`
- [ ] Verify relay activates
- [ ] Start face access system
- [ ] Test door unlock

## Benefits Summary

| Feature | RPi.GPIO | libgpiod |
|---------|----------|----------|
| **Interface** | sysfs (deprecated) | character device (modern) |
| **Multi-process** | Conflicts possible | Proper isolation |
| **Permissions** | Root or sysfs hacks | Standard group-based |
| **Raspberry Pi 5** | Issues reported | Full support |
| **Other SBCs** | Raspberry Pi only | Universal Linux |
| **Maintenance** | Minimal | Active development |

## Rollback (if needed)

If you need to temporarily rollback:

1. **Reinstall RPi.GPIO:**
   ```bash
   sudo apt install python3-rpi.gpio
   ```

2. **Restore old lock.py:**
   ```bash
   # Contact support for RPi.GPIO version
   ```

3. **Update config:**
   ```yaml
   lock:
     gpio_pin: 17
     # Remove gpio_chip line
     active_high: true
   ```

Note: Not recommended as RPi.GPIO is deprecated.

## Need Help?

1. Check detailed guide: `docs/GPIO_SETUP.md`
2. Run diagnostic: `tools/test_gpio.py --list`
3. Check system logs: `journalctl -xe | grep gpio`
4. Review main README: `README.md`

## Resources

- **libgpiod GitHub**: https://git.kernel.org/pub/scm/libs/libgpiod/libgpiod.git
- **Python docs**: https://libgpiod.readthedocs.io/
- **Kernel GPIO**: https://www.kernel.org/doc/html/latest/driver-api/gpio/

---

**Migration Status**: ✅ Complete and tested
**Recommended for**: All new deployments
**Required for**: Raspberry Pi 5 users
