# User TODO List

Steps to complete before deploying the system.

## 1. Download ONNX Model ⚠️ REQUIRED

The face recognition model is NOT included. You must download it separately.

### Option A: InsightFace Models (Recommended)

Visit: https://github.com/deepinsight/insightface/tree/master/model_zoo

Recommended models:
- **buffalo_l** (112x112, 512-dim): Good accuracy, medium speed
- **buffalo_m** (112x112, 256-dim): Medium accuracy, faster
- **buffalo_s** (112x112, 128-dim): Lower accuracy, fastest

Download steps:
```bash
# Example for buffalo_m
cd models/
wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip
unzip buffalo_m.zip
# Find the .onnx file and rename if needed
mv buffalo_m/w600k_r50.onnx insightface_medium.onnx
```

### Option B: ONNX Model Zoo

Visit: https://github.com/onnx/models

Look for face recognition models compatible with:
- Input: [1, 3, 112, 112] float32
- Output: [1, 512] float32 (or similar embedding dimension)

### Update Configuration

After downloading, update `config/usb_config.yaml`:
```yaml
face:
  onnx_model_path: "models/YOUR_MODEL_NAME.onnx"
  embedding_dim: 512  # Match your model's output dimension
```

## 2. Configure System Settings

### Edit Configuration File

```bash
cp config/usb_config.yaml config/my_config.yaml
nano config/my_config.yaml
```

### Required Changes

1. **Model Path** (see step 1)
   ```yaml
   face:
     onnx_model_path: "models/insightface_medium.onnx"
   ```

2. **Shared Secret** ⚠️ SECURITY
   ```yaml
   ble:
     shared_secret: "CHANGE_THIS_TO_STRONG_SECRET_KEY_12345"
   ```
   Generate with: `python -c "import os; print(os.urandom(32).hex())"`

3. **Camera Settings**
   ```yaml
   camera:
     type: usb  # or rtsp
     device_id: 0  # Try 0, 1, 2 if camera not detected
     # For RTSP:
     # rtsp_url: "rtsp://192.168.1.100:554/stream"
   ```

4. **Lock Settings**
   ```yaml
   lock:
     gpio_pin: 17  # Adjust based on your wiring
     mock_mode: true  # Set false when GPIO is connected
   ```

5. **Admin Mode**
   ```yaml
   access:
     admin_mode_enabled: true  # Keep true for development
     # In production: false, use GPIO button
   ```

## 3. Install Dependencies

### On Raspberry Pi

```bash
# System dependencies
sudo apt update
sudo apt install -y python3-pip python3-venv libopencv-dev python3-opencv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### Verify Installation

```bash
# Test imports
python -c "import cv2, numpy, onnxruntime; print('OK')"

# Test camera
python -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera FAIL'); cap.release()"

# Test model loading
python -c "import onnxruntime as ort; session = ort.InferenceSession('models/insightface_medium.onnx'); print('Model OK')"
```

## 4. Hardware Setup

### Camera Connection

**USB Camera:**
- Plug into USB port
- Check with: `v4l2-ctl --list-devices`
- Update `device_id` in config if needed

**RTSP Camera:**
- Connect to same network as Raspberry Pi
- Configure static IP on camera
- Update `rtsp_url` in config
- Test with: `ffplay rtsp://YOUR_CAMERA_IP:554/stream`

### GPIO Relay Wiring

**If using real GPIO (not mock mode):**

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

**Test GPIO:**
```python
import gpiod
chip = gpiod.Chip('gpiochip0')
line = chip.get_line(17)
line.request(consumer='test', type=gpiod.LINE_REQ_DIR_OUT)
line.set_value(1)  # Should activate relay
import time
time.sleep(2)
line.set_value(0)  # Should deactivate
line.release()
chip.close()
```

## 5. Initial Testing

### Test 1: Run System

```bash
source venv/bin/activate
python src/main.py --config config/my_config.yaml --log-level DEBUG
```

Check for errors in logs.

### Test 2: Register Test Employee

Prepare 2-3 test photos of the same person (JPEG format).

