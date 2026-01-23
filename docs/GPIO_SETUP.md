# GPIO Setup Guide (libgpiod)

This system uses **libgpiod**, the modern Linux GPIO interface, instead of the deprecated sysfs or RPi.GPIO.

## Why libgpiod?

- ✅ **Modern**: Character device interface (`/dev/gpiochipX`)
- ✅ **Safe**: Better resource isolation between processes
- ✅ **Standard**: Works on all Linux systems (not just Raspberry Pi)
- ✅ **Maintained**: Active kernel development (kernel 4.8+)
- ✅ **Permissions**: Proper access control via device permissions

## Installation

### On Raspberry Pi OS

```bash
# Install libgpiod library and Python bindings
sudo apt update
sudo apt install -y gpiod libgpiod2 python3-libgpiod

# Verify installation
gpioinfo
```

### Alternative: pip installation

If system packages are not available:

```bash
# Install development libraries first
sudo apt install -y libgpiod-dev

# Install Python package
pip install libgpiod
```

## Permissions Setup

### Option 1: Add user to gpio group (Recommended)

```bash
# Add current user to gpio group
sudo usermod -a -G gpio $USER

# Verify membership
groups $USER

# Reboot or re-login for changes to take effect
sudo reboot
```

### Option 2: Set udev rules

Create `/etc/udev/rules.d/99-gpio.rules`:

```
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", MODE="0660", GROUP="gpio"
```

Reload udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Option 3: Run with sudo (Not recommended for production)

```bash
sudo python src/main.py --config config/my_config.yaml
```

## Configuration

Edit your config file (`config/my_config.yaml`):

```yaml
lock:
  gpio_pin: 17          # GPIO line number (BCM numbering)
  gpio_chip: "gpiochip0"  # GPIO chip device name
  active_high: true     # Relay activation logic
  mock_mode: false      # Set true for testing without hardware
```

### GPIO Chip Selection

Raspberry Pi typically has one GPIO chip:

```bash
# List available GPIO chips
gpiodetect

# Expected output:
# gpiochip0 [pinctrl-bcm2835] (54 lines)
```

For other boards, you may have multiple chips:
- `gpiochip0` - Main GPIO
- `gpiochip1` - Additional GPIO expander
- etc.

### GPIO Pin Numbering

The system uses **BCM numbering** (same as RPi.GPIO BCM mode):

```
Physical Pin → BCM Number
Pin 11       → GPIO 17 (default)
Pin 12       → GPIO 18
Pin 13       → GPIO 27
```

Reference: https://pinout.xyz/

## Testing GPIO

### Test with gpioset/gpioget

```bash
# Set GPIO 17 to HIGH
gpioset gpiochip0 17=1

# Set GPIO 17 to LOW
gpioset gpiochip0 17=0

# Read GPIO 17 value
gpioget gpiochip0 17

# Monitor GPIO 17
gpiomon gpiochip0 17
```

### Test with Python

```python
#!/usr/bin/env python3
import gpiod
import time

# Open GPIO chip
chip = gpiod.Chip('gpiochip0')

# Get line 17
line = chip.get_line(17)

# Request line as output
line.request(consumer='test', type=gpiod.LINE_REQ_DIR_OUT)

# Blink LED/relay
for i in range(5):
    print(f"ON")
    line.set_value(1)
    time.sleep(1)

    print(f"OFF")
    line.set_value(0)
    time.sleep(1)

# Cleanup
line.release()
chip.close()
print("Done")
```

Save as `test_gpio.py` and run:
```bash
python3 test_gpio.py
```

## Hardware Wiring

### Relay Module Connection

```
Raspberry Pi          Relay Module
-----------          ------------
GPIO 17     ------>  IN
5V          ------>  VCC
GND         ------>  GND

Relay Module         Door Lock
-----------          ----------
NO (Normally Open)   Lock Power +
COM (Common)         Power Supply +
```

### Relay Types

**Active High (default):**
- GPIO HIGH (1) = Relay ON (unlocked)
- GPIO LOW (0) = Relay OFF (locked)
- Set `active_high: true`

**Active Low:**
- GPIO LOW (0) = Relay ON (unlocked)
- GPIO HIGH (1) = Relay OFF (locked)
- Set `active_high: false`

## Troubleshooting

### Error: "No such file or directory: gpiochip0"

**Cause**: GPIO chip not found

**Solution**:
```bash
# Check available chips
gpiodetect

# Try different chip name
ls -l /dev/gpiochip*

# Update config with correct chip name
```

### Error: "Permission denied"

**Cause**: User doesn't have GPIO access

**Solution**:
```bash
# Add to gpio group
sudo usermod -a -G gpio $USER

# Verify
ls -l /dev/gpiochip0
# Should show: crw-rw---- 1 root gpio ...

# Reboot
sudo reboot
```

### Error: "Device or resource busy"

**Cause**: GPIO line already in use

