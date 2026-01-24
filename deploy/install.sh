#!/bin/bash
#
# RP3 Face Access Control - Production Installation Script
# Run as: sudo ./install.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo ./install.sh)"
    exit 1
fi

# Configuration
INSTALL_DIR="/home/hseadmin/RPBluetooth"
SERVICE_NAME="face-access"
USER="hseadmin"
GROUP="hseadmin"

log_info "=========================================="
log_info "RP3 Face Access Control - Installation"
log_info "=========================================="

# 1. Install system dependencies
log_info "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-opencv \
    python3-libgpiod \
    libopencv-dev \
    libatlas-base-dev \
    libjpeg-dev \
    libpng-dev \
    bluetooth \
    bluez \
    libdbus-1-dev \
    libglib2.0-dev

# 2. Create installation directory
log_info "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/models"

# 3. Copy application files (if running from source directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

if [ -d "$SOURCE_DIR/src" ]; then
    log_info "Copying application files..."
    cp -r "$SOURCE_DIR/src" "$INSTALL_DIR/"
    cp -r "$SOURCE_DIR/config" "$INSTALL_DIR/"
    cp -r "$SOURCE_DIR/tools" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
fi

# 4. Create virtual environment
log_info "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"

# 5. Install Python dependencies
log_info "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel
"$INSTALL_DIR/venv/bin/pip" install \
    numpy \
    opencv-python-headless \
    onnxruntime \
    pyyaml \
    bleak \
    dbus-python \
    PyGObject \
    sdnotify

# 6. Set permissions
log_info "Setting permissions..."
chown -R "$USER:$GROUP" "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data"
chmod 700 "$INSTALL_DIR/logs"

# 7. Add user to required groups
log_info "Configuring user groups..."
usermod -a -G gpio "$USER" 2>/dev/null || true
usermod -a -G bluetooth "$USER" 2>/dev/null || true
usermod -a -G video "$USER" 2>/dev/null || true

# 8. Install systemd service
log_info "Installing systemd service..."
cp "$SCRIPT_DIR/face-access.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# 9. Configure Bluetooth
log_info "Configuring Bluetooth for BLE advertising..."
# Enable experimental features for BLE peripheral mode
if ! grep -q "ExperimentalFeatures" /etc/bluetooth/main.conf 2>/dev/null; then
    echo "" >> /etc/bluetooth/main.conf
    echo "[General]" >> /etc/bluetooth/main.conf
    echo "ExperimentalFeatures = true" >> /etc/bluetooth/main.conf
fi

# Restart Bluetooth
systemctl restart bluetooth

# 10. Create default config if not exists
if [ ! -f "$INSTALL_DIR/config/production.yaml" ]; then
    log_warn "No production.yaml found, copying template..."
    if [ -f "$INSTALL_DIR/config/usb_config.yaml" ]; then
        cp "$INSTALL_DIR/config/usb_config.yaml" "$INSTALL_DIR/config/production.yaml"
    fi
fi

# 11. Print summary
log_info "=========================================="
log_info "Installation complete!"
log_info "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy your ONNX model to: $INSTALL_DIR/models/"
echo "2. Edit config: $INSTALL_DIR/config/production.yaml"
echo "   - Set your shared_secret for BLE security"
echo "   - Verify GPIO pins for your hardware"
echo ""
echo "Commands:"
echo "  Start service:   sudo systemctl start $SERVICE_NAME"
echo "  Stop service:    sudo systemctl stop $SERVICE_NAME"
echo "  View status:     sudo systemctl status $SERVICE_NAME"
echo "  View logs:       sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Log files: $INSTALL_DIR/logs/"
echo ""
log_info "Reboot recommended to apply all changes"
