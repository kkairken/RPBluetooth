#!/usr/bin/env python3
"""
eval_verification.py - Оценка качества face verification модели

Метрики:
- Accuracy при оптимальном пороге
- TAR@FAR (True Accept Rate при заданном False Accept Rate)
- ROC AUC
- Распределение сходств (genuine vs impostor)

Использование:
    python eval_verification.py --model models/insightface_fp32.onnx --dataset ./data/lfw
    python eval_verification.py --model models/insightface_int8_static.onnx --dataset ./data/lfw.bin
"""

import os
import sys
import argparse
import time
import json
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict
from tqdm import tqdm
import warnings

# Локальные импорты
from preprocessing import InsightFacePreprocessor, normalize_embedding, cosine_similarity_batch
from datasets import LFWDataset, CFPDataset, AgeDBDataset, BinaryDataset, VerificationPair


@dataclass
class VerificationMetrics:
    """Результаты оценки верификации"""
    accuracy: float
    threshold: float
    tar_at_far_1e3: float  # TAR @ FAR=0.001
    tar_at_far_1e4: float  # TAR @ FAR=0.0001
    roc_auc: float

    # Дополнительная статистика
    genuine_mean: float
    genuine_std: float
    impostor_mean: float
    impostor_std: float

    # Информация о модели
    model_name: str = ""
    model_size_mb: float = 0.0
    inference_latency_ms: float = 0.0
    throughput_fps: float = 0.0

    def to_dict(self) -> Dict:
        # Конвертируем numpy типы в Python native для JSON сериализации
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, (np.floating, np.float32, np.float64)):
                result[key] = float(value)
            elif isinstance(value, (np.integer, np.int32, np.int64)):
                result[key] = int(value)
            else:
                result[key] = value
        return result

    def summary(self) -> str:
        return (
            f"=== Verification Results: {self.model_name} ===\n"
            f"Accuracy:        {self.accuracy:.4f} (threshold={self.threshold:.4f})\n"
            f"TAR@FAR=1e-3:    {self.tar_at_far_1e3:.4f}\n"
            f"TAR@FAR=1e-4:    {self.tar_at_far_1e4:.4f}\n"
            f"ROC AUC:         {self.roc_auc:.4f}\n"
            f"\n"
            f"Genuine pairs:   mean={self.genuine_mean:.4f}, std={self.genuine_std:.4f}\n"
            f"Impostor pairs:  mean={self.impostor_mean:.4f}, std={self.impostor_std:.4f}\n"
            f"\n"
            f"Model size:      {self.model_size_mb:.2f} MB\n"
            f"Latency:         {self.inference_latency_ms:.2f} ms\n"
            f"Throughput:      {self.throughput_fps:.1f} img/s\n"
        )


