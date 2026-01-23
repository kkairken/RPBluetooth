"""
Face photo quality checker.
Validates face photos for registration quality.
"""
import cv2
import numpy as np
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class FaceQualityChecker:
    """Checks face photo quality for registration."""

    def __init__(
        self,
        min_face_size: int = 80,
        blur_threshold: float = 100.0
    ):
        """
        Initialize quality checker.

        Args:
            min_face_size: Minimum face dimension (width or height)
            blur_threshold: Laplacian variance threshold (lower = more blurry)
        """
        self.min_face_size = min_face_size
        self.blur_threshold = blur_threshold

    def check_photo_quality(
        self,
        frame: np.ndarray,
        faces: list
    ) -> Tuple[bool, str]:
        """
        Check if photo meets quality requirements.

        Args:
            frame: BGR image
            faces: List of detected face bounding boxes [(x, y, w, h), ...]

        Returns:
            Tuple of (is_valid, reason)
        """
        # Check: exactly one face
        if len(faces) == 0:
            return False, "No face detected"

        if len(faces) > 1:
            return False, f"Multiple faces detected ({len(faces)})"

        # Check: face size
        x, y, w, h = faces[0]
        if w < self.min_face_size or h < self.min_face_size:
            return False, f"Face too small ({w}x{h}, minimum {self.min_face_size}x{self.min_face_size})"

        # Check: blur level
        blur_score = self._compute_blur_score(frame, faces[0])
        if blur_score < self.blur_threshold:
            return False, f"Image too blurry (score: {blur_score:.1f}, threshold: {self.blur_threshold})"

        return True, "OK"

    def _compute_blur_score(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int]
    ) -> float:
        """
        Compute blur score using Laplacian variance.

        Args:
            frame: BGR image
            bbox: Face bounding box (x, y, w, h)

        Returns:
            Blur score (higher = sharper)
        """
        try:
            x, y, w, h = bbox

            # Extract face region
            face_region = frame[y:y+h, x:x+w]

            # Convert to grayscale
            gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)

            # Compute Laplacian variance
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            variance = laplacian.var()

            return float(variance)

        except Exception as e:
            logger.error(f"Blur computation error: {e}")
            return 0.0

    def check_face_alignment(
        self,
        bbox: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int]
    ) -> Tuple[bool, str]:
        """
        Check if face is well-aligned in the frame.

        Args:
            bbox: Face bounding box (x, y, w, h)
            frame_shape: Frame shape (height, width)

        Returns:
            Tuple of (is_valid, reason)
        """
        x, y, w, h = bbox
        frame_h, frame_w = frame_shape

        # Check if face is too close to edges
        margin = 10
        if x < margin or y < margin:
            return False, "Face too close to frame edge"

        if x + w > frame_w - margin or y + h > frame_h - margin:
            return False, "Face too close to frame edge"

        # Check aspect ratio (should be roughly square for frontal faces)
        aspect_ratio = w / h if h > 0 else 0
        if aspect_ratio < 0.7 or aspect_ratio > 1.3:
            return False, f"Face aspect ratio unusual ({aspect_ratio:.2f})"

        return True, "OK"

    def validate_for_registration(
        self,
        frame: np.ndarray,
        faces: list
    ) -> Tuple[bool, str]:
        """
        Comprehensive validation for registration photo.

        Args:
            frame: BGR image
            faces: List of detected face bounding boxes

        Returns:
            Tuple of (is_valid, reason)
        """
        # Check photo quality
        valid, reason = self.check_photo_quality(frame, faces)
        if not valid:
            return False, reason

        # Check face alignment
        valid, reason = self.check_face_alignment(faces[0], frame.shape[:2])
        if not valid:
            return False, reason

        return True, "Photo validated"
