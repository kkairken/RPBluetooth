#!/usr/bin/env python3
"""
benchmark.py - Бенчмаркинг производительности ONNX моделей InsightFace

Измеряет:
- Latency (ms) для одиночного инференса
- Throughput (img/s) при батчевой обработке
- Размер модели
- Использование памяти

Поддерживаемые Execution Providers:
- CPUExecutionProvider (по умолчанию)
- CUDAExecutionProvider (требует GPU)
- OpenVINOExecutionProvider (Intel hardware)
- TensorrtExecutionProvider (NVIDIA TensorRT)
"""

import os
import sys
import argparse
import time
import json
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
import gc


@dataclass
class BenchmarkResult:
    """Результаты бенчмарка"""
    model_name: str
    model_size_mb: float
    
    # Latency (одиночный инференс)
    latency_mean_ms: float
    latency_std_ms: float
    latency_min_ms: float
    latency_max_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    
    # Throughput (батчевая обработка)
    throughput_fps: float
    batch_size: int
    
    # Конфигурация
    execution_provider: str
    num_threads: int
    warmup_iterations: int
    measure_iterations: int
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def summary(self) -> str:
        return (
            f"\n{'='*60}\n"
            f"Benchmark Results: {self.model_name}\n"
            f"{'='*60}\n"
            f"Model size:        {self.model_size_mb:.2f} MB\n"
            f"Provider:          {self.execution_provider}\n"
            f"Threads:           {self.num_threads}\n"
            f"\n--- Latency (single inference) ---\n"
            f"Mean:              {self.latency_mean_ms:.3f} ms\n"
            f"Std:               {self.latency_std_ms:.3f} ms\n"
            f"Min:               {self.latency_min_ms:.3f} ms\n"
            f"Max:               {self.latency_max_ms:.3f} ms\n"
            f"P50:               {self.latency_p50_ms:.3f} ms\n"
            f"P95:               {self.latency_p95_ms:.3f} ms\n"
            f"P99:               {self.latency_p99_ms:.3f} ms\n"
            f"\n--- Throughput (batch={self.batch_size}) ---\n"
            f"Throughput:        {self.throughput_fps:.1f} img/s\n"
            f"{'='*60}\n"
        )


