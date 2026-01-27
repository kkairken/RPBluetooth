"""
RTSP camera implementation using OpenCV.
Uses background thread for continuous frame capture to avoid blocking.
"""
import cv2
import logging
import threading
import time
from typing import Optional, Tuple
import numpy as np
from .base import CameraBase

logger = logging.getLogger(__name__)


class RTSPCamera(CameraBase):
    """RTSP/IP camera implementation with threaded capture."""

    def __init__(
        self,
        rtsp_url: str,
        transport: str = "tcp",
        width: int = 640,
        height: int = 480,
        reconnect_attempts: int = 3,
        buffer_flush_count: int = 2
    ):
        """
        Initialize RTSP camera.

        Args:
            rtsp_url: RTSP stream URL (e.g., rtsp://192.168.1.100:554/stream)
            transport: Transport protocol ('tcp' or 'udp')
            width: Desired frame width (for resizing)
            height: Desired frame height (for resizing)
            reconnect_attempts: Number of reconnection attempts
            buffer_flush_count: Not used (kept for compatibility)
        """
        self.rtsp_url = rtsp_url
        self.transport = transport.lower()
        self.width = width
        self.height = height
        self.reconnect_attempts = reconnect_attempts
        self.cap: Optional[cv2.VideoCapture] = None

        # Threading for continuous capture
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._last_frame_time = 0.0

    def open(self) -> bool:
        """
        Open RTSP camera stream and start capture thread.

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.reconnect_attempts):
            try:
                # Open with OpenCV + FFMPEG for TCP transport
                if self.transport == "tcp":
                    self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                else:
                    self.cap = cv2.VideoCapture(self.rtsp_url)

                if not self.cap.isOpened():
                    logger.warning(
                        f"RTSP camera open attempt {attempt + 1}/{self.reconnect_attempts} failed"
                    )
                    continue

                # Test reading a frame
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logger.warning("RTSP stream opened but no frames received")
                    self.cap.release()
                    continue

                logger.info(
                    f"RTSP camera opened: {self.rtsp_url} "
                    f"(transport: {self.transport}, resolution: {frame.shape[1]}x{frame.shape[0]})"
                )

                # Start background capture thread
                self._running = True
                self._thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._thread.start()

                # Wait for first frame
                if self._frame_ready.wait(timeout=5.0):
                    return True
                else:
                    logger.error("Timeout waiting for first frame")
                    self._running = False
                    self.cap.release()
                    continue

            except Exception as e:
                logger.error(f"Error opening RTSP camera (attempt {attempt + 1}): {e}")

        logger.error(f"Failed to open RTSP camera after {self.reconnect_attempts} attempts")
        return False

    def _capture_loop(self):
        """Background thread for continuous frame capture."""
        logger.debug("RTSP capture thread started")
        consecutive_errors = 0
        max_errors = 30

        while self._running:
            try:
                if not self.cap or not self.cap.isOpened():
                    logger.warning("Camera disconnected, stopping capture")
                    break

                ret, frame = self.cap.read()
                if not ret or frame is None:
                    consecutive_errors += 1
                    if consecutive_errors >= max_errors:
                        logger.error("Too many frame errors, stopping capture")
                        break
                    time.sleep(0.01)
                    continue

                consecutive_errors = 0

                # Resize if needed
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    frame = cv2.resize(frame, (self.width, self.height))

                # Store latest frame
                with self._frame_lock:
                    self._frame = frame
                    self._last_frame_time = time.time()

                self._frame_ready.set()

            except Exception as e:
                logger.error(f"Capture thread error: {e}")
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    break
                time.sleep(0.1)

        logger.debug("RTSP capture thread stopped")
        self._running = False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Get the latest captured frame (non-blocking).

        Returns:
            Tuple of (success, frame)
        """
        if not self._running:
            return False, None

        with self._frame_lock:
            if self._frame is None:
                return False, None
            # Return a copy to avoid race conditions
            return True, self._frame.copy()

    def release(self):
        """Release RTSP camera resources."""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self.cap:
            self.cap.release()
            logger.info("RTSP camera released")

    def is_opened(self) -> bool:
        """Check if RTSP stream is opened and capturing."""
        return self._running and self.cap is not None and self.cap.isOpened()

    def get_resolution(self) -> Tuple[int, int]:
        """Get current stream resolution."""
        return (self.width, self.height)

    def get_frame_age(self) -> float:
        """Get age of current frame in seconds."""
        if self._last_frame_time == 0:
            return float('inf')
        return time.time() - self._last_frame_time
