# Offline Face Access Control System for Raspberry Pi 3

Production-ready offline face recognition access control system designed for Raspberry Pi 3. Works completely offline without internet connection.

## Features

- **Offline Operation**: No internet or external API required
- **Face Recognition**: ONNX Runtime with InsightFace models
- **BLE Registration**: Employee registration via Bluetooth LE (GATT)
- **Multiple Cameras**: USB (UVC) and RTSP (IP camera) support
- **Security**: HMAC-SHA256 authentication for admin operations
- **Access Control**: Time-based access periods, rate limiting, audit logging
- **GPIO Lock Control**: Direct relay control with mock mode for testing

## Architecture

```
┌─────────────────┐
│  Mobile App     │
│  (iOS/Android)  │
└────────┬────────┘
         │ BLE
         │ (Employee Registration)
         ▼
┌─────────────────────────────────────────┐
│        Raspberry Pi 3                   │
│  ┌───────────────────────────────────┐  │
│  │   BLE GATT Server                 │  │
│  │   - HMAC Authentication           │  │
│  │   - Photo Chunking Protocol       │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │   Face Recognition Engine         │  │
│  │   - ONNX Runtime (CPU)            │  │
│  │   - Face Detection & Alignment    │  │
│  │   - Embedding & Matching          │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │   Access Control                  │  │
│  │   - Time Period Validation        │  │
│  │   - Rate Limiting                 │  │
│  │   - Audit Logging                 │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │   SQLite Database                 │  │
│  │   - Employees                     │  │
│  │   - Embeddings                    │  │
│  │   - Audit Log                     │  │
│  └───────────────────────────────────┘  │
└────────┬────────────────────┬───────────┘
         │                    │
         ▼                    ▼
    ┌────────┐          ┌─────────┐
    │ Camera │          │  Relay  │
    │USB/RTSP│          │  Lock   │
    └────────┘          └─────────┘
```

## Hardware Requirements

- **Raspberry Pi 3** (Model B or B+)
- **Camera**: USB webcam or RTSP IP camera
- **Relay Module**: For door lock control (GPIO)
- **MicroSD Card**: 16GB+ recommended
- **Power Supply**: 5V 2.5A

## Software Requirements

- Raspberry Pi OS (32-bit or 64-bit)
- Python 3.10+
- ONNX Runtime
- OpenCV
- BlueZ (for BLE)

## Installation

### 1. Prepare Raspberry Pi

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
    python3-pip \
    python3-venv \
    libopencv-dev \
    python3-opencv \
    libatlas-base-dev \
    libjpeg-dev \
    libopenblas-dev \
    bluez \
    bluetooth \
    libbluetooth-dev \
    gpiod \
    libgpiod2 \
    python3-libgpiod

# Enable Bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Set up GPIO permissions
sudo usermod -a -G gpio $USER

# Reboot for permissions to take effect
sudo reboot
```

### 2. Install Project

```bash
# Clone or copy project to Raspberry Pi
cd /home/pi
cp -r /path/to/rp3_face_access .
cd rp3_face_access

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Download ONNX Model

Download InsightFace ONNX model:

```bash
# Create models directory
mkdir -p models

# Download model (example - adjust URL based on your model source)
# For InsightFace models, see: https://github.com/deepinsight/insightface
# Place your .onnx model file in models/ directory

# Example model structure:
# models/
#   └── insightface_medium.onnx
```

**Note**: Update `onnx_model_path` in your config file to match the model filename.

### 4. Configure System

```bash
# Copy and edit configuration
cp config/usb_config.yaml config/my_config.yaml

# Edit configuration
nano config/my_config.yaml
```

Key configuration options:

- **camera.type**: `usb` or `rtsp`
- **face.onnx_model_path**: Path to ONNX model
- **face.similarity_threshold**: Recognition threshold (0.5-0.7 recommended)
- **ble.shared_secret**: Change this for security
- **access.admin_mode_enabled**: Set to `true` for registration
- **lock.mock_mode**: Set to `true` for testing without GPIO

### 5. Initialize Database

```bash
# Database will be created automatically on first run
mkdir -p data
```

## Usage

### Running the System

#### USB Camera Mode

