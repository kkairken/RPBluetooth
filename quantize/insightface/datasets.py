#!/usr/bin/env python3
"""
datasets.py - Загрузчики датасетов для face verification

Поддерживаемые датасеты:
- LFW (Labeled Faces in the Wild)
- CFP-FP (Celebrities in Frontal-Profile)
- AgeDB-30

Формат данных: пары изображений + метки (same/different person)
"""

import os
import sys
import numpy as np
import cv2
from pathlib import Path
from typing import List, Tuple, Generator, Optional, Dict
from dataclasses import dataclass
import tarfile
import zipfile
from tqdm import tqdm


@dataclass
class VerificationPair:
    """Пара изображений для верификации"""
    img1_path: str
    img2_path: str
    is_same: bool  # True если одна личность
    
    def load_images(self) -> Tuple[np.ndarray, np.ndarray]:
        """Загрузка изображений"""
        img1 = cv2.imread(self.img1_path)
        img2 = cv2.imread(self.img2_path)
        
        if img1 is None:
            raise ValueError(f"Cannot load image: {self.img1_path}")
        if img2 is None:
            raise ValueError(f"Cannot load image: {self.img2_path}")
        
        return img1, img2


class LFWDataset:
    """
    LFW (Labeled Faces in the Wild) Dataset
    
    Структура:
    - lfw/
      - Aaron_Eckhart/
        - Aaron_Eckhart_0001.jpg
      - ...
    - pairs.txt (6000 пар для тестирования)
    
    Download: http://vis-www.cs.umass.edu/lfw/
    """
    
    URL = "http://vis-www.cs.umass.edu/lfw/lfw.tgz"
    PAIRS_URL = "http://vis-www.cs.umass.edu/lfw/pairs.txt"
    
    def __init__(self, root_dir: str, aligned: bool = True):
        """
        Args:
            root_dir: путь к папке с LFW
            aligned: использовать выровненные изображения (lfw-align-128 или lfw)
        """
        self.root_dir = Path(root_dir)
        self.aligned = aligned
        
        # Определяем папку с изображениями
        if aligned:
            candidates = ["lfw-align-128", "lfw_funneled", "lfw-deepfunneled/lfw-deepfunneled", "lfw-deepfunneled", "lfw"]
        else:
            candidates = ["lfw"]
        
        self.images_dir = None
        for candidate in candidates:
            if (self.root_dir / candidate).exists():
                self.images_dir = self.root_dir / candidate
                break
        
        if self.images_dir is None:
            # Если root_dir сама содержит папки с людьми
            if any((self.root_dir / d).is_dir() for d in os.listdir(self.root_dir) if not d.startswith('.')):
                self.images_dir = self.root_dir
            else:
                raise ValueError(f"LFW images not found in {root_dir}")
        
        self.pairs_file = self.root_dir / "pairs.txt"
        
        print(f"[INFO] LFW dataset initialized")
        print(f"  Images dir: {self.images_dir}")
        print(f"  Pairs file: {self.pairs_file}")
    
    def _get_image_path(self, name: str, idx: int) -> str:
        """Получение пути к изображению по имени и индексу"""
        # Формат: Name_Surname_0001.jpg
        filename = f"{name}_{idx:04d}.jpg"
        path = self.images_dir / name / filename
        return str(path)
    
    def load_pairs(self) -> List[VerificationPair]:
        """
        Загрузка пар из pairs.txt
        
        Формат pairs.txt:
        - Первая строка: количество фолдов и пар в фолде (e.g., "10    300")
        - Positive pairs: "Name    idx1    idx2"
        - Negative pairs: "Name1    idx1    Name2    idx2"
        """
        if not self.pairs_file.exists():
            raise FileNotFoundError(
                f"pairs.txt not found at {self.pairs_file}\n"
                f"Download from: {self.PAIRS_URL}"
            )
        
        pairs = []
        
        with open(self.pairs_file, 'r') as f:
            lines = f.readlines()
        
        # Пропускаем заголовок
        header = lines[0].strip().split()
        if len(header) == 2:
            n_folds, n_pairs = int(header[0]), int(header[1])
            start_idx = 1
        else:
            start_idx = 0
        
        for line in lines[start_idx:]:
            parts = line.strip().split('\t')
            if len(parts) == 0 or parts[0] == '':
                continue
            
            if len(parts) == 3:
                # Positive pair: same person
                name = parts[0]
                idx1, idx2 = int(parts[1]), int(parts[2])
                
                img1_path = self._get_image_path(name, idx1)
                img2_path = self._get_image_path(name, idx2)
                
                pairs.append(VerificationPair(img1_path, img2_path, is_same=True))
                
            elif len(parts) == 4:
                # Negative pair: different persons
                name1, idx1 = parts[0], int(parts[1])
                name2, idx2 = parts[2], int(parts[3])
                
                img1_path = self._get_image_path(name1, idx1)
                img2_path = self._get_image_path(name2, idx2)
                
                pairs.append(VerificationPair(img1_path, img2_path, is_same=False))
        
        print(f"[INFO] Loaded {len(pairs)} pairs ({sum(p.is_same for p in pairs)} positive, {sum(not p.is_same for p in pairs)} negative)")
        
        return pairs
    
    def get_calibration_images(self, n_images: int = 1000) -> List[str]:
        """
        Получение изображений для калибровки при статическом квантовании
        
        Args:
            n_images: количество изображений
        
        Returns:
            Список путей к изображениям
        """
        all_images = []
        
        for person_dir in self.images_dir.iterdir():
            if person_dir.is_dir():
                for img_file in person_dir.glob("*.jpg"):
                    all_images.append(str(img_file))
        
        # Случайная выборка
        np.random.shuffle(all_images)
        
        return all_images[:n_images]


