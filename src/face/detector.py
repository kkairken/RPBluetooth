"""
Face detection module.
Supports multiple detector types: OpenCV Haar Cascade, MediaPipe, or custom.
"""
import cv2
import logging
import numpy as np
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class FaceDetector:
    """Face detector wrapper supporting multiple backends."""

    def __init__(
        self,
        detector_type: str = "opencv_haar",
        scale_factor: float = 1.1,
        min_neighbors: int = 5,
        min_face_size: Tuple[int, int] = (60, 60)
    ):
        """
        Initialize face detector.

        Args:
            detector_type: Type of detector ('opencv_haar', 'mediapipe', or 'none')
            scale_factor: Scale factor for opencv_haar
            min_neighbors: Minimum neighbors for opencv_haar
            min_face_size: Minimum face size (width, height)
        """
        self.detector_type = detector_type.lower()
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.min_face_size = min_face_size
        self.detector = None

        self._init_detector()

    def _init_detector(self):
        """Initialize the selected detector."""
        if self.detector_type == "opencv_haar":
            self._init_opencv_haar()
        elif self.detector_type == "mediapipe":
            self._init_mediapipe()
        elif self.detector_type == "none":
            logger.warning("No face detector enabled")
        else:
            raise ValueError(f"Unknown detector type: {self.detector_type}")

    def _init_opencv_haar(self):
        """Initialize OpenCV Haar Cascade detector."""
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.detector = cv2.CascadeClassifier(cascade_path)

            if self.detector.empty():
                raise RuntimeError("Failed to load Haar Cascade")

            logger.info("OpenCV Haar Cascade detector initialized")

        except Exception as e:
            logger.error(f"Failed to initialize OpenCV Haar detector: {e}")
            raise

    def _init_mediapipe(self):
        """Initialize MediaPipe face detection."""
        try:
            import mediapipe as mp
            self.mp_face_detection = mp.solutions.face_detection
            self.detector = self.mp_face_detection.FaceDetection(
                model_selection=0,  # 0 for short-range (< 2m), 1 for full-range
                min_detection_confidence=0.5
            )
            logger.info("MediaPipe face detector initialized")

        except ImportError:
            logger.error("MediaPipe not installed. Install with: pip install mediapipe")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe detector: {e}")
            raise

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces in a frame.

        Args:
            frame: BGR image as numpy array

        Returns:
            List of bounding boxes as (x, y, w, h) tuples
        """
        if self.detector_type == "opencv_haar":
            return self._detect_opencv_haar(frame)
        elif self.detector_type == "mediapipe":
            return self._detect_mediapipe(frame)
        elif self.detector_type == "none":
            # Return full frame as single "face"
            h, w = frame.shape[:2]
            return [(0, 0, w, h)]
        else:
            return []

    def _detect_opencv_haar(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces using OpenCV Haar Cascade."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=self.min_face_size,
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]

    def _detect_mediapipe(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces using MediaPipe."""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.detector.process(rgb_frame)

        if not results.detections:
            return []

        h, w = frame.shape[:2]
        faces = []

        for detection in results.detections:
            bbox = detection.location_data.relative_bounding_box
            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)

            # Clamp to frame boundaries
            x = max(0, x)
            y = max(0, y)
            width = min(width, w - x)
            height = min(height, h - y)

            if width >= self.min_face_size[0] and height >= self.min_face_size[1]:
                faces.append((x, y, width, height))

        return faces

    def detect_largest(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect and return the largest face in the frame.

        Args:
            frame: BGR image as numpy array

        Returns:
            Largest face bounding box (x, y, w, h) or None
        """
        faces = self.detect(frame)

        if not faces:
            return None

        # Return the largest face by area
        largest = max(faces, key=lambda f: f[2] * f[3])
        return largest
