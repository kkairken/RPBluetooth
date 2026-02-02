#!/usr/bin/env python3
"""
preprocessing.py - Препроцессинг изображений для FaceNet (InceptionResNetV1)

FaceNet параметры:
- Input size: 160x160
- Color: RGB
- Normalization: (pixel - 127.5) / 128.0 -> range [-0.9961, 0.9961]
- Layout: NCHW (batch, channels, height, width)
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from pathlib import Path


class FaceNetPreprocessor:
    """Препроцессор изображений для FaceNet"""

    def __init__(
        self,
        input_size: Tuple[int, int] = (160, 160),
        input_mean: float = 127.5,
        input_std: float = 128.0,
        color_format: str = "RGB"
    ):
        """
        Args:
            input_size: размер входа (width, height)
            input_mean: среднее для нормализации
            input_std: std для нормализации
            color_format: RGB или BGR
        """
        self.input_size = input_size
        self.input_mean = input_mean
        self.input_std = input_std
        self.color_format = color_format.upper()

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Препроцессинг одного изображения

        Args:
            image: BGR изображение (H, W, 3) из OpenCV

        Returns:
            тензор (1, 3, 160, 160) float32
        """
        # Resize
        if image.shape[:2] != (self.input_size[1], self.input_size[0]):
            image = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)

        # BGR -> RGB
        if self.color_format == "RGB":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # float32
        image = image.astype(np.float32)

        # Normalize: (pixel - 127.5) / 128.0
        image = (image - self.input_mean) / self.input_std

        # HWC -> CHW
        image = image.transpose(2, 0, 1)

        # Add batch dimension
        image = np.expand_dims(image, axis=0)

        return image

    def preprocess_batch(self, images: List[np.ndarray]) -> np.ndarray:
        """
        Препроцессинг батча изображений

        Args:
            images: список BGR изображений

        Returns:
            тензор (N, 3, 160, 160) float32
        """
        tensors = [self.preprocess(img) for img in images]
        return np.concatenate(tensors, axis=0)

    def load_and_preprocess(self, image_path: str) -> Optional[np.ndarray]:
        """
        Загрузка и препроцессинг из файла

        Args:
            image_path: путь к изображению

        Returns:
            тензор (1, 3, 160, 160) или None
        """
        image = cv2.imread(image_path)
        if image is None:
            return None
        return self.preprocess(image)


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    """L2 нормализация эмбеддинга"""
    if embedding.ndim == 1:
        norm = np.linalg.norm(embedding)
        if norm > 0:
            return embedding / norm
        return embedding

    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    return embedding / norms


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Косинусное сходство между двумя эмбеддингами"""
    emb1_norm = normalize_embedding(emb1.flatten())
    emb2_norm = normalize_embedding(emb2.flatten())
    return float(np.dot(emb1_norm, emb2_norm))


def cosine_similarity_batch(emb1: np.ndarray, emb2: np.ndarray) -> np.ndarray:
    """
    Косинусное сходство для батча пар

    Args:
        emb1: (N, D) - первые эмбеддинги
        emb2: (N, D) - вторые эмбеддинги

    Returns:
        (N,) массив сходств
    """
    emb1_norm = normalize_embedding(emb1)
    emb2_norm = normalize_embedding(emb2)
    return np.sum(emb1_norm * emb2_norm, axis=1)