```bash
source venv/bin/activate
python src/main.py --config config/usb_config.yaml
```

#### RTSP Camera Mode

```bash
source venv/bin/activate
python src/main.py --config config/rtsp_config.yaml
```

#### Export Audit Logs

```bash
python src/main.py --config config/my_config.yaml --export-logs logs_export.json
```

### Employee Registration (via BLE Client Simulator)

For testing without mobile app:

```bash
# Register employee with photos
python tools/ble_client_simulator.py \
  --action register \
  --employee-id EMP001 \
  --display-name "John Doe" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2025-12-31T23:59:59Z" \
  --photos photo1.jpg photo2.jpg photo3.jpg \
  --shared-secret "change_this_secret_key_in_production"

# Deactivate employee
python tools/ble_client_simulator.py \
  --action deactivate \
  --employee-id EMP001 \
  --shared-secret "change_this_secret_key_in_production"

# Update access period
python tools/ble_client_simulator.py \
  --action update-period \
  --employee-id EMP001 \
  --access-start "2026-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --shared-secret "change_this_secret_key_in_production"

# Get system status
python tools/ble_client_simulator.py \
  --action status
```

**Note**: The simulator only prints commands. For actual BLE communication, integrate with a BLE library like `bleak` or develop a mobile app.

## BLE Protocol

### GATT Service

- **Service UUID**: `12345678-1234-5678-1234-56789abcdef0`
- **Command Characteristic**: `12345678-1234-5678-1234-56789abcdef1` (Write)
- **Response Characteristic**: `12345678-1234-5678-1234-56789abcdef2` (Notify)

### Commands

#### BEGIN_UPSERT
```json
{
  "command": "BEGIN_UPSERT",
  "employee_id": "EMP001",
  "display_name": "John Doe",
  "access_start": "2025-01-01T00:00:00Z",
  "access_end": "2025-12-31T23:59:59Z",
  "num_photos": 3,
  "nonce": "1234567890_abc123",
  "hmac": "signature_here"
}
```

#### PHOTO_CHUNK
```json
{
  "command": "PHOTO_CHUNK",
  "chunk_index": 0,
  "total_chunks": 10,
  "data": "base64_encoded_chunk",
  "is_last": false,
  "sha256": "hash_of_complete_photo"
}
```

#### END_UPSERT
```json
{
  "command": "END_UPSERT"
}
```

#### UPDATE_PERIOD
```json
{
  "command": "UPDATE_PERIOD",
  "employee_id": "EMP001",
  "access_start": "2026-01-01T00:00:00Z",
  "access_end": "2026-12-31T23:59:59Z",
  "nonce": "1234567890_xyz789",
  "hmac": "signature_here"
}
```

#### DEACTIVATE
```json
{
  "command": "DEACTIVATE",
  "employee_id": "EMP001",
  "nonce": "1234567890_def456",
  "hmac": "signature_here"
}
```

#### GET_STATUS
```json
{
  "command": "GET_STATUS"
}
```

### HMAC Authentication

Commands requiring authentication must include:
- **nonce**: Timestamp + random string (format: `{timestamp}_{random}`)
- **hmac**: HMAC-SHA256 signature of command (excluding `hmac` field)

Example HMAC computation (Python):
```python
import json
import hmac
import hashlib
import time
import os

command = {
    "command": "DEACTIVATE",
    "employee_id": "EMP001",
    "nonce": f"{int(time.time())}_{os.urandom(8).hex()}"
}

message = json.dumps(command, sort_keys=True).encode('utf-8')
signature = hmac.new(
    b"shared_secret",
    message,
    hashlib.sha256
).hexdigest()

command['hmac'] = signature
```

## Testing

Run unit tests:

```bash
source venv/bin/activate

# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_db.py

# Or use unittest
python -m unittest discover tests
```

## Security Considerations

1. **Change Default Secret**: Update `ble.shared_secret` in config
2. **Admin Mode**: Disable `admin_mode_enabled` in production, use GPIO button
3. **Physical Security**: Secure Raspberry Pi and relay physically
4. **Database Backup**: Regularly backup `data/access_control.db`
5. **Logs**: Monitor `face_access.log` for suspicious activity
6. **BLE Security**: Use secure pairing for BLE connections
7. **Network Isolation**: Keep system on isolated network (no internet)

