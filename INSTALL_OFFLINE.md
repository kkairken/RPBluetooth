# Offline Installation Guide

Complete guide for installing the face access control system on Raspberry Pi 3 without internet connection.

## Prerequisites

- Raspberry Pi 3 (Model B or B+) with Raspberry Pi OS
- MicroSD card (16GB+) with fresh OS installation
- USB drive for transferring files
- Development machine with internet access

## Step 1: Prepare on Development Machine (With Internet)

### 1.1 Download Project and Dependencies

```bash
# Clone/download project
git clone https://github.com/yourusername/rp3-face-access.git
cd rp3-face-access

# Create directory for offline packages
mkdir -p offline_packages

# Download all Python packages
pip download -r requirements.txt -d offline_packages/

# Download optional packages
pip download libgpiod -d offline_packages/
pip download bleak -d offline_packages/

# Download system packages (Debian/Ubuntu)
# Note: Match these to your Raspberry Pi OS version
mkdir -p offline_deb

# For Raspberry Pi OS Bullseye (example URLs - update as needed)
cd offline_deb
wget http://archive.raspberrypi.org/debian/pool/main/p/python3-opencv/python3-opencv_4.5.1_armhf.deb
wget http://archive.raspberrypi.org/debian/pool/main/libjpeg-turbo/libjpeg62-turbo_2.0.6_armhf.deb
# Add other necessary .deb files
cd ..
```

### 1.2 Download ONNX Model

```bash
# Download InsightFace ONNX model
# Example sources:
# - https://github.com/deepinsight/insightface
# - https://github.com/onnx/models

# Place model in models/ directory
mkdir -p models
# Download and place your model file:
# models/insightface_medium.onnx
```

### 1.3 Create Offline Package

```bash
# Create complete offline package
tar -czf rp3_face_access_offline.tar.gz \
  rp3_face_access/ \
  offline_packages/ \
  offline_deb/

# Copy to USB drive
cp rp3_face_access_offline.tar.gz /media/usb/
```

## Step 2: Install on Raspberry Pi (Offline)

### 2.1 Transfer Files

```bash
# Insert USB drive into Raspberry Pi
# Copy package to home directory
cd /home/pi
cp /media/usb/rp3_face_access_offline.tar.gz .
tar -xzf rp3_face_access_offline.tar.gz
```

### 2.2 Install System Dependencies

```bash
# Install .deb packages
cd offline_deb
sudo dpkg -i *.deb

# Fix any dependency issues
sudo apt --fix-broken install

# Verify installations
python3 --version  # Should be 3.10+
```

### 2.3 Install Python Packages

```bash
cd /home/pi/rp3_face_access

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages from offline cache
pip install --no-index --find-links=../offline_packages/ -r requirements.txt

# Verify installation
python -c "import cv2; print(cv2.__version__)"
python -c "import onnxruntime; print(onnxruntime.__version__)"
```

### 2.4 Configure System

```bash
# Copy config template
cp config/usb_config.yaml config/my_config.yaml

# Edit configuration
nano config/my_config.yaml
```

Required changes:
- Update `face.onnx_model_path` to point to your model
- Set `ble.shared_secret` to a secure value
- Configure camera settings
- Set `lock.mock_mode: true` for initial testing

### 2.5 Initialize Database

```bash
# Create data directory
mkdir -p data

# Database will be created on first run
```

### 2.6 Test Installation

```bash
# Run tests
python -m pytest tests/

# Test camera (USB)
python -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera FAIL'); cap.release()"

# Test model loading
python -c "import onnxruntime as ort; session = ort.InferenceSession('models/insightface_medium.onnx'); print('Model OK')"
```

## Step 3: Run System

### 3.1 Test Run

```bash
source venv/bin/activate
python src/main.py --config config/my_config.yaml --log-level DEBUG
```

### 3.2 Set Up Autostart (Optional)

Create systemd service:

```bash
sudo nano /etc/systemd/system/face-access.service
```

