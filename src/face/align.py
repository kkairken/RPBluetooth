"""
Face alignment module.
Performs simple face alignment based on bounding box.
"""
import cv2
import numpy as np
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class FaceAligner:
    """Simple face alignment based on crop and resize."""

    def __init__(self, output_size: Tuple[int, int] = (112, 112)):
        """
        Initialize face aligner.

        Args:
            output_size: Target face size (width, height)
        """
        self.output_size = output_size

    def align(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        margin: float = 0.2
    ) -> Optional[np.ndarray]:
        """
        Align face by cropping and resizing.

        Args:
            frame: Input BGR image
            bbox: Face bounding box (x, y, w, h)
            margin: Margin to add around face (fraction of bbox size)

        Returns:
            Aligned face image or None if invalid
        """
        try:
            x, y, w, h = bbox
            frame_h, frame_w = frame.shape[:2]

            # Add margin
            margin_w = int(w * margin)
            margin_h = int(h * margin)

            x1 = max(0, x - margin_w)
            y1 = max(0, y - margin_h)
            x2 = min(frame_w, x + w + margin_w)
            y2 = min(frame_h, y + h + margin_h)

            # Crop face region
            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size == 0:
                logger.warning("Empty face crop")
                return None

            # Resize to target size
            aligned = cv2.resize(face_crop, self.output_size, interpolation=cv2.INTER_LINEAR)

            return aligned

        except Exception as e:
            logger.error(f"Face alignment error: {e}")
            return None

    def align_multiple(
        self,
        frame: np.ndarray,
        bboxes: list,
        margin: float = 0.2
    ) -> list:
        """
        Align multiple faces.

        Args:
            frame: Input BGR image
            bboxes: List of face bounding boxes
            margin: Margin to add around faces

        Returns:
            List of aligned face images
        """
        aligned_faces = []

        for bbox in bboxes:
            aligned = self.align(frame, bbox, margin)
            if aligned is not None:
                aligned_faces.append(aligned)

        return aligned_faces
