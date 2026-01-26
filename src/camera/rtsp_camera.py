"""
RTSP camera implementation using OpenCV or GStreamer.
Supports RTP/RTCP streaming from IP cameras.
"""
import cv2
import logging
from typing import Optional, Tuple
import numpy as np
from .base import CameraBase

logger = logging.getLogger(__name__)


class RTSPCamera(CameraBase):
    """RTSP/IP camera implementation."""

    def __init__(
        self,
        rtsp_url: str,
        transport: str = "tcp",
        width: int = 640,
        height: int = 480,
        reconnect_attempts: int = 3,
        buffer_flush_count: int = 5
    ):
        """
        Initialize RTSP camera.

        Args:
            rtsp_url: RTSP stream URL (e.g., rtsp://192.168.1.100:554/stream)
            transport: Transport protocol ('tcp' or 'udp')
            width: Desired frame width (for resizing)
            height: Desired frame height (for resizing)
            reconnect_attempts: Number of reconnection attempts
            buffer_flush_count: Number of frames to skip to get fresh frame
        """
        self.rtsp_url = rtsp_url
        self.transport = transport.lower()
        self.width = width
        self.height = height
        self.reconnect_attempts = reconnect_attempts
        self.buffer_flush_count = buffer_flush_count
        self.cap: Optional[cv2.VideoCapture] = None

    def _build_gstreamer_pipeline(self) -> str:
        """
        Build GStreamer pipeline for RTSP (optional, for better control).

        Returns:
            GStreamer pipeline string
        """
        # Example GStreamer pipeline for RTSP with TCP
        pipeline = (
            f"rtspsrc location={self.rtsp_url} protocols={self.transport} latency=0 ! "
            f"rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! "
            f"videoscale ! video/x-raw,width={self.width},height={self.height} ! "
            f"appsink"
        )
        return pipeline

    def open(self) -> bool:
        """
        Open RTSP camera stream.

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.reconnect_attempts):
            try:
                # Try opening with OpenCV
                # Set RTSP transport protocol via environment variable
                if self.transport == "tcp":
                    self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
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
                return True

            except Exception as e:
                logger.error(f"Error opening RTSP camera (attempt {attempt + 1}): {e}")

        logger.error(f"Failed to open RTSP camera after {self.reconnect_attempts} attempts")
        return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from RTSP stream.
        Flushes buffer to get the most recent frame.

        Returns:
            Tuple of (success, frame)
        """
        if not self.cap or not self.cap.isOpened():
            return False, None

        try:
            # Flush buffer by grabbing frames without decoding
            # This discards old buffered frames to get the latest
            for _ in range(self.buffer_flush_count):
                self.cap.grab()

            # Now retrieve the latest frame
            ret, frame = self.cap.retrieve()
            if not ret or frame is None:
                # Fallback to regular read
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logger.warning("Failed to read frame from RTSP stream")
                    return False, None

            # Resize if needed
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))

            return True, frame

        except Exception as e:
            logger.error(f"Error reading RTSP frame: {e}")
            return False, None

    def release(self):
        """Release RTSP camera resources."""
        if self.cap:
            self.cap.release()
            logger.info("RTSP camera released")

    def is_opened(self) -> bool:
        """Check if RTSP stream is opened."""
        return self.cap is not None and self.cap.isOpened()

    def get_resolution(self) -> Tuple[int, int]:
        """Get current stream resolution."""
        if self.cap and self.cap.isOpened():
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (width, height)
        return (self.width, self.height)