class FaceVerificationEvaluator:
    """Оценщик качества face verification"""

    def __init__(
            self,
            model_path: str,
            preprocessor: InsightFacePreprocessor = None,
            providers: List[str] = None,
            num_threads: int = 4
    ):
        """
        Args:
            model_path: путь к ONNX модели
            preprocessor: препроцессор (по умолчанию InsightFacePreprocessor)
            providers: ONNX Runtime execution providers
            num_threads: количество потоков для CPU
        """
        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        # Препроцессор
        self.preprocessor = preprocessor or InsightFacePreprocessor()

        # Настройка ONNX Runtime
        if providers is None:
            providers = ['CPUExecutionProvider']

        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = num_threads
        sess_options.inter_op_num_threads = num_threads
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        print(f"[INFO] Loading model: {self.model_path.name}")
        print(f"[INFO] Providers: {providers}")

        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=sess_options,
            providers=providers
        )

        # Получаем информацию о входе/выходе
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape
        self.output_name = self.session.get_outputs()[0].name

        print(f"[INFO] Input: {self.input_name} {self.input_shape}")
        print(f"[INFO] Output: {self.output_name}")

        # Размер модели
        self.model_size_mb = os.path.getsize(model_path) / (1024 * 1024)

    def get_embedding(self, image: np.ndarray) -> np.ndarray:
        """
        Получение эмбеддинга для одного изображения

        Args:
            image: BGR изображение (H, W, 3)

        Returns:
            L2-нормализованный эмбеддинг
        """
        # Препроцессинг
        input_tensor = self.preprocessor.preprocess(image)

        # Инференс
        outputs = self.session.run(
            [self.output_name],
            {self.input_name: input_tensor}
        )

        embedding = outputs[0]

        # L2 нормализация
        embedding = normalize_embedding(embedding)

        return embedding

    def get_embeddings_batch(
            self,
            images: List[np.ndarray],
            batch_size: int = 32,
            show_progress: bool = True
    ) -> np.ndarray:
        """
        Получение эмбеддингов для батча изображений

        Args:
            images: список BGR изображений
            batch_size: размер батча
            show_progress: показывать прогресс

        Returns:
            (N, D) массив эмбеддингов
        """
        embeddings = []

        iterator = range(0, len(images), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Computing embeddings")

        for i in iterator:
            batch_images = images[i:i + batch_size]

            # Препроцессинг батча
            batch_tensors = []
            for img in batch_images:
                tensor = self.preprocessor.preprocess(img)
                batch_tensors.append(tensor)

            batch_input = np.concatenate(batch_tensors, axis=0)

            # Инференс
            outputs = self.session.run(
                [self.output_name],
                {self.input_name: batch_input}
            )

            batch_embeddings = normalize_embedding(outputs[0])
            embeddings.append(batch_embeddings)

        return np.concatenate(embeddings, axis=0)

    def compute_similarities(
            self,
            pairs: List[VerificationPair] = None,
            imgs1: List[np.ndarray] = None,
            imgs2: List[np.ndarray] = None,
            labels: np.ndarray = None,
            batch_size: int = 32
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Вычисление косинусных сходств для пар

        Args:
            pairs: список VerificationPair (для файловых датасетов)
            imgs1, imgs2, labels: напрямую изображения и метки (для бинарных)

        Returns:
            similarities: (N,) массив сходств
            labels: (N,) массив меток (True/False)
        """
        if pairs is not None:
            # Загружаем изображения из файлов
            print("[INFO] Loading images from pairs...")
            imgs1_list = []
            imgs2_list = []
            labels_list = []

            for pair in tqdm(pairs, desc="Loading pairs"):
                try:
                    img1, img2 = pair.load_images()
                    imgs1_list.append(img1)
                    imgs2_list.append(img2)
                    labels_list.append(pair.is_same)
                except Exception as e:
                    print(f"[WARN] Failed to load pair: {e}")

            imgs1 = imgs1_list
            imgs2 = imgs2_list
            labels = np.array(labels_list)

        # Получаем эмбеддинги
        print(f"[INFO] Computing embeddings for {len(imgs1)} pairs...")
        emb1 = self.get_embeddings_batch(imgs1, batch_size=batch_size)
        emb2 = self.get_embeddings_batch(imgs2, batch_size=batch_size)

        # Косинусное сходство
        similarities = cosine_similarity_batch(emb1, emb2)

        return similarities, labels

    def find_optimal_threshold(
            self,
            similarities: np.ndarray,
            labels: np.ndarray,
            n_thresholds: int = 1000
    ) -> Tuple[float, float]:
        """
        Поиск оптимального порога для максимальной accuracy

        Returns:
            threshold: оптимальный порог
            accuracy: точность при этом пороге
        """
        thresholds = np.linspace(similarities.min(), similarities.max(), n_thresholds)

        best_threshold = 0
        best_accuracy = 0

        for thresh in thresholds:
            predictions = similarities >= thresh
            accuracy = np.mean(predictions == labels)

            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_threshold = thresh

        return best_threshold, best_accuracy

    def compute_tar_at_far(
            self,
            similarities: np.ndarray,
            labels: np.ndarray,
            target_far: float
    ) -> Tuple[float, float]:
        """
        Вычисление TAR при заданном FAR

        TAR (True Accept Rate) = TP / (TP + FN) = чувствительность для genuine пар
        FAR (False Accept Rate) = FP / (FP + TN) = ложные срабатывания на impostor парах

        Returns:
            tar: True Accept Rate при target_far
            threshold: порог для достижения target_far
        """
        # Разделяем на genuine и impostor
        genuine_similarities = similarities[labels]
        impostor_similarities = similarities[~labels]

        # Сортируем impostor сходства по убыванию
        sorted_impostor = np.sort(impostor_similarities)[::-1]

        # Находим порог для target_far
        n_impostors = len(impostor_similarities)
        idx = int(np.ceil(target_far * n_impostors))

        if idx >= len(sorted_impostor):
            threshold = sorted_impostor[-1] - 0.001
        else:
            threshold = sorted_impostor[idx]

        # Вычисляем TAR при этом пороге
        tar = np.mean(genuine_similarities >= threshold)

        return tar, threshold

    def compute_roc_auc(
            self,
            similarities: np.ndarray,
            labels: np.ndarray
    ) -> float:
        """Вычисление ROC AUC"""
        try:
            from sklearn.metrics import roc_auc_score
            return roc_auc_score(labels, similarities)
        except ImportError:
            # Простая реализация
            genuine = similarities[labels]
            impostor = similarities[~labels]

            n_pos = len(genuine)
            n_neg = len(impostor)

            auc = 0.0
            for g in genuine:
                auc += np.sum(g > impostor) + 0.5 * np.sum(g == impostor)

            return auc / (n_pos * n_neg)

    def measure_latency(
            self,
            n_warmup: int = 10,
            n_iterations: int = 100
    ) -> Tuple[float, float]:
        """
        Измерение latency и throughput

        Returns:
            latency_ms: средняя латентность в миллисекундах
            throughput: изображений в секунду
        """
        # Создаём тестовый вход
        input_shape = self.input_shape.copy()
        input_shape[0] = 1  # batch_size = 1
        input_shape = [s if isinstance(s, int) else 1 for s in input_shape]

        dummy_input = np.random.randn(*input_shape).astype(np.float32)

        # Прогрев
        for _ in range(n_warmup):
            self.session.run([self.output_name], {self.input_name: dummy_input})

        # Измерение
        start = time.perf_counter()
        for _ in range(n_iterations):
            self.session.run([self.output_name], {self.input_name: dummy_input})
        elapsed = time.perf_counter() - start

        latency_ms = (elapsed / n_iterations) * 1000
        throughput = n_iterations / elapsed

        return latency_ms, throughput

    def evaluate(
            self,
            pairs: List[VerificationPair] = None,
            imgs1: List[np.ndarray] = None,
            imgs2: List[np.ndarray] = None,
            labels: np.ndarray = None,
            batch_size: int = 32,
            measure_speed: bool = True
    ) -> VerificationMetrics:
        """
        Полная оценка модели

        Args:
            pairs: список пар (для файловых датасетов)
            imgs1, imgs2, labels: напрямую данные (для бинарных датасетов)
            batch_size: размер батча
            measure_speed: измерять скорость

        Returns:
            VerificationMetrics со всеми метриками
        """
        # Вычисляем сходства
        similarities, labels = self.compute_similarities(
            pairs=pairs,
            imgs1=imgs1,
            imgs2=imgs2,
            labels=labels,
            batch_size=batch_size
        )

        # Метрики
        print("[INFO] Computing metrics...")

        threshold, accuracy = self.find_optimal_threshold(similarities, labels)
        tar_1e3, _ = self.compute_tar_at_far(similarities, labels, 1e-3)
        tar_1e4, _ = self.compute_tar_at_far(similarities, labels, 1e-4)
        roc_auc = self.compute_roc_auc(similarities, labels)

        # Статистика распределений
        genuine_sims = similarities[labels]
        impostor_sims = similarities[~labels]

        # Скорость
        latency_ms = 0.0
        throughput = 0.0
        if measure_speed:
            print("[INFO] Measuring latency...")
            latency_ms, throughput = self.measure_latency()

        metrics = VerificationMetrics(
            accuracy=accuracy,
            threshold=threshold,
            tar_at_far_1e3=tar_1e3,
            tar_at_far_1e4=tar_1e4,
            roc_auc=roc_auc,
            genuine_mean=float(np.mean(genuine_sims)),
            genuine_std=float(np.std(genuine_sims)),
            impostor_mean=float(np.mean(impostor_sims)),
            impostor_std=float(np.std(impostor_sims)),
            model_name=self.model_path.name,
            model_size_mb=self.model_size_mb,
            inference_latency_ms=latency_ms,
            throughput_fps=throughput
        )

        return metrics, similarities, labels


def evaluate_model_on_dataset(
        model_path: str,
        dataset_path: str,
        dataset_type: str = "auto",
        output_dir: str = "./results",
        batch_size: int = 32
) -> VerificationMetrics:
    """
    Оценка модели на датасете

    Args:
        model_path: путь к ONNX модели
        dataset_path: путь к датасету
        dataset_type: тип датасета (auto, lfw, cfp_fp, agedb, binary)
        output_dir: директория для результатов
        batch_size: размер батча
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Определяем тип датасета
    if dataset_type == "auto":
        if dataset_path.endswith(".bin"):
            dataset_type = "binary"
        elif "cfp" in dataset_path.lower():
            dataset_type = "cfp_fp"
        elif "agedb" in dataset_path.lower():
            dataset_type = "agedb"
        else:
            dataset_type = "lfw"

    print(f"\n{'=' * 60}")
    print(f"Evaluating: {Path(model_path).name}")
    print(f"Dataset: {dataset_path} ({dataset_type})")
    print(f"{'=' * 60}\n")

    # Создаём evaluator
    evaluator = FaceVerificationEvaluator(model_path)

    # Загружаем датасет
    if dataset_type == "binary":
        dataset = BinaryDataset(dataset_path)
        imgs1, imgs2, labels = dataset.load_pairs()
        metrics, sims, labels = evaluator.evaluate(
            imgs1=imgs1, imgs2=imgs2, labels=labels,
            batch_size=batch_size
        )
    elif dataset_type == "lfw":
        dataset = LFWDataset(dataset_path)
        pairs = dataset.load_pairs()
        metrics, sims, labels = evaluator.evaluate(pairs=pairs, batch_size=batch_size)
    elif dataset_type == "cfp_fp":
        dataset = CFPDataset(dataset_path, protocol="FP")
        pairs = dataset.load_pairs()
        metrics, sims, labels = evaluator.evaluate(pairs=pairs, batch_size=batch_size)
    elif dataset_type == "agedb":
        dataset = AgeDBDataset(dataset_path)
        pairs = dataset.load_pairs()
        metrics, sims, labels = evaluator.evaluate(pairs=pairs, batch_size=batch_size)
    else:
        raise ValueError(f"Unknown dataset type: {dataset_type}")

    # Вывод результатов
    print("\n" + metrics.summary())

    # Сохраняем результаты
    model_name = Path(model_path).stem
    results_file = output_path / f"results_{model_name}.json"

    with open(results_file, 'w') as f:
        json.dump(metrics.to_dict(), f, indent=2)

    print(f"[INFO] Results saved to: {results_file}")

    # Сохраняем распределения сходств для анализа
    np.savez(
        output_path / f"similarities_{model_name}.npz",
        similarities=sims,
        labels=labels,
        genuine=sims[labels],
        impostor=sims[~labels]
    )

    return metrics


def compare_models(
        model_paths: List[str],
        dataset_path: str,
        output_dir: str = "./results"
) -> Dict[str, VerificationMetrics]:
    """Сравнение нескольких моделей"""
    results = {}

    for model_path in model_paths:
        try:
            metrics = evaluate_model_on_dataset(
                model_path=model_path,
                dataset_path=dataset_path,
                output_dir=output_dir
            )
            results[Path(model_path).name] = metrics
        except Exception as e:
            print(f"[ERROR] Failed to evaluate {model_path}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Face Verification Evaluation")
    parser.add_argument("--model", type=str, required=True,
                        help="Path to ONNX model")
    parser.add_argument("--dataset", type=str, required=True,
                        help="Path to dataset (directory or .bin file)")
    parser.add_argument("--dataset-type", type=str, default="auto",
                        choices=["auto", "lfw", "cfp_fp", "agedb", "binary"],
                        help="Dataset type")
    parser.add_argument("--output-dir", type=str, default="./results",
                        help="Output directory for results")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Batch size for inference")
    parser.add_argument("--compare", type=str, nargs="+", default=None,
                        help="Compare multiple models")

    args = parser.parse_args()

    if args.compare:
        compare_models(
            model_paths=args.compare,
            dataset_path=args.dataset,
            output_dir=args.output_dir
        )
    else:
        evaluate_model_on_dataset(
            model_path=args.model,
            dataset_path=args.dataset,
            dataset_type=args.dataset_type,
            output_dir=args.output_dir,
            batch_size=args.batch_size
        )


if __name__ == "__main__":
    main()