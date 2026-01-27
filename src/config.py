"""
Configuration module for offline face access control system.
Loads YAML config and provides type-safe access to settings.
"""
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Camera configuration."""
    type: str  # 'usb', 'rtsp', or 'picamera'
    device_id: Optional[int] = None  # for USB
    rtsp_url: Optional[str] = None  # for RTSP
    width: int = 640
    height: int = 480
    fps: int = 15
    rtsp_transport: str = "tcp"  # tcp or udp
    # Pi Camera specific
    rotation: int = 0  # 0, 90, 180, 270
    hflip: bool = False
    vflip: bool = False


@dataclass
class FaceConfig:
    """Face recognition configuration."""
    onnx_model_path: str
    detector_type: str = "opencv_haar"  # opencv_haar, mediapipe, or none
    detector_scale_factor: float = 1.1
    detector_min_neighbors: int = 5
    detector_min_face_size: Tuple[int, int] = (60, 60)
    embedding_dim: int = 512
    similarity_threshold: float = 0.6  # cosine similarity threshold
    quality_min_face_size: int = 80
    quality_blur_threshold: float = 100.0
    align_enabled: bool = True


@dataclass
class BLEConfig:
    """BLE GATT server configuration."""
    device_name: str = "RP3_FaceAccess"
    service_uuid: str = "12345678-1234-5678-1234-56789abcdef0"
    command_char_uuid: str = "12345678-1234-5678-1234-56789abcdef1"
    response_char_uuid: str = "12345678-1234-5678-1234-56789abcdef2"
    photo_chunk_size: int = 512
    max_photo_size: int = 5 * 1024 * 1024  # 5 MB
    shared_secret: Optional[str] = None
    hmac_enabled: bool = True
    use_real_ble: bool = False  # Set to true to use real BlueZ BLE server


@dataclass
class AccessConfig:
    """Access control configuration."""
    admin_mode_enabled: bool = False
    admin_gpio_pin: Optional[int] = None
    unlock_duration_sec: float = 3.0
    cooldown_sec: float = 0.5  # Reduced from 2.0 for faster recognition
    max_attempts_per_minute: int = 30  # Increased to allow faster attempts
    granted_lockout_sec: float = 10.0  # Reduced from 30.0 for faster re-recognition


@dataclass
class LockConfig:
    """Lock GPIO configuration (using libgpiod)."""
    gpio_pin: int = 17
    gpio_chip: str = "gpiochip0"
    active_high: bool = True
    mock_mode: bool = False
    # Exit button configuration
    button_pin: Optional[int] = None  # GPIO pin for exit button (None = disabled)
    button_active_low: bool = True    # True if button connects to GND (internal pull-up)
    button_debounce_ms: int = 50      # Debounce time in milliseconds


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "data/access_control.db"


@dataclass
class SystemConfig:
    """Main system configuration."""
    camera: CameraConfig
    face: FaceConfig
    ble: BLEConfig
    access: AccessConfig
    lock: LockConfig
    database: DatabaseConfig
    log_level: str = "INFO"


def load_config(config_path: str) -> SystemConfig:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to YAML config file

    Returns:
        SystemConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)

    try:
        # Parse camera config
        camera_data = data.get('camera', {})
        camera = CameraConfig(
            type=camera_data.get('type', 'usb'),
            device_id=camera_data.get('device_id'),
            rtsp_url=camera_data.get('rtsp_url'),
            width=camera_data.get('width', 640),
            height=camera_data.get('height', 480),
            fps=camera_data.get('fps', 15),
            rtsp_transport=camera_data.get('rtsp_transport', 'tcp'),
            rotation=camera_data.get('rotation', 0),
            hflip=camera_data.get('hflip', False),
            vflip=camera_data.get('vflip', False)
        )

        # Parse face config
        face_data = data.get('face', {})
        face = FaceConfig(
            onnx_model_path=face_data.get('onnx_model_path'),
            detector_type=face_data.get('detector_type', 'opencv_haar'),
            detector_scale_factor=face_data.get('detector_scale_factor', 1.1),
            detector_min_neighbors=face_data.get('detector_min_neighbors', 5),
            detector_min_face_size=tuple(face_data.get('detector_min_face_size', [60, 60])),
            embedding_dim=face_data.get('embedding_dim', 512),
            similarity_threshold=face_data.get('similarity_threshold', 0.6),
            quality_min_face_size=face_data.get('quality_min_face_size', 80),
            quality_blur_threshold=face_data.get('quality_blur_threshold', 100.0),
            align_enabled=face_data.get('align_enabled', True)
        )

        if not face.onnx_model_path:
            raise ValueError("face.onnx_model_path is required")

        # Parse BLE config
        ble_data = data.get('ble', {})
        ble = BLEConfig(
            device_name=ble_data.get('device_name', 'RP3_FaceAccess'),
            service_uuid=ble_data.get('service_uuid', '12345678-1234-5678-1234-56789abcdef0'),
            command_char_uuid=ble_data.get('command_char_uuid', '12345678-1234-5678-1234-56789abcdef1'),
            response_char_uuid=ble_data.get('response_char_uuid', '12345678-1234-5678-1234-56789abcdef2'),
            photo_chunk_size=ble_data.get('photo_chunk_size', 512),
            max_photo_size=ble_data.get('max_photo_size', 5 * 1024 * 1024),
            shared_secret=ble_data.get('shared_secret'),
            hmac_enabled=ble_data.get('hmac_enabled', True),
            use_real_ble=ble_data.get('use_real_ble', False)
        )

        # Parse access config
        access_data = data.get('access', {})
        access = AccessConfig(
            admin_mode_enabled=access_data.get('admin_mode_enabled', False),
            admin_gpio_pin=access_data.get('admin_gpio_pin'),
            unlock_duration_sec=access_data.get('unlock_duration_sec', 3.0),
            cooldown_sec=access_data.get('cooldown_sec', 0.5),
            max_attempts_per_minute=access_data.get('max_attempts_per_minute', 30),
            granted_lockout_sec=access_data.get('granted_lockout_sec', 10.0)
        )

        # Parse lock config
        lock_data = data.get('lock', {})
        lock = LockConfig(
            gpio_pin=lock_data.get('gpio_pin', 17),
            gpio_chip=lock_data.get('gpio_chip', 'gpiochip0'),
            active_high=lock_data.get('active_high', True),
            mock_mode=lock_data.get('mock_mode', False),
            button_pin=lock_data.get('button_pin'),
            button_active_low=lock_data.get('button_active_low', True),
            button_debounce_ms=lock_data.get('button_debounce_ms', 50)
        )

        # Parse database config
        db_data = data.get('database', {})
        database = DatabaseConfig(
            path=db_data.get('path', 'data/access_control.db')
        )

        return SystemConfig(
            camera=camera,
            face=face,
            ble=ble,
            access=access,
            lock=lock,
            database=database,
            log_level=data.get('log_level', 'INFO')
        )

    except Exception as e:
        raise ValueError(f"Invalid configuration: {e}")