## Troubleshooting

### Camera Issues

```bash
# Test USB camera
v4l2-ctl --list-devices

# Test RTSP stream
ffplay rtsp://192.168.1.100:554/stream
```

### GPIO Issues

```bash
# Check GPIO chip
gpiodetect

# Test specific GPIO line
gpioget gpiochip0 17
gpioset gpiochip0 17=1  # Should activate relay

# Check permissions
ls -l /dev/gpiochip0

# Add user to gpio group if permission denied
sudo usermod -a -G gpio $USER
sudo reboot

# Run in mock mode for testing
# Set lock.mock_mode: true in config
```

See detailed GPIO troubleshooting: `docs/GPIO_SETUP.md`

### BLE Issues

```bash
# Check Bluetooth status
sudo systemctl status bluetooth

# Scan for devices
sudo hcitool dev

# Reset Bluetooth
sudo systemctl restart bluetooth
```

### Model Loading Issues

- Ensure ONNX model path is correct
- Check model format compatibility with onnxruntime
- Verify model input/output dimensions

### Performance Issues

- Reduce camera resolution in config
- Increase `frame_skip` in recognition loop
- Use smaller ONNX model
- Optimize detector settings

## Directory Structure

```
rp3_face_access/
├── README.md
├── requirements.txt
├── config/
│   ├── usb_config.yaml
│   └── rtsp_config.yaml
├── src/
│   ├── config.py
│   ├── db.py
│   ├── ble_server.py
│   ├── access_control.py
│   ├── lock.py
│   ├── main.py
│   ├── camera/
│   │   ├── base.py
│   │   ├── usb_camera.py
│   │   └── rtsp_camera.py
│   └── face/
│       ├── detector.py
│       ├── align.py
│       ├── embedder_onnx.py
│       ├── matcher.py
│       └── quality.py
├── tests/
│   ├── test_db.py
│   ├── test_access_control.py
│   ├── test_hmac.py
│   └── test_protocol.py
├── tools/
│   └── ble_client_simulator.py
├── models/
│   └── (place ONNX models here)
└── data/
    └── (database created here)
```

## Offline Installation

For systems without internet:

1. **On Development Machine** (with internet):
```bash
# Download dependencies
pip download -r requirements.txt -d packages/

# Copy entire project to USB drive
```

2. **On Raspberry Pi** (offline):
```bash
# Install from local packages
pip install --no-index --find-links=packages/ -r requirements.txt
```

## Performance Tips

- **Raspberry Pi 3**: Expect 1-3 FPS for full pipeline
- **Optimize**: Reduce camera resolution, use smaller models
- **Cooling**: Use heatsinks or fan for continuous operation
- **Power**: Use quality power supply (2.5A+)

## Contributing

This is a production-ready template. Customize for your specific use case:

- Replace BLE mock with real BlueZ integration
- Add face liveness detection
- Implement face anti-spoofing
- Add remote monitoring (optional)
- Enhance UI/LED indicators

## Documentation

Complete documentation available:

- **README.md** (this file) - Main documentation and setup
- **QUICKSTART.md** - 15-minute quick start guide
- **INSTALL_OFFLINE.md** - Air-gapped installation instructions
- **ARCHITECTURE.md** - Technical architecture and design
- **API_REFERENCE.md** - BLE API for mobile developers
- **docs/GPIO_SETUP.md** - GPIO setup and troubleshooting (libgpiod)
- **MIGRATION_GPIOD.md** - Migration from RPi.GPIO to libgpiod
- **CHANGELOG.md** - Version history and changes
- **CONTRIBUTING.md** - Development guidelines
- **TODO_USER.md** - Pre-deployment checklist

## License

MIT License - See LICENSE file for details

## Acknowledgments

- InsightFace for face recognition models
- ONNX Runtime for efficient inference
- OpenCV for computer vision
- Raspberry Pi Foundation

## Support

For issues and questions:
- Check logs: `face_access.log`
- Review configuration
- Test components individually
- Consult troubleshooting section

---

**Note**: This system is designed for access control in controlled environments. Always comply with local privacy and data protection regulations.
