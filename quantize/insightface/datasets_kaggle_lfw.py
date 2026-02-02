#!/usr/bin/env python3
"""
datasets_kaggle_lfw.py - Загрузчик для Kaggle LFW датасета

Структура датасета jessicali9530/lfw-dataset:
- lfw-deepfunneled/lfw-deepfunneled/  - выровненные изображения
- matchpairsDevTest.csv   - пары для тестирования (same person)
- matchpairsDevTrain.csv  - пары для обучения (same person)  
- mismatchpairsDevTest.csv  - пары разных людей (test)
- mismatchpairsDevTrain.csv - пары разных людей (train)
- pairs.txt - оригинальный файл пар LFW
- people.csv / peopleDevTest.csv / peopleDevTrain.csv - списки людей

Использование:
    dataset = KaggleLFWDataset(
        root_dir="C:/Users/kosan/.cache/kagglehub/datasets/jessicali9530/lfw-dataset/versions/4",
        images_dir="C:/Users/kosan/.cache/kagglehub/datasets/jessicali9530/lfw-dataset/versions/4/lfw-deepfunneled/lfw-deepfunneled"
    )
    pairs = dataset.load_pairs()
"""

import os
import csv
import numpy as np
import cv2
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from tqdm import tqdm


@dataclass
class VerificationPair:
    """Пара изображений для верификации"""
    img1_path: str
    img2_path: str
    is_same: bool
    
    def load_images(self) -> Tuple[np.ndarray, np.ndarray]:
        """Загрузка изображений"""
        img1 = cv2.imread(self.img1_path)
        img2 = cv2.imread(self.img2_path)
        
        if img1 is None:
            raise ValueError(f"Cannot load image: {self.img1_path}")
        if img2 is None:
            raise ValueError(f"Cannot load image: {self.img2_path}")
        
        return img1, img2