class ONNXBenchmark:
    """Бенчмаркер для ONNX моделей"""
    
    SUPPORTED_PROVIDERS = [
        'CPUExecutionProvider',
        'CUDAExecutionProvider',
        'OpenVINOExecutionProvider',
        'TensorrtExecutionProvider',
        'DmlExecutionProvider',  # DirectML (Windows)
        'CoreMLExecutionProvider',  # Apple Silicon
    ]
    
    def __init__(
        self,
        model_path: str,
        providers: List[str] = None,
        num_threads: int = 4,
        enable_profiling: bool = False
    ):
        """
        Args:
            model_path: путь к ONNX модели
            providers: список execution providers
            num_threads: количество потоков для CPU
            enable_profiling: включить профилирование
        """
        self.model_path = Path(model_path)
        self.num_threads = num_threads
        self.enable_profiling = enable_profiling
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        # Определяем доступные providers
        available_providers = ort.get_available_providers()
        
        if providers is None:
            providers = ['CPUExecutionProvider']
        
        # Фильтруем только доступные
        self.providers = [p for p in providers if p in available_providers]
        
        if not self.providers:
            raise RuntimeError(f"No available providers from: {providers}")
        
        print(f"[INFO] Using providers: {self.providers}")
        
        # Создаём сессию
        self.session = self._create_session()
        
        # Информация о модели
        self.input_info = self.session.get_inputs()[0]
        self.output_info = self.session.get_outputs()[0]
        self.model_size_mb = os.path.getsize(model_path) / (1024 * 1024)
    
    def _create_session(self) -> ort.InferenceSession:
        """Создание ONNX Runtime сессии с оптимизациями"""
        sess_options = ort.SessionOptions()
        
        # CPU настройки
        sess_options.intra_op_num_threads = self.num_threads
        sess_options.inter_op_num_threads = self.num_threads
        
        # Оптимизации
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        # Профилирование
        if self.enable_profiling:
            sess_options.enable_profiling = True
        
        # Дополнительные оптимизации
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        
        return ort.InferenceSession(
            str(self.model_path),
            sess_options=sess_options,
            providers=self.providers
        )
    
    def _create_dummy_input(self, batch_size: int = 1) -> np.ndarray:
        """Создание тестового входа"""
        shape = list(self.input_info.shape)
        
        # Заменяем динамические размеры
        shape[0] = batch_size
        shape = [s if isinstance(s, int) else 112 for s in shape]
        
        return np.random.randn(*shape).astype(np.float32)
    
    def measure_latency(
        self,
        warmup_iterations: int = 50,
        measure_iterations: int = 200
    ) -> Dict[str, float]:
        """
        Измерение latency для одиночного инференса
        
        Args:
            warmup_iterations: количество прогревочных итераций
            measure_iterations: количество измерительных итераций
        
        Returns:
            словарь с метриками latency
        """
        dummy_input = self._create_dummy_input(batch_size=1)
        input_name = self.input_info.name
        
        # Прогрев
        print(f"[INFO] Warming up ({warmup_iterations} iterations)...")
        for _ in range(warmup_iterations):
            self.session.run(None, {input_name: dummy_input})
        
        # Измерение
        print(f"[INFO] Measuring latency ({measure_iterations} iterations)...")
        latencies = []
        
        for _ in range(measure_iterations):
            start = time.perf_counter()
            self.session.run(None, {input_name: dummy_input})
            elapsed = (time.perf_counter() - start) * 1000  # ms
            latencies.append(elapsed)
        
        latencies = np.array(latencies)
        
        return {
            'mean': float(np.mean(latencies)),
            'std': float(np.std(latencies)),
            'min': float(np.min(latencies)),
            'max': float(np.max(latencies)),
            'p50': float(np.percentile(latencies, 50)),
            'p95': float(np.percentile(latencies, 95)),
            'p99': float(np.percentile(latencies, 99)),
        }
    
    def measure_throughput(
        self,
        batch_size: int = 32,
        duration_seconds: float = 10.0
    ) -> float:
        """
        Измерение throughput (img/s)
        
        Args:
            batch_size: размер батча
            duration_seconds: длительность измерения
        
        Returns:
            throughput в изображениях в секунду
        """
        dummy_input = self._create_dummy_input(batch_size=batch_size)
        input_name = self.input_info.name
        
        # Прогрев
        for _ in range(10):
            self.session.run(None, {input_name: dummy_input})
        
        # Измерение
        print(f"[INFO] Measuring throughput (batch={batch_size}, duration={duration_seconds}s)...")
        
        total_images = 0
        start_time = time.perf_counter()
        
        while (time.perf_counter() - start_time) < duration_seconds:
            self.session.run(None, {input_name: dummy_input})
            total_images += batch_size
        
        elapsed = time.perf_counter() - start_time
        throughput = total_images / elapsed
        
        return throughput
    
    def run_benchmark(
        self,
        warmup_iterations: int = 50,
        measure_iterations: int = 200,
        batch_size: int = 32,
        throughput_duration: float = 10.0
    ) -> BenchmarkResult:
        """
        Полный бенчмарк модели
        
        Returns:
            BenchmarkResult со всеми метриками
        """
        print(f"\n{'='*60}")
        print(f"Benchmarking: {self.model_path.name}")
        print(f"Provider: {self.providers[0]}")
        print(f"Threads: {self.num_threads}")
        print(f"{'='*60}\n")
        
        # Latency
        latency_metrics = self.measure_latency(
            warmup_iterations=warmup_iterations,
            measure_iterations=measure_iterations
        )
        
        # Throughput
        throughput = self.measure_throughput(
            batch_size=batch_size,
            duration_seconds=throughput_duration
        )
        
        result = BenchmarkResult(
            model_name=self.model_path.name,
            model_size_mb=self.model_size_mb,
            latency_mean_ms=latency_metrics['mean'],
            latency_std_ms=latency_metrics['std'],
            latency_min_ms=latency_metrics['min'],
            latency_max_ms=latency_metrics['max'],
            latency_p50_ms=latency_metrics['p50'],
            latency_p95_ms=latency_metrics['p95'],
            latency_p99_ms=latency_metrics['p99'],
            throughput_fps=throughput,
            batch_size=batch_size,
            execution_provider=self.providers[0],
            num_threads=self.num_threads,
            warmup_iterations=warmup_iterations,
            measure_iterations=measure_iterations
        )
        
        return result


