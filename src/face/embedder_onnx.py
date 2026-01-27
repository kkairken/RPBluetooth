"""
Face embedding module using ONNX Runtime.
Computes face embeddings using InsightFace or similar models.
"""
import onnxruntime as ort
import cv2
import numpy as np
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class FaceEmbedder:
    """Face embedding generator using ONNX models."""

    def __init__(
        self,
        model_path: str,
        embedding_dim: int = 512,
        input_size: Tuple[int, int] = (112, 112)
    ):
        """
        Initialize face embedder.

        Args:
            model_path: Path to ONNX model file
            embedding_dim: Expected embedding dimension
            input_size: Model input size (width, height)
        """
        self.model_path = model_path
        self.embedding_dim = embedding_dim
        self.input_size = input_size
        self.session: Optional[ort.InferenceSession] = None

        self._load_model()

    def _load_model(self):
        """Load ONNX model."""
        try:
            if not Path(self.model_path).exists():
                raise FileNotFoundError(f"Model file not found: {self.model_path}")

            # Create ONNX Runtime session with CPU provider
            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            # Optimize for Raspberry Pi - use all available cores
            import os
            num_cores = os.cpu_count() or 4
            session_options.intra_op_num_threads = num_cores
            session_options.inter_op_num_threads = num_cores
            session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            logger.info(f"ONNX Runtime using {num_cores} threads")

            providers = ['CPUExecutionProvider']

            self.session = ort.InferenceSession(
                self.model_path,
                sess_options=session_options,
                providers=providers
            )

            # Get model input/output info
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name

            input_shape = self.session.get_inputs()[0].shape
            output_shape = self.session.get_outputs()[0].shape

            logger.info(
                f"ONNX model loaded: {self.model_path}\n"
                f"  Input: {self.input_name} {input_shape}\n"
                f"  Output: {self.output_name} {output_shape}"
            )

        except Exception as e:
            logger.error(f"Failed to load ONNX model: {e}")
            raise

    def preprocess(self, face_image: np.ndarray) -> np.ndarray:
        """
        Preprocess face image for model input.

        Args:
            face_image: BGR face image

        Returns:
            Preprocessed tensor [1, 3, H, W]
        """
        # Resize if needed
        if face_image.shape[:2] != self.input_size[::-1]:
            face_image = cv2.resize(face_image, self.input_size, interpolation=cv2.INTER_LINEAR)

        # Convert BGR to RGB
        face_rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Normalize to [-1, 1] (standard for InsightFace models)
        face_normalized = (face_rgb.astype(np.float32) - 127.5) / 127.5

        # Transpose to CHW format
        face_transposed = face_normalized.transpose(2, 0, 1)

        # Add batch dimension
        face_batch = np.expand_dims(face_transposed, axis=0)

        return face_batch.astype(np.float32)

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
            input_tensor = self.preprocess(face_image)

            # Run inference
            outputs = self.session.run([self.output_name], {self.input_name: input_tensor})

            embedding = outputs[0].flatten()

            # Normalize embedding (L2 normalization)
            embedding = embedding / np.linalg.norm(embedding)

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
