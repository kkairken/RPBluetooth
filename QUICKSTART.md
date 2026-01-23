# Quick Start Guide

Get the face access control system running in 15 minutes.

## Prerequisites

- Raspberry Pi 3 with Raspberry Pi OS
- USB webcam or RTSP IP camera
- Python 3.10+
- InsightFace ONNX model file

## 5-Step Setup

### 1. Install Dependencies (5 min)

```bash
# Update system
sudo apt update && sudo apt install -y python3-pip python3-venv libopencv-dev python3-opencv

# Create project directory
cd /home/pi
mkdir -p rp3_face_access && cd rp3_face_access

# Install project
python3 -m venv venv
source venv/bin/activate
pip install numpy opencv-python onnxruntime PyYAML pytest
```

### 2. Setup Project Structure (2 min)

```bash
# Create directories
mkdir -p src config models data

# Copy all .py files to src/
# Copy config .yaml files to config/
# Place ONNX model in models/
```

### 3. Configure (3 min)

Edit `config/usb_config.yaml`:

```yaml
camera:
  type: usb
  device_id: 0

face:
  onnx_model_path: "models/insightface_medium.onnx"
  similarity_threshold: 0.6

access:
  admin_mode_enabled: true

lock:
  mock_mode: true  # Test without GPIO
```

### 4. Test Camera (2 min)

```bash
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print('Camera OK' if ret else 'Camera FAIL')
cap.release()
"
```

### 5. Run System (3 min)

```bash
source venv/bin/activate
python src/main.py --config config/usb_config.yaml
```

## Quick Test Workflow

### Test 1: Register Employee

```bash
# Create test photos (or use your own)
python tools/ble_client_simulator.py \
  --action register \
  --employee-id TEST001 \
  --display-name "Test User" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos test_photo1.jpg test_photo2.jpg
```

### Test 2: Verify Recognition

- Position face in front of camera
- System should recognize and grant access
- Check logs: `tail -f face_access.log`

### Test 3: Check Database

```bash
sqlite3 data/access_control.db "SELECT * FROM employees;"
sqlite3 data/access_control.db "SELECT COUNT(*) FROM embeddings;"
sqlite3 data/access_control.db "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 5;"
```

## Common Issues

### Issue: "Camera not found"
```bash
# Fix: Check camera connection
v4l2-ctl --list-devices
# Or try different device_id: 1, 2, etc.
```

### Issue: "Model file not found"
```bash
# Fix: Verify model path
ls -l models/*.onnx
# Update path in config
```

### Issue: "No face detected"
```bash
# Fix: Check lighting and camera angle
# Reduce detector_min_face_size in config
```

### Issue: "Low similarity score"
```bash
# Fix: Lower similarity_threshold
# Use more/better quality photos for registration
```

## Next Steps

1. **Production Setup:**
   - Set `lock.mock_mode: false`
   - Connect GPIO relay
   - Disable `admin_mode_enabled`
   - Add GPIO button for admin mode

2. **Security:**
   - Change `ble.shared_secret`
   - Set up autostart service
   - Configure firewall

3. **Optimization:**
   - Tune similarity threshold
   - Adjust camera settings
   - Optimize for your lighting conditions

## Monitoring

```bash
# Watch logs
tail -f face_access.log

# Check system status
sqlite3 data/access_control.db "
SELECT
  (SELECT COUNT(*) FROM employees WHERE is_active=1) as active_employees,
  (SELECT COUNT(*) FROM embeddings) as total_embeddings,
  (SELECT COUNT(*) FROM audit_log WHERE timestamp >= datetime('now', '-1 hour')) as recent_attempts;
"

# Export logs
python src/main.py --config config/usb_config.yaml --export-logs logs.json
```

## Tips

- **Lighting:** Good lighting is critical for face recognition
- **Camera Position:** Place camera at eye level, 0.5-1m from face
- **Registration Photos:** Use 3-5 photos from different angles
- **Threshold Tuning:** Start with 0.6, adjust based on false positive/negative rates
- **Performance:** Expect 1-3 FPS on Raspberry Pi 3 with full pipeline

## Getting Help

1. Check logs: `face_access.log`
2. Run tests: `python -m pytest tests/`
3. Verify config: `python -c "from config import load_config; c = load_config('config/usb_config.yaml'); print('Config OK')"`
4. Review README.md troubleshooting section
