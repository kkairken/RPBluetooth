"""
Base camera interface for unified frame capture.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np


class CameraBase(ABC):
    """Abstract base class for camera sources."""

    @abstractmethod
    def open(self) -> bool:
        """
        Open camera connection.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a single frame from camera.

        Returns:
            Tuple of (success, frame) where frame is BGR numpy array or None
        """
        pass

    @abstractmethod
    def release(self):
        """Release camera resources."""
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """
        Check if camera is opened.

        Returns:
            True if camera is opened, False otherwise
        """
        pass

    def get_resolution(self) -> Tuple[int, int]:
        """
        Get current camera resolution.

        Returns:
            Tuple of (width, height)
        """
        return (640, 480)  # Default resolution
