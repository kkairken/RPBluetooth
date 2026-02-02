#!/usr/bin/env python3
"""
preprocessing.py - Единый модуль препроцессинга для InsightFace

КРИТИЧЕСКИ ВАЖНО: Использовать ИДЕНТИЧНЫЙ препроцессинг для baseline и квантованных моделей!

InsightFace стандартный препроцессинг:
- Input size: 112x112
- Color: RGB (NOT BGR!)
- Range: [-1, 1] (pixel / 127.5 - 1.0)
- Layout: NCHW
- No mean/std subtraction (только линейная нормализация)
"""

import numpy as np
import cv2
from typing import Tuple, List, Optional, Union
from pathlib import Path


class InsightFacePreprocessor:
    """
    Стандартный препроцессор для InsightFace recognition моделей
    
    Параметры по умолчанию соответствуют buffalo_l / ArcFace:
    - input_size: (112, 112)
    - color_format: "RGB"
    - input_range: [-1, 1]
    """
    
    def __init__(
        self,
        input_size: Tuple[int, int] = (112, 112),
        input_mean: float = 127.5,
        input_std: float = 127.5,
        color_format: str = "RGB",  # или "BGR"
    ):
        self.input_size = input_size  # (width, height)
        self.input_mean = input_mean
        self.input_std = input_std
        self.color_format = color_format.upper()
        
        # Валидация
        assert self.color_format in ["RGB", "BGR"], f"Invalid color format: {color_format}"
    
    def __call__(self, image: np.ndarray) -> np.ndarray:
        """Полный пайплайн препроцессинга"""
        return self.preprocess(image)
    
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Препроцессинг одного изображения
        
        Args:
            image: numpy array (H, W, C) в BGR формате (OpenCV стандарт)
        
        Returns:
            numpy array (1, C, H, W) готовый для инференса
        """
        # 1. Resize (cv2 использует (width, height))
        if image.shape[:2] != (self.input_size[1], self.input_size[0]):
            image = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)
        
        # 2. BGR -> RGB конвертация (если нужно)
        if self.color_format == "RGB":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # 3. Нормализация: [0, 255] -> [-1, 1]
        image = image.astype(np.float32)
        image = (image - self.input_mean) / self.input_std
        
        # 4. HWC -> CHW
        image = image.transpose(2, 0, 1)
        
        # 5. Добавляем batch dimension: CHW -> NCHW
        image = np.expand_dims(image, axis=0)
        
        return image
    
    def preprocess_batch(self, images: List[np.ndarray]) -> np.ndarray:
        """Препроцессинг батча изображений"""
        processed = [self.preprocess(img) for img in images]
        return np.concatenate(processed, axis=0)
    
    def load_and_preprocess(self, image_path: Union[str, Path]) -> np.ndarray:
        """Загрузка и препроцессинг изображения из файла"""
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot load image: {image_path}")
        return self.preprocess(image)


class AlignedFacePreprocessor(InsightFacePreprocessor):
    """
    Препроцессор с выравниванием лица по landmarks
    
    Используется когда входные изображения НЕ выровнены
    """
    
    # Стандартные позиции landmarks для 112x112
    ARCFACE_DST = np.array([
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041]
    ], dtype=np.float32)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._face_detector = None
    
    @property
    def face_detector(self):
        """Ленивая инициализация детектора лиц"""
        if self._face_detector is None:
            try:
                from insightface.app import FaceAnalysis
                self._face_detector = FaceAnalysis(
                    name='buffalo_l', 
                    providers=['CPUExecutionProvider']
                )
                self._face_detector.prepare(ctx_id=-1, det_size=(640, 640))
            except ImportError:
                raise ImportError("Install insightface: pip install insightface")
        return self._face_detector
    
    def align_face(self, image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """
        Выравнивание лица по 5 landmarks
        
        Args:
            image: исходное изображение (BGR)
            landmarks: 5 точек (5, 2) - left_eye, right_eye, nose, left_mouth, right_mouth
        
        Returns:
            Выровненное лицо 112x112
        """
        from skimage import transform as trans
        
        # Вычисляем аффинное преобразование
        tform = trans.SimilarityTransform()
        tform.estimate(landmarks, self.ARCFACE_DST)
        
        # Применяем трансформацию
        M = tform.params[0:2, :]
        aligned = cv2.warpAffine(
            image, M, 
            (self.input_size[0], self.input_size[1]), 
            borderValue=0.0
        )
        
        return aligned
    
    def detect_and_align(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Детекция лица и выравнивание
        
        Returns:
            Выровненное лицо или None если лицо не найдено
        """
        faces = self.face_detector.get(image)
        
        if len(faces) == 0:
            return None
        
        # Берём лицо с максимальным confidence
        face = max(faces, key=lambda x: x.det_score)
        landmarks = face.kps  # 5 landmarks
        
        aligned = self.align_face(image, landmarks)
        return aligned
    
    def preprocess_with_detection(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Полный пайплайн: детекция -> выравнивание -> препроцессинг"""
        aligned = self.detect_and_align(image)
        if aligned is None:
            return None
        
        # Стандартный препроцессинг (без resize, уже 112x112)
        if self.color_format == "RGB":
            aligned = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)
        
        aligned = aligned.astype(np.float32)
        aligned = (aligned - self.input_mean) / self.input_std
        aligned = aligned.transpose(2, 0, 1)
        aligned = np.expand_dims(aligned, axis=0)
        
        return aligned


def normalize_embedding(embedding: np.ndarray, axis: int = 1) -> np.ndarray:
    """
    L2 нормализация эмбеддингов
    
    Args:
        embedding: (N, D) или (D,) эмбеддинги
        axis: ось для нормализации
    
    Returns:
        Нормализованные эмбеддинги с ||e|| = 1
    """
    if embedding.ndim == 1:
        norm = np.linalg.norm(embedding)
        return embedding / (norm + 1e-10)
    else:
        norm = np.linalg.norm(embedding, axis=axis, keepdims=True)
        return embedding / (norm + 1e-10)


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Косинусное сходство между двумя эмбеддингами
    
    Предполагается, что эмбеддинги уже L2-нормализованы
    """
    return float(np.dot(emb1.flatten(), emb2.flatten()))


def cosine_similarity_batch(emb1: np.ndarray, emb2: np.ndarray) -> np.ndarray:
    """
    Косинусное сходство для батчей
    
    Args:
        emb1: (N, D) первый батч
        emb2: (N, D) второй батч
    
    Returns:
        (N,) сходства для каждой пары
    """
    # Нормализация на всякий случай
    emb1 = normalize_embedding(emb1)
    emb2 = normalize_embedding(emb2)
    
    # Поэлементное скалярное произведение
    return np.sum(emb1 * emb2, axis=1)


# Пресеты для разных моделей
PREPROCESS_CONFIGS = {
    "arcface": {
        "input_size": (112, 112),
        "input_mean": 127.5,
        "input_std": 127.5,
        "color_format": "RGB"
    },
    "insightface_buffalo": {
        "input_size": (112, 112),
        "input_mean": 127.5,
        "input_std": 127.5,
        "color_format": "RGB"
    },
    "facenet": {
        "input_size": (160, 160),
        "input_mean": 127.5,
        "input_std": 128.0,
        "color_format": "RGB"
    },
    "vggface2": {
        "input_size": (224, 224),
        "input_mean": 127.5,
        "input_std": 127.5,
        "color_format": "BGR"
    }
}


def get_preprocessor(preset: str = "arcface") -> InsightFacePreprocessor:
    """Получение препроцессора по имени пресета"""
    if preset not in PREPROCESS_CONFIGS:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(PREPROCESS_CONFIGS.keys())}")
    
    config = PREPROCESS_CONFIGS[preset]
    return InsightFacePreprocessor(**config)


if __name__ == "__main__":
    # Тест препроцессинга
    import tempfile
    
    print("=== Тест препроцессинга ===")
    
    # Создаём тестовое изображение
    test_img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    
    preprocessor = InsightFacePreprocessor()
    
    processed = preprocessor.preprocess(test_img)
    
    print(f"Input shape: {test_img.shape}")
    print(f"Output shape: {processed.shape}")
    print(f"Output dtype: {processed.dtype}")
    print(f"Output range: [{processed.min():.3f}, {processed.max():.3f}]")
    print(f"Expected range: [-1, 1]")
    
    # Тест нормализации эмбеддингов
    print("\n=== Тест нормализации ===")
    emb = np.random.randn(1, 512).astype(np.float32)
    emb_norm = normalize_embedding(emb)
    print(f"Original norm: {np.linalg.norm(emb):.4f}")
    print(f"Normalized norm: {np.linalg.norm(emb_norm):.4f}")
    
    print("\n[OK] Препроцессинг работает корректно")