**Solution**:
```bash
# Check what's using the GPIO
sudo lsof | grep gpio

# Or check line status
gpioinfo gpiochip0 | grep "line  17"

# Restart system to release all GPIOs
sudo reboot
```

### Error: "ImportError: No module named 'gpiod'"

**Cause**: libgpiod Python bindings not installed

**Solution**:
```bash
# Install system package
sudo apt install python3-libgpiod

# Or install via pip
pip install libgpiod
```

### System doesn't unlock (mock mode works)

**Checklist**:

1. **Verify wiring:**
   ```bash
   gpioget gpiochip0 17  # Should output 0 or 1
   gpioset gpiochip0 17=1  # Should activate relay (hear click)
   ```

2. **Check relay module:**
   - LED should light when activated
   - Multimeter: continuity between NO and COM when active

3. **Verify config:**
   ```yaml
   lock:
     gpio_pin: 17  # Correct pin?
     active_high: true  # Matches relay type?
     mock_mode: false  # Must be false for real GPIO
   ```

4. **Check logs:**
   ```bash
   tail -f face_access.log | grep -i gpio
   ```

5. **Test isolation:**
   ```python
   # Direct test (run as user)
   import gpiod
   chip = gpiod.Chip('gpiochip0')
   line = chip.get_line(17)
   line.request(consumer='test', type=gpiod.LINE_REQ_DIR_OUT)
   line.set_value(1)
   input("Press Enter to unlock...")
   line.set_value(0)
   line.release()
   ```

## Mock Mode for Testing

Test without hardware:

```yaml
lock:
  mock_mode: true  # Simulates GPIO operations
```

In mock mode:
- No actual GPIO operations
- Logs show simulated state changes
- Useful for development/testing

## Migration from RPi.GPIO

If you were using the old RPi.GPIO version:

| RPi.GPIO | libgpiod |
|----------|----------|
| `GPIO.setmode(GPIO.BCM)` | N/A (always BCM) |
| `GPIO.setup(17, GPIO.OUT)` | `line.request(..., type=LINE_REQ_DIR_OUT)` |
| `GPIO.output(17, GPIO.HIGH)` | `line.set_value(1)` |
| `GPIO.output(17, GPIO.LOW)` | `line.set_value(0)` |
| `GPIO.cleanup()` | `line.release(); chip.close()` |

**No code changes needed** - the system handles the migration automatically!

## Advanced Usage

### Multiple GPIO Lines

To control multiple relays/devices:

```python
import gpiod

chip = gpiod.Chip('gpiochip0')

# Request multiple lines
lines = chip.get_lines([17, 18, 27])
lines.request(consumer='multi', type=gpiod.LINE_REQ_DIR_OUT)

# Set values
lines.set_values([1, 0, 1])  # GPIO 17=HIGH, 18=LOW, 27=HIGH

# Cleanup
lines.release()
```

### Input Monitoring (e.g., for admin button)

```python
import gpiod

chip = gpiod.Chip('gpiochip0')
line = chip.get_line(23)  # Admin button on GPIO 23

# Request as input with pull-up
line.request(
    consumer='button',
    type=gpiod.LINE_REQ_DIR_IN,
    flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP
)

# Read value
value = line.get_value()
print(f"Button pressed: {value == 0}")

line.release()
```

### Event Detection (button press)

```python
import gpiod

chip = gpiod.Chip('gpiochip0')
line = chip.get_line(23)

# Request with edge detection
line.request(
    consumer='button',
    type=gpiod.LINE_REQ_EV_FALLING_EDGE
)

print("Waiting for button press...")
event = line.event_wait(timeout=10)  # 10 second timeout

if event:
    evt = line.event_read()
    print(f"Button pressed at {evt.sec}.{evt.nsec}")

line.release()
```

## Resources

- **libgpiod GitHub**: https://git.kernel.org/pub/scm/libs/libgpiod/libgpiod.git
- **Python bindings docs**: https://libgpiod.readthedocs.io/
- **Raspberry Pi pinout**: https://pinout.xyz/
- **Kernel GPIO docs**: https://www.kernel.org/doc/html/latest/driver-api/gpio/

## FAQ

**Q: Do I need to install kernel modules?**
A: No, GPIO support is built into modern Linux kernels (4.8+).

**Q: Can I use this on other SBCs (Orange Pi, Banana Pi, etc.)?**
A: Yes! libgpiod works on any Linux system. Just adjust the gpio_chip and pin numbers.

**Q: What if I have multiple processes accessing GPIO?**
A: libgpiod handles this better than sysfs. Each process gets proper isolation and exclusive access when requesting lines.

**Q: Does this work on Raspberry Pi 5?**
A: Yes, and it's actually recommended as RPi.GPIO may have issues on Pi 5.

**Q: Can I mix libgpiod with other GPIO libraries?**
A: Not recommended. Stick to one library to avoid conflicts.

---

**Need help?** Check logs: `tail -f face_access.log | grep -i gpio`
