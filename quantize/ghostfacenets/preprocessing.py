#!/usr/bin/env python3
"""
preprocessing.py - Preprocessing for GhostFaceNets models.

Defaults:
- Input size: 112x112
- Color: BGR
- Normalization: (pixel/255 - 0.5) / 0.5 -> range [-1, 1]
- Layout: NHWC
"""

import numpy as np
import cv2
from typing import Tuple, List, Union
from pathlib import Path


class GhostFaceNetsPreprocessor:
    def __init__(
        self,
        input_size: Tuple[int, int] = (112, 112),
        input_mean: float = 127.5,
        input_std: float = 127.5,
        color_format: str = "BGR",
    ):
        self.input_size = input_size
        self.input_mean = input_mean
        self.input_std = input_std
        self.color_format = color_format.upper()
        assert self.color_format in ["RGB", "BGR"], f"Invalid color format: {color_format}"

    def __call__(self, image: np.ndarray) -> np.ndarray:
        return self.preprocess(image)

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        if image.shape[:2] != (self.input_size[1], self.input_size[0]):
            image = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)

        if self.color_format == "RGB":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        image = image.astype(np.float32)
        image = (image - self.input_mean) / self.input_std
        image = np.expand_dims(image, axis=0)
        return image

    def preprocess_batch(self, images: List[np.ndarray]) -> np.ndarray:
        processed = [self.preprocess(img) for img in images]
        return np.concatenate(processed, axis=0)

    def load_and_preprocess(self, image_path: Union[str, Path]) -> np.ndarray:
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot load image: {image_path}")
        return self.preprocess(image)


def normalize_embedding(embedding: np.ndarray, axis: int = 1) -> np.ndarray:
    if embedding.ndim == 1:
        norm = np.linalg.norm(embedding)
        return embedding / (norm + 1e-10)
    norm = np.linalg.norm(embedding, axis=axis, keepdims=True)
    return embedding / (norm + 1e-10)


def cosine_similarity_batch(emb1: np.ndarray, emb2: np.ndarray) -> np.ndarray:
    numerator = np.sum(emb1 * emb2, axis=1)
    denom = np.linalg.norm(emb1, axis=1) * np.linalg.norm(emb2, axis=1)
    return numerator / (denom + 1e-10)