class KaggleLFWDataset:
    """
    Загрузчик для Kaggle LFW датасета (jessicali9530/lfw-dataset)
    """
    
    def __init__(
        self,
        root_dir: str,
        images_dir: str = None,
        use_test: bool = True
    ):
        """
        Args:
            root_dir: путь к корню датасета (где лежат CSV файлы)
            images_dir: путь к папке с изображениями (lfw-deepfunneled/lfw-deepfunneled)
            use_test: использовать Test (True) или Train (False) split
        """
        self.root_dir = Path(root_dir)
        
        # Определяем путь к изображениям
        if images_dir:
            self.images_dir = Path(images_dir)
        else:
            # Пробуем стандартные пути
            candidates = [
                self.root_dir / "lfw-deepfunneled" / "lfw-deepfunneled",
                self.root_dir / "lfw-deepfunneled",
                self.root_dir / "lfw_funneled" / "lfw_funneled",
                self.root_dir / "lfw"
            ]
            self.images_dir = None
            for c in candidates:
                if c.exists():
                    self.images_dir = c
                    break
            
            if self.images_dir is None:
                raise ValueError(f"Cannot find images directory in {root_dir}")
        
        self.use_test = use_test
        
        # Определяем файлы пар
        if use_test:
            self.match_file = self.root_dir / "matchpairsDevTest.csv"
            self.mismatch_file = self.root_dir / "mismatchpairsDevTest.csv"
        else:
            self.match_file = self.root_dir / "matchpairsDevTrain.csv"
            self.mismatch_file = self.root_dir / "mismatchpairsDevTrain.csv"
        
        # Также проверим pairs.txt (оригинальный формат LFW)
        self.pairs_txt = self.root_dir / "pairs.txt"
        
        print(f"[INFO] Kaggle LFW Dataset initialized")
        print(f"  Root dir: {self.root_dir}")
        print(f"  Images dir: {self.images_dir}")
        print(f"  Split: {'Test' if use_test else 'Train'}")
    
    def _get_image_path(self, name: str, image_num: int) -> str:
        """
        Получение пути к изображению
        
        Args:
            name: имя человека (e.g., "George_W_Bush")
            image_num: номер изображения (1-based)
        
        Returns:
            Полный путь к файлу
        """
        # Формат имени файла: Name_Surname_0001.jpg
        filename = f"{name}_{image_num:04d}.jpg"
        path = self.images_dir / name / filename
        return str(path)
    
    def _parse_match_csv(self, csv_path: Path) -> List[Tuple[str, int, int]]:
        """
        Парсинг CSV с positive парами (одна личность)
        
        Формат: name,imagenum1,imagenum2
        """
        pairs = []
        
        if not csv_path.exists():
            print(f"[WARN] File not found: {csv_path}")
            return pairs
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Пропускаем заголовок
            
            for row in reader:
                if len(row) >= 3:
                    name = row[0].strip()
                    try:
                        num1 = int(row[1])
                        num2 = int(row[2])
                        pairs.append((name, num1, num2))
                    except ValueError:
                        continue
        
        return pairs
    
    def _parse_mismatch_csv(self, csv_path: Path) -> List[Tuple[str, int, str, int]]:
        """
        Парсинг CSV с negative парами (разные личности)
        
        Формат: name1,imagenum1,name2,imagenum2
        """
        pairs = []
        
        if not csv_path.exists():
            print(f"[WARN] File not found: {csv_path}")
            return pairs
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            
            for row in reader:
                if len(row) >= 4:
                    name1 = row[0].strip()
                    name2 = row[2].strip()
                    try:
                        num1 = int(row[1])
                        num2 = int(row[3])
                        pairs.append((name1, num1, name2, num2))
                    except ValueError:
                        continue
        
        return pairs
    
    def load_pairs_from_csv(self) -> List[VerificationPair]:
        """
        Загрузка пар из CSV файлов Kaggle датасета
        """
        pairs = []
        skipped = 0
        
        # Positive pairs (same person)
        print(f"[INFO] Loading positive pairs from {self.match_file.name}...")
        match_data = self._parse_match_csv(self.match_file)
        
        for name, num1, num2 in match_data:
            img1_path = self._get_image_path(name, num1)
            img2_path = self._get_image_path(name, num2)
            
            if os.path.exists(img1_path) and os.path.exists(img2_path):
                pairs.append(VerificationPair(img1_path, img2_path, is_same=True))
            else:
                skipped += 1
        
        n_positive = len(pairs)
        
        # Negative pairs (different persons)
        print(f"[INFO] Loading negative pairs from {self.mismatch_file.name}...")
        mismatch_data = self._parse_mismatch_csv(self.mismatch_file)
        
        for name1, num1, name2, num2 in mismatch_data:
            img1_path = self._get_image_path(name1, num1)
            img2_path = self._get_image_path(name2, num2)
            
            if os.path.exists(img1_path) and os.path.exists(img2_path):
                pairs.append(VerificationPair(img1_path, img2_path, is_same=False))
            else:
                skipped += 1
        
        n_negative = len(pairs) - n_positive
        
        print(f"[INFO] Loaded {len(pairs)} pairs:")
        print(f"  Positive (same): {n_positive}")
        print(f"  Negative (diff): {n_negative}")
        if skipped > 0:
            print(f"  Skipped (missing files): {skipped}")
        
        return pairs
    
    def load_pairs_from_txt(self) -> List[VerificationPair]:
        """
        Загрузка пар из оригинального pairs.txt (если CSV не работает)
        
        Формат pairs.txt:
        - Первая строка: "10	300" (10 фолдов по 300 пар)
        - Positive: "Name	num1	num2"
        - Negative: "Name1	num1	Name2	num2"
        """
        pairs = []
        
        if not self.pairs_txt.exists():
            print(f"[WARN] pairs.txt not found: {self.pairs_txt}")
            return pairs
        
        print(f"[INFO] Loading pairs from {self.pairs_txt}...")
        
        with open(self.pairs_txt, 'r') as f:
            lines = f.readlines()
        
        # Пропускаем заголовок
        start_idx = 0
        first_line = lines[0].strip().split()
        if len(first_line) == 2 and first_line[0].isdigit():
            start_idx = 1
        
        skipped = 0
        
        for line in lines[start_idx:]:
            parts = line.strip().split('\t')
            
            if len(parts) == 3:
                # Positive pair
                name = parts[0]
                try:
                    num1, num2 = int(parts[1]), int(parts[2])
                    img1_path = self._get_image_path(name, num1)
                    img2_path = self._get_image_path(name, num2)
                    
                    if os.path.exists(img1_path) and os.path.exists(img2_path):
                        pairs.append(VerificationPair(img1_path, img2_path, is_same=True))
                    else:
                        skipped += 1
                except ValueError:
                    pass
                    
            elif len(parts) == 4:
                # Negative pair
                name1, name2 = parts[0], parts[2]
                try:
                    num1, num2 = int(parts[1]), int(parts[3])
                    img1_path = self._get_image_path(name1, num1)
                    img2_path = self._get_image_path(name2, num2)
                    
                    if os.path.exists(img1_path) and os.path.exists(img2_path):
                        pairs.append(VerificationPair(img1_path, img2_path, is_same=False))
                    else:
                        skipped += 1
                except ValueError:
                    pass
        
        n_positive = sum(1 for p in pairs if p.is_same)
        n_negative = len(pairs) - n_positive
        
        print(f"[INFO] Loaded {len(pairs)} pairs:")
        print(f"  Positive (same): {n_positive}")
        print(f"  Negative (diff): {n_negative}")
        if skipped > 0:
            print(f"  Skipped (missing files): {skipped}")
        
        return pairs
    
    def load_pairs(self) -> List[VerificationPair]:
        """
        Загрузка пар - пробует CSV, потом pairs.txt
        """
        # Сначала пробуем CSV
        if self.match_file.exists() and self.mismatch_file.exists():
            pairs = self.load_pairs_from_csv()
            if len(pairs) > 0:
                return pairs
        
        # Fallback на pairs.txt
        return self.load_pairs_from_txt()
    
    def get_calibration_images(self, n_images: int = 500) -> List[str]:
        """
        Получение путей к изображениям для калибровки
        """
        all_images = []
        
        for person_dir in self.images_dir.iterdir():
            if person_dir.is_dir():
                for img_file in person_dir.glob("*.jpg"):
                    all_images.append(str(img_file))
        
        print(f"[INFO] Found {len(all_images)} total images")
        
        # Случайная выборка
        np.random.shuffle(all_images)
        
        return all_images[:n_images]
    
    def get_all_image_paths(self) -> List[str]:
        """Получение всех путей к изображениям"""
        return self.get_calibration_images(n_images=999999)


