"""
Raspberry Pi Camera Module implementation using picamera.
For Raspberry Pi with CSI camera interface.
"""
import logging
from typing import Optional, Tuple
import numpy as np
from .base import CameraBase

logger = logging.getLogger(__name__)

# Try to import picamera (only available on Raspberry Pi)
try:
    import picamera
    import picamera.array
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera not available (not running on Raspberry Pi?)")


class PiCamera(CameraBase):
    """Raspberry Pi Camera Module implementation."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
        rotation: int = 0,
        hflip: bool = False,
        vflip: bool = False
    ):
        """
        Initialize Pi Camera.

        Args:
            width: Frame width
            height: Frame height
            fps: Frames per second
            rotation: Rotation in degrees (0, 90, 180, 270)
            hflip: Horizontal flip
            vflip: Vertical flip
        """
        if not PICAMERA_AVAILABLE:
            raise RuntimeError("picamera library not available")

        self.width = width
        self.height = height
        self.fps = fps
        self.rotation = rotation
        self.hflip = hflip
        self.vflip = vflip
        self.camera = None
        self.raw_capture = None

    def open(self) -> bool:
        """
        Open Pi Camera.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.camera = picamera.PiCamera()
            self.camera.resolution = (self.width, self.height)
            self.camera.framerate = self.fps
            self.camera.rotation = self.rotation
            self.camera.hflip = self.hflip
            self.camera.vflip = self.vflip

            # Allow camera to warm up
            import time
            time.sleep(0.5)

            # Create raw capture for continuous capture
            self.raw_capture = picamera.array.PiRGBArray(
                self.camera,
                size=(self.width, self.height)
            )

            logger.info(
                f"Pi Camera opened: {self.width}x{self.height} @ {self.fps}fps"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to open Pi Camera: {e}")
            if self.camera:
                self.camera.close()
                self.camera = None
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from Pi Camera.

        Returns:
            Tuple of (success, frame in BGR format)
        """
        if not self.camera or not self.raw_capture:
            return False, None

        try:
            # Clear the stream for next frame
            self.raw_capture.truncate(0)
            self.raw_capture.seek(0)

            # Capture frame
            self.camera.capture(
                self.raw_capture,
                format='bgr',
                use_video_port=True
            )

            frame = self.raw_capture.array

            if frame is None or frame.size == 0:
                return False, None

            return True, frame

        except Exception as e:
            logger.error(f"Error reading Pi Camera frame: {e}")
            return False, None

    def release(self):
        """Release Pi Camera resources."""
        if self.camera:
            try:
                self.camera.close()
            except Exception as e:
                logger.error(f"Error closing Pi Camera: {e}")
            self.camera = None
            self.raw_capture = None
            logger.info("Pi Camera released")

    def is_opened(self) -> bool:
        """Check if Pi Camera is opened."""
        return self.camera is not None and not self.camera.closed

    def get_resolution(self) -> Tuple[int, int]:
        """Get current resolution."""
        if self.camera:
            return self.camera.resolution
        return (self.width, self.height)