```bash
python tools/ble_client_simulator.py \
  --action register \
  --employee-id TEST001 \
  --display-name "Test User" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos test_photo1.jpg test_photo2.jpg test_photo3.jpg \
  --shared-secret "YOUR_SECRET_FROM_CONFIG"
```

### Test 3: Verify Registration

```bash
sqlite3 data/access_control.db "SELECT * FROM employees;"
sqlite3 data/access_control.db "SELECT COUNT(*) FROM embeddings WHERE employee_id='TEST001';"
```

Should show employee and embeddings.

### Test 4: Test Recognition

- Start system
- Position face in front of camera
- System should recognize and unlock (or log in mock mode)
- Check logs: `tail -f face_access.log`

## 6. Production Deployment

### Security Hardening

1. **Disable Admin Mode**
   ```yaml
   access:
     admin_mode_enabled: false
   ```

2. **Set up GPIO Admin Button** (optional)
   ```yaml
   access:
     admin_gpio_pin: 23  # Connect button between GPIO 23 and GND
   ```

3. **File Permissions**
   ```bash
   chmod 600 config/my_config.yaml
   chmod 700 data/
   ```

4. **Firewall** (if networked)
   ```bash
   sudo apt install ufw
   sudo ufw default deny incoming
   sudo ufw enable
   ```

### Systemd Service

Create `/etc/systemd/system/face-access.service`:

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

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-access
sudo systemctl start face-access
sudo systemctl status face-access
```

### Log Rotation

Create `/etc/logrotate.d/face-access`:

```
/home/pi/rp3_face_access/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

### Database Backup

Add to crontab (`crontab -e`):

```cron
# Backup database daily at 2 AM
0 2 * * * cp /home/pi/rp3_face_access/data/access_control.db /home/pi/rp3_face_access/data/backup_$(date +\%Y\%m\%d).db
```

## 7. Mobile App Development (Optional)

If developing a mobile app for BLE registration:

1. Read `API_REFERENCE.md` for BLE protocol
2. Implement BLE GATT client
3. Implement HMAC signing
4. Implement photo chunking
5. Test with BLE simulator first
6. Test with actual Raspberry Pi

## 8. Monitoring and Maintenance

### Regular Checks

- [ ] Review logs weekly
- [ ] Check disk space
- [ ] Verify camera functionality
- [ ] Test lock mechanism
- [ ] Backup database
- [ ] Review audit logs for anomalies

### Troubleshooting

See `README.md` "Troubleshooting" section for common issues.

## 9. Optimization (If Needed)

If performance is too slow:

1. **Reduce Camera Resolution**
   ```yaml
   camera:
     width: 320
     height: 240
   ```

2. **Lower Threshold** (if too many false rejections)
   ```yaml
   face:
     similarity_threshold: 0.5  # Lower = more lenient
   ```

3. **Use Smaller Model** (see step 1)

4. **Frame Skipping** (edit `main.py`)
   ```python
   frame_skip = 3  # Process every 3rd frame
   ```

## 10. Documentation

Keep these documents handy:

- [ ] `README.md` - Main documentation
- [ ] `QUICKSTART.md` - Quick setup
- [ ] `ARCHITECTURE.md` - Technical details
- [ ] `API_REFERENCE.md` - BLE API (for mobile dev)
- [ ] `INSTALL_OFFLINE.md` - Offline installation

## Checklist Summary

- [ ] Download ONNX model
- [ ] Configure `my_config.yaml`
- [ ] Change shared secret
- [ ] Install dependencies
- [ ] Connect camera
- [ ] Connect GPIO relay (or use mock)
- [ ] Test system startup
- [ ] Register test employee
- [ ] Test face recognition
- [ ] Set up systemd service
- [ ] Configure log rotation
- [ ] Set up database backup
- [ ] Harden security
- [ ] Document deployment

## Support

If you encounter issues:

1. Check logs: `face_access.log`
2. Run tests: `pytest tests/`
3. Review `README.md` troubleshooting
4. Check GitHub issues
5. Open new issue with logs and config (redact secrets!)

---

**Good luck with your deployment!** 🚀