def test_kaggle_lfw():
    """Тест загрузчика"""
    
    # Пути для Windows (используй forward slashes или raw strings)
    root_dir = "C:/Users/kosan/.cache/kagglehub/datasets/jessicali9530/lfw-dataset/versions/4"
    images_dir = "C:/Users/kosan/.cache/kagglehub/datasets/jessicali9530/lfw-dataset/versions/4/lfw-deepfunneled/lfw-deepfunneled"
    
    print("="*60)
    print("Testing Kaggle LFW Dataset Loader")
    print("="*60)
    
    # Проверяем существование путей
    if not os.path.exists(root_dir):
        print(f"[ERROR] Root directory not found: {root_dir}")
        print("\nУкажите правильные пути к датасету!")
        return
    
    # Создаём загрузчик
    dataset = KaggleLFWDataset(
        root_dir=root_dir,
        images_dir=images_dir,
        use_test=True
    )
    
    # Загружаем пары
    pairs = dataset.load_pairs()
    
    if len(pairs) > 0:
        # Тестируем загрузку изображения
        print("\n[INFO] Testing image loading...")
        pair = pairs[0]
        try:
            img1, img2 = pair.load_images()
            print(f"  Image 1 shape: {img1.shape}")
            print(f"  Image 2 shape: {img2.shape}")
            print(f"  Is same person: {pair.is_same}")
            print("[OK] Image loading works!")
        except Exception as e:
            print(f"[ERROR] Failed to load images: {e}")
    
    # Тестируем получение калибровочных изображений
    print("\n[INFO] Testing calibration images...")
    calib_images = dataset.get_calibration_images(n_images=10)
    print(f"  Got {len(calib_images)} calibration image paths")
    if calib_images:
        print(f"  Example: {calib_images[0]}")


if __name__ == "__main__":
    test_kaggle_lfw()
