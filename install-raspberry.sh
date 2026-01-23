#!/bin/bash
# Automatic installation script for Raspberry Pi
# Installs all dependencies for the face access control system

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_step() {
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        print_warning "This doesn't appear to be a Raspberry Pi"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        print_success "Detected Raspberry Pi"
    fi
}

# Check Python version
check_python_version() {
    print_step "Checking Python version"

    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    python_major=$(echo $python_version | cut -d. -f1)
    python_minor=$(echo $python_version | cut -d. -f2)

    echo "Python version: $python_version"

    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 10 ]); then
        print_error "Python 3.10+ required, but found $python_version"
        print_warning "Please upgrade to Raspberry Pi OS Bookworm or newer"
        exit 1
    else
        print_success "Python version OK"
    fi
}

# Update system
update_system() {
    print_step "Updating system packages"
    sudo apt update
    sudo apt upgrade -y
    print_success "System updated"
}

# Install system packages
install_system_packages() {
    print_step "Installing system packages"

    echo "This will install the following categories:"
    echo "  - Python development tools"
    echo "  - Computer vision libraries (OpenCV)"
    echo "  - Bluetooth and BLE support (BlueZ)"
    echo "  - GPIO support (libgpiod)"
    echo "  - Image processing libraries"
    echo ""

    # Read packages from file (one per line, skip comments)
    packages=$(grep -v '^#' system-packages.txt | grep -v '^[[:space:]]*$' | tr '\n' ' ')

    echo "Installing packages..."
    sudo apt install -y $packages

    print_success "System packages installed"
}

# Setup GPIO permissions
setup_gpio_permissions() {
    print_step "Setting up GPIO permissions"

    # Add user to gpio group
    sudo usermod -a -G gpio $USER

    # Check if added
    if groups $USER | grep -q gpio; then
        print_success "User added to gpio group"
        print_warning "You need to REBOOT for GPIO permissions to take effect"
    else
        print_error "Failed to add user to gpio group"
    fi
}

# Setup Bluetooth permissions
setup_bluetooth_permissions() {
    print_step "Setting up Bluetooth permissions"

    # Add user to bluetooth group
    sudo usermod -a -G bluetooth $USER

    # Enable Bluetooth service
    sudo systemctl enable bluetooth
    sudo systemctl start bluetooth

    # Check status
    if systemctl is-active --quiet bluetooth; then
        print_success "Bluetooth service is running"
    else
        print_warning "Bluetooth service is not running"
    fi
}

# Create virtual environment
create_venv() {
    print_step "Creating Python virtual environment"

    if [ -d "venv" ]; then
        print_warning "Virtual environment already exists"
        read -p "Recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf venv
            python3 -m venv venv
            print_success "Virtual environment recreated"
        fi
    else
        python3 -m venv venv
        print_success "Virtual environment created"
    fi
}

# Install Python packages
install_python_packages() {
    print_step "Installing Python packages"

    # Activate virtual environment
    source venv/bin/activate

    # Upgrade pip
    echo "Upgrading pip..."
    pip install --upgrade pip setuptools wheel

    # Install requirements
    echo "Installing Python dependencies..."
    echo "This may take 10-15 minutes on Raspberry Pi 3..."

    # Try to use system packages for opencv, dbus, gi
    export PIP_NO_BINARY=opencv-python

    pip install -r requirements-raspberry.txt

    print_success "Python packages installed"

    # Verify critical imports
    echo ""
    echo "Verifying installations..."
    python3 << 'EOF'
import sys

packages_to_check = [
    ("numpy", "NumPy"),
    ("cv2", "OpenCV"),
    ("PIL", "Pillow"),
    ("yaml", "PyYAML"),
    ("onnxruntime", "ONNX Runtime"),
    ("pytest", "pytest"),
]

optional_packages = [
    ("dbus", "dbus-python (for BLE server)"),
    ("gi", "PyGObject (for BLE server)"),
    ("bleak", "bleak (for BLE client)"),
]

print("Required packages:")
all_ok = True
for module, name in packages_to_check:
    try:
        __import__(module)
        print(f"  ✅ {name}")
    except ImportError:
        print(f"  ❌ {name}")
        all_ok = False

print("\nOptional packages:")
for module, name in optional_packages:
    try:
        __import__(module)
        print(f"  ✅ {name}")
    except ImportError:
        print(f"  ⚠️  {name} - not installed (optional)")

if not all_ok:
    print("\n❌ Some required packages failed to import!")
    sys.exit(1)
else:
    print("\n✅ All required packages imported successfully!")
EOF

    if [ $? -eq 0 ]; then
        print_success "Package verification passed"
    else
        print_error "Package verification failed"
        exit 1
    fi
}