Service file content:
```ini
[Unit]
Description=Face Access Control System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rp3_face_access
Environment="PATH=/home/pi/rp3_face_access/venv/bin"
ExecStart=/home/pi/rp3_face_access/venv/bin/python src/main.py --config config/my_config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-access.service
sudo systemctl start face-access.service

# Check status
sudo systemctl status face-access.service

# View logs
sudo journalctl -u face-access.service -f
```

## Troubleshooting

### Missing System Libraries

If you get import errors, you may need additional libraries:

```bash
# On development machine, find dependencies
ldd /path/to/problematic_library.so

# Download required .deb packages
# Transfer to Raspberry Pi and install
```

### Python Package Conflicts

```bash
# Clear pip cache
rm -rf ~/.cache/pip

# Reinstall in clean environment
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links=../offline_packages/ -r requirements.txt
```

### Model Loading Issues

```bash
# Verify model file
ls -lh models/insightface_medium.onnx

# Test model loading
python -c "
import onnxruntime as ort
session = ort.InferenceSession('models/insightface_medium.onnx')
print('Input:', session.get_inputs()[0].name, session.get_inputs()[0].shape)
print('Output:', session.get_outputs()[0].name, session.get_outputs()[0].shape)
"
```

## Hardware Setup

### Camera Connection

**USB Camera:**
```bash
# List USB devices
lsusb

# Check video devices
ls -l /dev/video*

# Test with v4l-utils
v4l2-ctl --list-devices
```

**RTSP Camera:**
- Connect camera to same LAN as Raspberry Pi
- Configure static IP for camera
- Update `camera.rtsp_url` in config

### GPIO Relay

**Wiring (BCM pin 17):**
```
Raspberry Pi          Relay Module
-----------          ------------
GPIO 17     ------>  IN
5V          ------>  VCC
GND         ------>  GND
```

**Testing:**
```python
# Test GPIO (with libgpiod installed)
import gpiod
chip = gpiod.Chip('gpiochip0')
line = chip.get_line(17)
line.request(consumer='test', type=gpiod.LINE_REQ_DIR_OUT)
line.set_value(1)  # Activate
import time
time.sleep(2)
line.set_value(0)  # Deactivate
line.release()
chip.close()
```

## Security Hardening

After installation:

1. **Change Default Credentials:**
   ```bash
   # Update shared secret in config
   nano config/my_config.yaml
   # Set strong value for ble.shared_secret
   ```

2. **Disable Unnecessary Services:**
   ```bash
   sudo systemctl disable bluetooth  # If not using BLE
   sudo systemctl disable wifi        # If using wired connection
   ```

3. **Firewall:**
   ```bash
   sudo apt install ufw
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw enable
   ```

4. **File Permissions:**
   ```bash
   chmod 600 config/my_config.yaml
   chmod 700 data/
   ```

## Backup and Recovery

### Backup Database

```bash
# Create backup
cp data/access_control.db data/access_control.db.backup.$(date +%Y%m%d)

# Or use SQLite backup
sqlite3 data/access_control.db ".backup 'backup.db'"
```

### SD Card Image

```bash
# On development machine, create SD card image
sudo dd if=/dev/sdX of=rp3_face_access.img bs=4M status=progress
gzip rp3_face_access.img
```

## Performance Optimization

For better performance on Raspberry Pi 3:

1. **Overclock (Carefully):**
   ```bash
   sudo nano /boot/config.txt
   # Add:
   # over_voltage=2
   # arm_freq=1350
   ```

2. **Disable Desktop:**
   ```bash
   sudo systemctl set-default multi-user.target
   ```

3. **Reduce Camera Resolution:**
   ```yaml
   # In config:
   camera:
     width: 320
     height: 240
   ```

4. **Use Lighter Detector:**
   ```yaml
   face:
     detector_type: opencv_haar  # Faster than mediapipe
   ```

## Support

For offline support:
- Check logs: `face_access.log`
- Review test results
- Verify hardware connections
- Consult README.md troubleshooting section