class CFPDataset:
    """
    CFP (Celebrities in Frontal-Profile) Dataset
    
    Два протокола:
    - CFP-FF: Frontal vs Frontal
    - CFP-FP: Frontal vs Profile (более сложный)
    
    Download: http://www.cfpw.io/
    """
    
    def __init__(self, root_dir: str, protocol: str = "FP"):
        """
        Args:
            root_dir: путь к папке CFP
            protocol: "FP" (Frontal-Profile) или "FF" (Frontal-Frontal)
        """
        self.root_dir = Path(root_dir)
        self.protocol = protocol.upper()
        
        assert self.protocol in ["FP", "FF"], f"Invalid protocol: {protocol}"
        
        self.images_dir = self.root_dir / "Data" / "Images"
        self.protocol_dir = self.root_dir / "Protocol" / f"Fold{self.protocol.lower()}"
        
        print(f"[INFO] CFP-{self.protocol} dataset initialized")
        print(f"  Root: {self.root_dir}")
    
    def load_pairs(self, fold: int = None) -> List[VerificationPair]:
        """
        Загрузка пар из протокола
        
        Args:
            fold: номер фолда (1-10) или None для всех
        """
        pairs = []
        
        if fold is not None:
            folds = [fold]
        else:
            folds = range(1, 11)
        
        for f in folds:
            # Positive pairs (same identity)
            same_file = self.protocol_dir / f"fold_{f:02d}" / "same.txt"
            if same_file.exists():
                with open(same_file, 'r') as file:
                    for line in file:
                        parts = line.strip().split(',')
                        if len(parts) == 2:
                            img1 = self.images_dir / parts[0].strip()
                            img2 = self.images_dir / parts[1].strip()
                            pairs.append(VerificationPair(str(img1), str(img2), is_same=True))
            
            # Negative pairs (different identity)
            diff_file = self.protocol_dir / f"fold_{f:02d}" / "diff.txt"
            if diff_file.exists():
                with open(diff_file, 'r') as file:
                    for line in file:
                        parts = line.strip().split(',')
                        if len(parts) == 2:
                            img1 = self.images_dir / parts[0].strip()
                            img2 = self.images_dir / parts[1].strip()
                            pairs.append(VerificationPair(str(img1), str(img2), is_same=False))
        
        print(f"[INFO] Loaded {len(pairs)} pairs from CFP-{self.protocol}")
        return pairs