# Create directories
create_directories() {
    print_step "Creating project directories"

    mkdir -p data
    mkdir -p models
    mkdir -p logs
    mkdir -p photos

    print_success "Directories created"
}

# Test hardware
test_hardware() {
    print_step "Testing hardware"

    # Test camera
    echo "Testing camera..."
    if v4l2-ctl --list-devices &>/dev/null; then
        v4l2-ctl --list-devices
        print_success "Camera devices found"
    else
        print_warning "No camera devices detected"
    fi

    # Test GPIO
    echo ""
    echo "Testing GPIO..."
    if gpiodetect &>/dev/null; then
        gpiodetect
        print_success "GPIO chip detected"
    else
        print_warning "GPIO chip not detected (may need reboot)"
    fi

    # Test Bluetooth
    echo ""
    echo "Testing Bluetooth..."
    if hciconfig &>/dev/null; then
        hciconfig
        print_success "Bluetooth adapter found"
    else
        print_warning "Bluetooth adapter not detected"
    fi
}

# Show next steps
show_next_steps() {
    print_step "Installation Complete!"

    echo ""
    echo "✅ System packages installed"
    echo "✅ Python virtual environment created"
    echo "✅ Python dependencies installed"
    echo "✅ Directories created"
    echo ""
    echo "⚠️  IMPORTANT: You need to REBOOT for permissions to take effect:"
    echo "   sudo reboot"
    echo ""
    echo "After reboot, follow these steps:"
    echo ""
    echo "1. Download ONNX model:"
    echo "   See TODO_USER.md section 1"
    echo ""
    echo "2. Configure system:"
    echo "   cp config/usb_config.yaml config/my_config.yaml"
    echo "   nano config/my_config.yaml"
    echo "   # Update: onnx_model_path, shared_secret, camera settings"
    echo ""
    echo "3. Test the system:"
    echo "   source venv/bin/activate"
    echo "   python src/main.py --config config/my_config.yaml --log-level DEBUG"
    echo ""
    echo "4. For BLE support, use:"
    echo "   cp config/ble_config.yaml config/my_ble_config.yaml"
    echo "   # Update shared_secret and set use_real_ble: true"
    echo "   sudo venv/bin/python src/main.py --config config/my_ble_config.yaml"
    echo ""
    echo "📚 Documentation:"
    echo "   - RASPBERRY_PI_GUIDE.md - Detailed setup guide"
    echo "   - DEPLOY_QUICK.md - Quick deployment"
    echo "   - BLE_SETUP_GUIDE.md - BLE server setup"
    echo ""
}

# Main installation flow
main() {
    echo ""
    echo "=================================================="
    echo "  Face Access Control System - Raspberry Pi"
    echo "  Installation Script"
    echo "=================================================="
    echo ""

    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_error "Do not run this script as root (sudo)"
        print_warning "Run as normal user: ./install-raspberry.sh"
        exit 1
    fi

    # Pre-flight checks
    check_raspberry_pi
    check_python_version

    # Ask for confirmation
    echo ""
    echo "This script will:"
    echo "  - Update system packages"
    echo "  - Install system dependencies (~500MB)"
    echo "  - Create Python virtual environment"
    echo "  - Install Python packages (~300MB)"
    echo "  - Setup GPIO and Bluetooth permissions"
    echo ""
    read -p "Continue with installation? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi

    # Installation steps
    update_system
    install_system_packages
    setup_gpio_permissions
    setup_bluetooth_permissions
    create_venv
    install_python_packages
    create_directories

    # Optional hardware tests
    echo ""
    read -p "Test hardware (camera, GPIO, Bluetooth)? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_hardware
    fi

    # Show next steps
    show_next_steps

    echo ""
    echo "🎉 Installation completed successfully!"
    echo ""
    read -p "Reboot now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo reboot
    fi
}

# Run main function
main