def benchmark_multiple_models(
    model_paths: List[str],
    output_dir: str = "./results",
    providers: List[str] = None,
    num_threads: int = 4,
    batch_size: int = 32
) -> Dict[str, BenchmarkResult]:
    """
    Бенчмарк нескольких моделей
    
    Args:
        model_paths: список путей к моделям
        output_dir: директория для результатов
        providers: execution providers
        num_threads: количество потоков
        batch_size: размер батча для throughput
    
    Returns:
        словарь с результатами для каждой модели
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    for model_path in model_paths:
        try:
            benchmark = ONNXBenchmark(
                model_path=model_path,
                providers=providers,
                num_threads=num_threads
            )
            
            result = benchmark.run_benchmark(batch_size=batch_size)
            results[Path(model_path).name] = result
            
            print(result.summary())
            
            # Освобождаем память
            del benchmark
            gc.collect()
            
        except Exception as e:
            print(f"[ERROR] Failed to benchmark {model_path}: {e}")
    
    # Сохраняем результаты
    results_dict = {name: r.to_dict() for name, r in results.items()}
    
    with open(output_path / "benchmark_results.json", 'w') as f:
        json.dump(results_dict, f, indent=2)
    
    print(f"\n[INFO] Results saved to: {output_path / 'benchmark_results.json'}")
    
    return results


def create_comparison_table(results: Dict[str, BenchmarkResult]) -> str:
    """Создание таблицы сравнения моделей"""
    
    if not results:
        return "No results to compare"
    
    # Заголовок
    header = (
        f"{'Model':<35} | {'Size (MB)':>10} | {'Latency (ms)':>12} | "
        f"{'P95 (ms)':>10} | {'Throughput':>12}"
    )
    separator = "-" * len(header)
    
    lines = [separator, header, separator]
    
    # Сортируем по latency
    sorted_results = sorted(results.items(), key=lambda x: x[1].latency_mean_ms)
    
    for name, result in sorted_results:
        line = (
            f"{name:<35} | {result.model_size_mb:>10.2f} | "
            f"{result.latency_mean_ms:>12.3f} | {result.latency_p95_ms:>10.3f} | "
            f"{result.throughput_fps:>10.1f}/s"
        )
        lines.append(line)
    
    lines.append(separator)
    
    # Относительное сравнение
    if len(sorted_results) > 1:
        baseline = sorted_results[0][1]
        lines.append("\nRelative comparison (vs fastest):")
        lines.append(separator)
        
        for name, result in sorted_results:
            speedup = baseline.latency_mean_ms / result.latency_mean_ms
            size_ratio = result.model_size_mb / baseline.model_size_mb
            lines.append(f"{name}: {speedup:.2f}x speed, {size_ratio:.2f}x size")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ONNX Model Benchmarking")
    parser.add_argument("--models", type=str, nargs="+", required=True,
                        help="Paths to ONNX models to benchmark")
    parser.add_argument("--output-dir", type=str, default="./results",
                        help="Output directory for results")
    parser.add_argument("--provider", type=str, default="CPUExecutionProvider",
                        help="Execution provider")
    parser.add_argument("--num-threads", type=int, default=4,
                        help="Number of CPU threads")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Batch size for throughput measurement")
    parser.add_argument("--warmup", type=int, default=50,
                        help="Warmup iterations")
    parser.add_argument("--iterations", type=int, default=200,
                        help="Measurement iterations")
    
    args = parser.parse_args()
    
    results = benchmark_multiple_models(
        model_paths=args.models,
        output_dir=args.output_dir,
        providers=[args.provider],
        num_threads=args.num_threads,
        batch_size=args.batch_size
    )
    
    # Выводим сравнительную таблицу
    print("\n" + create_comparison_table(results))


if __name__ == "__main__":
    main()