class AgeDBDataset:
    """
    AgeDB Dataset для тестирования с разницей в возрасте
    
    Протоколы: AgeDB-30 (разница в возрасте до 30 лет)
    
    Download: https://ibug.doc.ic.ac.uk/resources/agedb/
    """
    
    def __init__(self, root_dir: str, protocol: str = "30"):
        """
        Args:
            root_dir: путь к папке AgeDB
            protocol: "30" (разница до 30 лет)
        """
        self.root_dir = Path(root_dir)
        self.protocol = protocol
        
        # Структура может быть разной
        self.images_dir = self.root_dir / "aligned"
        if not self.images_dir.exists():
            self.images_dir = self.root_dir
        
        self.pairs_file = self.root_dir / f"agedb_{protocol}_pair.txt"
        
        print(f"[INFO] AgeDB-{protocol} dataset initialized")
        print(f"  Root: {self.root_dir}")
    
    def load_pairs(self) -> List[VerificationPair]:
        """Загрузка пар из файла протокола"""
        pairs = []
        
        if not self.pairs_file.exists():
            print(f"[WARN] Pairs file not found: {self.pairs_file}")
            return pairs
        
        with open(self.pairs_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3:
                    img1_name = parts[0]
                    img2_name = parts[1]
                    is_same = int(parts[2]) == 1
                    
                    img1_path = self._find_image(img1_name)
                    img2_path = self._find_image(img2_name)
                    
                    if img1_path and img2_path:
                        pairs.append(VerificationPair(img1_path, img2_path, is_same))
        
        print(f"[INFO] Loaded {len(pairs)} pairs from AgeDB-{self.protocol}")
        return pairs
    
    def _find_image(self, name: str) -> Optional[str]:
        """Поиск изображения по имени"""
        for ext in ['.jpg', '.png', '.jpeg']:
            path = self.images_dir / (name + ext)
            if path.exists():
                return str(path)
        
        # Поиск в подпапках
        for subdir in self.images_dir.iterdir():
            if subdir.is_dir():
                for ext in ['.jpg', '.png', '.jpeg']:
                    path = subdir / (name + ext)
                    if path.exists():
                        return str(path)
        
        return None


class BinaryDataset:
    """
    Загрузчик для бинарных датасетов InsightFace (*.bin)
    
    Эти файлы содержат уже выровненные изображения и пары.
    Используются в официальных бенчмарках InsightFace.
    
    Download: https://github.com/deepinsight/insightface/tree/master/recognition/_datasets_
    """
    
    def __init__(self, bin_path: str):
        """
        Args:
            bin_path: путь к .bin файлу (e.g., lfw.bin, cfp_fp.bin, agedb_30.bin)
        """
        self.bin_path = Path(bin_path)
        
        if not self.bin_path.exists():
            raise FileNotFoundError(f"Binary file not found: {bin_path}")
        
        print(f"[INFO] Loading binary dataset: {self.bin_path.name}")
    
    def load_pairs(self) -> Tuple[List[np.ndarray], List[np.ndarray], np.ndarray]:
        """
        Загрузка данных из бинарного файла
        
        Returns:
            imgs1: список изображений 1 (уже выровненных, RGB, float32)
            imgs2: список изображений 2
            issame: numpy array меток (True/False)
        """
        import pickle
        
        with open(self.bin_path, 'rb') as f:
            bins, issame = pickle.load(f, encoding='bytes')
        
        # Конвертация в numpy arrays
        imgs1 = []
        imgs2 = []
        
        for i in range(len(issame)):
            img1 = np.frombuffer(bins[2*i], dtype=np.uint8)
            img2 = np.frombuffer(bins[2*i + 1], dtype=np.uint8)
            
            # Декодирование JPEG
            img1 = cv2.imdecode(img1, cv2.IMREAD_COLOR)
            img2 = cv2.imdecode(img2, cv2.IMREAD_COLOR)
            
            imgs1.append(img1)
            imgs2.append(img2)
        
        issame = np.array(issame)
        
        print(f"[INFO] Loaded {len(issame)} pairs ({issame.sum()} positive)")
        
        return imgs1, imgs2, issame
    
    def get_calibration_images(self, n_images: int = 500) -> List[np.ndarray]:
        """Получение изображений для калибровки"""
        imgs1, imgs2, _ = self.load_pairs()
        all_imgs = imgs1 + imgs2
        
        np.random.shuffle(all_imgs)
        return all_imgs[:n_images]


def download_lfw(output_dir: str = "./data"):
    """Скачивание LFW датасета"""
    import urllib.request
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Скачиваем архив
    lfw_url = "http://vis-www.cs.umass.edu/lfw/lfw.tgz"
    pairs_url = "http://vis-www.cs.umass.edu/lfw/pairs.txt"
    
    lfw_path = output_path / "lfw.tgz"
    pairs_path = output_path / "pairs.txt"
    
    print("[INFO] Downloading LFW dataset...")
    
    if not lfw_path.exists():
        urllib.request.urlretrieve(lfw_url, lfw_path)
        print(f"  Downloaded: {lfw_path}")
    
    if not pairs_path.exists():
        urllib.request.urlretrieve(pairs_url, pairs_path)
        print(f"  Downloaded: {pairs_path}")
    
    # Распаковываем
    print("[INFO] Extracting...")
    with tarfile.open(lfw_path, "r:gz") as tar:
        tar.extractall(output_path)
    
    print(f"[INFO] LFW dataset ready at: {output_path}")
    
    return str(output_path)


def download_insightface_bins(output_dir: str = "./data"):
    """
    Скачивание бинарных датасетов InsightFace
    
    Содержит: lfw.bin, cfp_fp.bin, agedb_30.bin
    """
    import urllib.request
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # URL для датасетов (могут меняться)
    base_url = "https://github.com/deepinsight/insightface/releases/download/v0.2/"
    
    datasets = ["lfw.bin", "cfp_fp.bin", "agedb_30.bin"]
    
    print("[INFO] Downloading InsightFace binary datasets...")
    
    for ds in datasets:
        ds_path = output_path / ds
        if not ds_path.exists():
            try:
                url = base_url + ds
                print(f"  Downloading: {ds}")
                urllib.request.urlretrieve(url, ds_path)
            except Exception as e:
                print(f"  [WARN] Failed to download {ds}: {e}")
    
    print(f"[INFO] Datasets saved to: {output_path}")
    
    return str(output_path)


if __name__ == "__main__":
    # Пример использования
    print("=== Dataset Loaders Test ===\n")
    
    # Тест с фиктивными данными
    print("Testing LFW loader structure...")
    print("  Expected: lfw/ directory with person folders")
    print("  Expected: pairs.txt file with verification pairs")
    
    print("\nTo download LFW:")
    print("  python datasets.py --download lfw --output ./data")
    
    print("\nTo download InsightFace binaries:")
    print("  python datasets.py --download bins --output ./data")
