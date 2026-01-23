"""
USB camera implementation using OpenCV VideoCapture.
"""
import cv2
import logging
from typing import Optional, Tuple
import numpy as np
from .base import CameraBase

logger = logging.getLogger(__name__)


class USBCamera(CameraBase):
    """USB/UVC camera implementation."""

    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480, fps: int = 15):
        """
        Initialize USB camera.

        Args:
            device_id: Camera device ID (default 0)
            width: Frame width
            height: Frame height
            fps: Frames per second
        """
        self.device_id = device_id
        self.width = width
        self.height = height
        self.fps = fps
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        """
        Open USB camera.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.cap = cv2.VideoCapture(self.device_id)

            if not self.cap.isOpened():
                logger.error(f"Failed to open USB camera {self.device_id}")
                return False

            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

            # Verify actual settings
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self.cap.get(cv2.CAP_PROP_FPS))

            logger.info(
                f"USB camera {self.device_id} opened: "
                f"{actual_width}x{actual_height} @ {actual_fps} FPS"
            )

            return True

        except Exception as e:
            logger.error(f"Error opening USB camera: {e}")
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from USB camera.

        Returns:
            Tuple of (success, frame)
        """
        if not self.cap or not self.cap.isOpened():
            return False, None

        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.warning("Failed to read frame from USB camera")
                return False, None

            return True, frame

        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return False, None

    def release(self):
        """Release USB camera resources."""
        if self.cap:
            self.cap.release()
            logger.info(f"USB camera {self.device_id} released")

    def is_opened(self) -> bool:
        """Check if camera is opened."""
        return self.cap is not None and self.cap.isOpened()

    def get_resolution(self) -> Tuple[int, int]:
        """Get current camera resolution."""
        if self.cap and self.cap.isOpened():
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (width, height)
        return (self.width, self.height)
