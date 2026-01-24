# RP3 Face Access - Production Deployment

## Quick Start

```bash
# 1. Copy project to Raspberry Pi
scp -r rp3_face_access pi@raspberrypi:/home/pi/

# 2. SSH to Raspberry Pi
ssh pi@raspberrypi

# 3. Run installation
cd /home/pi/rp3_face_access/deploy
sudo ./install.sh

# 4. Copy your ONNX model
# scp insightface_medium.onnx pi@raspberrypi:/home/pi/rp3_face_access/models/

# 5. Edit production config
nano /home/pi/rp3_face_access/config/production.yaml

# 6. Start service
sudo systemctl start face-access

# 7. Check status
sudo systemctl status face-access
```

## Configuration

Edit `/home/pi/rp3_face_access/config/production.yaml`:

```yaml
# IMPORTANT: Change the shared secret!
ble:
  shared_secret: "YOUR_SECURE_RANDOM_STRING_HERE"

# Adjust GPIO pins for your hardware
lock:
  gpio_pin: 17      # Relay control
  button_pin: 27    # Exit button (optional)
```

## Service Management

```bash
# Using manage.sh
./deploy/manage.sh start      # Start service
./deploy/manage.sh stop       # Stop service
./deploy/manage.sh restart    # Restart service
./deploy/manage.sh status     # Show status
./deploy/manage.sh logs       # Live logs
./deploy/manage.sh health     # Health check
./deploy/manage.sh backup     # Backup data

# Using systemctl directly
sudo systemctl start face-access
sudo systemctl stop face-access
sudo systemctl restart face-access
sudo systemctl status face-access
sudo journalctl -u face-access -f
```

## Features

### Automatic Startup
Service starts automatically on boot via systemd.

### Watchdog
- Systemd monitors the service every 60 seconds
- Automatic restart if service becomes unresponsive
- Up to 5 restarts per minute, then stops

### Error Recovery
- Camera: auto-reopens if connection lost
- BLE: auto-restarts on errors
- Recognition loop: continues after individual frame errors
- Exponential backoff on repeated failures

### Logging
- Console: INFO level
- File: DEBUG level with rotation (10MB × 5 files)
- Errors: separate error log
- Location: `/home/pi/rp3_face_access/logs/`

### Security
- Systemd sandboxing enabled
- HMAC authentication for BLE commands
- Read-only filesystem protection

## Monitoring

### Health Check
```bash
./deploy/healthcheck.sh
# Returns: OK, WARNING, or CRITICAL
```

### Cron Jobs (optional)
```bash
# Install cron jobs for maintenance
sudo crontab -u pi /home/pi/rp3_face_access/deploy/cron-jobs
```

This sets up:
- Weekly log cleanup
- Daily database backup
- Weekly database optimization

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u face-access -n 50 --no-pager

# Test manually
./deploy/manage.sh test
```

### Camera issues
```bash
# Check camera
ls -la /dev/video*
v4l2-ctl --list-devices
```

### GPIO permission denied
```bash
sudo usermod -a -G gpio pi
# Logout and login again
```

### BLE not advertising
```bash
# Check Bluetooth
sudo systemctl status bluetooth
bluetoothctl show

# Enable experimental features
sudo nano /etc/bluetooth/main.conf
# Add: ExperimentalFeatures = true
sudo systemctl restart bluetooth
```

### Database issues
```bash
# Check integrity
sqlite3 /home/pi/rp3_face_access/data/access_control.db "PRAGMA integrity_check;"

# Vacuum (optimize)
sqlite3 /home/pi/rp3_face_access/data/access_control.db "VACUUM;"
```

## Backup & Restore

### Backup
```bash
./deploy/manage.sh backup
# Creates: /home/pi/backups/face_access_YYYYMMDD_HHMMSS.tar.gz
```

### Restore
```bash
cd /home/pi/rp3_face_access
tar -xzf /home/pi/backups/face_access_BACKUP.tar.gz
sudo systemctl restart face-access
```

## Hardware Connections

### GPIO Pinout (BCM)
| Function | GPIO | Physical Pin |
|----------|------|--------------|
| Lock Relay | 17 | 11 |
| Exit Button | 27 | 13 |
| GND | - | 6, 9, 14, etc. |

### Wiring
```
Lock Relay:
  GPIO 17 ──── Relay IN
  5V ──────── Relay VCC
  GND ─────── Relay GND

Exit Button (active low):
  GPIO 27 ───┬─── Button ─── GND
             │
        (internal pull-up)
```

## Performance Tuning

For better performance on Raspberry Pi 3:

```yaml
# config/production.yaml
face:
  detector_scale_factor: 1.2  # Less accurate but faster
  quality_min_face_size: 100  # Ignore small faces

camera:
  fps: 10  # Reduce if CPU too high
```

## Updating

```bash
# Stop service
sudo systemctl stop face-access

# Update files
cd /home/pi/rp3_face_access
git pull  # or copy new files

# Update dependencies (if needed)
./venv/bin/pip install -r requirements.txt

# Start service
sudo systemctl start face-access
```
