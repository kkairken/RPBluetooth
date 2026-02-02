"""
Face embedding module using OpenCV DNN.
Alternative to ONNX Runtime for 32-bit ARM systems (Raspberry Pi 2, etc.)
"""
import cv2
import numpy as np
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class FaceEmbedderOpenCV:
    """Face embedding generator using OpenCV DNN backend."""

    def __init__(
        self,
        model_path: str,
        embedding_dim: int = 512,
        input_size: Tuple[int, int] = (112, 112),
        norm_mean: float = 127.5,
        norm_std: float = 127.5
    ):
        """
        Initialize face embedder with OpenCV DNN.

        Args:
            model_path: Path to ONNX model file
            embedding_dim: Expected embedding dimension
            input_size: Model input size (width, height)
            norm_mean: Normalization mean (subtracted from pixel values)
            norm_std: Normalization std (divides centered pixel values)
        """
        self.model_path = model_path
        self.embedding_dim = embedding_dim
        self.input_size = input_size
        self.norm_mean = norm_mean
        self.norm_std = norm_std
        self.net = None

        self._load_model()

    def _load_model(self):
        """Load ONNX model using OpenCV DNN."""
        try:
            if not Path(self.model_path).exists():
                raise FileNotFoundError(f"Model file not found: {self.model_path}")

            # Load ONNX model with OpenCV DNN
            self.net = cv2.dnn.readNetFromONNX(self.model_path)

            # Use CPU backend (works on 32-bit ARM)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

            logger.info(
                f"OpenCV DNN model loaded: {self.model_path}\n"
                f"  Input size: {self.input_size}\n"
                f"  Embedding dim: {self.embedding_dim}"
            )

        except Exception as e:
            logger.error(f"Failed to load ONNX model with OpenCV DNN: {e}")
            raise

    def preprocess(self, face_image: np.ndarray) -> np.ndarray:
        """
        Preprocess face image for model input.

        Args:
            face_image: BGR face image

        Returns:
            Preprocessed blob for OpenCV DNN
        """
        # Resize if needed
        if face_image.shape[:2] != self.input_size[::-1]:
            face_image = cv2.resize(face_image, self.input_size, interpolation=cv2.INTER_LINEAR)

        # Convert BGR to RGB
        face_rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Create blob: (image - mean) * scalefactor
        blob = cv2.dnn.blobFromImage(
            face_rgb,
            scalefactor=1.0 / self.norm_std,
            size=self.input_size,
            mean=(self.norm_mean, self.norm_mean, self.norm_mean),
            swapRB=False,  # Already RGB
            crop=False
        )

        return blob

    def compute_embedding(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        """
        Compute face embedding.

        Args:
            face_image: Aligned face image (BGR)

        Returns:
            Embedding vector as numpy array or None on error
        """
        try:
            # Preprocess
            blob = self.preprocess(face_image)

            # Run inference
            self.net.setInput(blob)
            output = self.net.forward()

            embedding = output.flatten()

            # Normalize embedding (L2 normalization)
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm

            if len(embedding) != self.embedding_dim:
                logger.warning(
                    f"Unexpected embedding dimension: {len(embedding)} (expected {self.embedding_dim})"
                )

            return embedding.astype(np.float32)

        except Exception as e:
            logger.error(f"Embedding computation failed: {e}")
            return None

    def compute_embeddings_batch(self, face_images: list) -> list:
        """
        Compute embeddings for multiple faces.

        Args:
            face_images: List of aligned face images

        Returns:
            List of embedding vectors
        """
        embeddings = []

        for face_image in face_images:
            embedding = self.compute_embedding(face_image)
            if embedding is not None:
                embeddings.append(embedding)

        return embeddings
