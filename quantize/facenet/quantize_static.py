#!/usr/bin/env python3
"""
quantize_static.py - Статическое квантование ONNX модели FaceNet

Статическое квантование (QDQ формат):
- И веса, и активации квантуются статически
- Требует калибровочный датасет для определения диапазонов активаций
- Вставляет QuantizeLinear/DequantizeLinear (QDQ) ноды
"""

import os
import sys
import argparse
import numpy as np
from pathlib import Path
from typing import List, Optional
import onnx
import onnxruntime as ort
from tqdm import tqdm


class FaceNetCalibrationDataReader:
    """
    CalibrationDataReader для FaceNet модели

    Подаёт препроцессированные изображения для калибровки диапазонов активаций
    """

    def __init__(
        self,
        calibration_images: List[np.ndarray],
        input_name: str = "input",
        batch_size: int = 1
    ):
        self.calibration_images = calibration_images
        self.input_name = input_name
        self.batch_size = batch_size
        self.index = 0

        print(f"[INFO] Calibration data reader initialized")
        print(f"  Total images: {len(calibration_images)}")
        print(f"  Batch size: {batch_size}")
        print(f"  Input name: {input_name}")

    def get_next(self) -> Optional[dict]:
        """Получение следующего батча для калибровки"""
        if self.index >= len(self.calibration_images):
            return None

        batch_end = min(self.index + self.batch_size, len(self.calibration_images))
        batch_images = self.calibration_images[self.index:batch_end]

        if self.batch_size == 1:
            batch = batch_images[0]
            if batch.ndim == 3:
                batch = np.expand_dims(batch, axis=0)
        else:
            batch = np.stack([img[0] if img.ndim == 4 else img for img in batch_images])

        self.index = batch_end
        return {self.input_name: batch.astype(np.float32)}

    def rewind(self):
        """Сброс итератора в начало"""
        self.index = 0


def prepare_calibration_data(
    images: List[np.ndarray],
    n_samples: int = 500,
    input_size: tuple = (160, 160),
    input_mean: float = 127.5,
    input_std: float = 128.0
) -> List[np.ndarray]:
    """Подготовка калибровочных данных для FaceNet"""
    import cv2

    print(f"[INFO] Preparing {min(n_samples, len(images))} calibration samples...")

    indices = np.random.permutation(len(images))[:n_samples]
    calibration_data = []

    for idx in tqdm(indices, desc="Preprocessing"):
        img = images[idx]

        if img.shape[:2] != (input_size[1], input_size[0]):
            img = cv2.resize(img, input_size, interpolation=cv2.INTER_LINEAR)

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32)
        img = (img - input_mean) / input_std
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0)

        calibration_data.append(img)

    return calibration_data


def quantize_static(
    input_model_path: str,
    output_model_path: str,
    calibration_data: List[np.ndarray],
    input_name: str = None,
    activation_type: str = "QUInt8",
    weight_type: str = "QInt8",
    quant_format: str = "QDQ",
    per_channel: bool = True,
    reduce_range: bool = False,
    calibration_method: str = "MinMax",
    extra_options: dict = None
) -> str:
    """Применение статического квантования к ONNX модели FaceNet"""
    from onnxruntime.quantization import (
        quantize_static as ort_quantize_static,
        QuantType,
        QuantFormat,
        CalibrationMethod
    )

    input_path = Path(input_model_path)
    output_path = Path(output_model_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Model not found: {input_model_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_name is None:
        model = onnx.load(input_model_path)
        input_name = model.graph.input[0].name

    act_type = QuantType.QUInt8 if activation_type == "QUInt8" else QuantType.QInt8
    wgt_type = QuantType.QInt8 if weight_type == "QInt8" else QuantType.QUInt8

    if quant_format.upper() == "QDQ":
        qformat = QuantFormat.QDQ
    else:
        qformat = QuantFormat.QOperator

    calib_methods = {
        "MinMax": CalibrationMethod.MinMax,
        "Entropy": CalibrationMethod.Entropy,
        "Percentile": CalibrationMethod.Percentile
    }
    calib_method = calib_methods.get(calibration_method, CalibrationMethod.MinMax)

    print(f"\n{'='*60}")
    print("FaceNet Static Quantization (QDQ)")
    print(f"{'='*60}")
    print(f"Input model:       {input_path}")
    print(f"Output model:      {output_path}")
    print(f"Activation type:   {activation_type}")
    print(f"Weight type:       {weight_type}")
    print(f"Quant format:      {quant_format}")
    print(f"Per-channel:       {per_channel}")
    print(f"Calibration:       {calibration_method}")
    print(f"Calibration data:  {len(calibration_data)} samples")
    print(f"{'='*60}\n")

    data_reader = FaceNetCalibrationDataReader(
        calibration_images=calibration_data,
        input_name=input_name,
        batch_size=1
    )

    extra_opts = extra_options or {}
    if "ActivationSymmetric" not in extra_opts:
        extra_opts["ActivationSymmetric"] = False
    if "WeightSymmetric" not in extra_opts:
        extra_opts["WeightSymmetric"] = True

    print("[INFO] Running static quantization with calibration...")

    try:
        ort_quantize_static(
            model_input=str(input_path),
            model_output=str(output_path),
            calibration_data_reader=data_reader,
            quant_format=qformat,
            activation_type=act_type,
            weight_type=wgt_type,
            per_channel=per_channel,
            reduce_range=reduce_range,
            calibrate_method=calib_method,
            extra_options=extra_opts
        )
        print(f"\n[OK] Quantized model saved to: {output_path}")

    except Exception as e:
        print(f"\n[ERROR] Quantization failed: {e}")
        print("[INFO] Retrying with fallback settings...")

        data_reader.rewind()

        ort_quantize_static(
            model_input=str(input_path),
            model_output=str(output_path),
            calibration_data_reader=data_reader,
            quant_format=qformat,
            activation_type=act_type,
            weight_type=wgt_type,
            per_channel=False,
            reduce_range=True,
            calibrate_method=CalibrationMethod.MinMax,
            extra_options=extra_opts
        )
        print(f"\n[OK] Quantized model saved (fallback): {output_path}")

    original_size = os.path.getsize(input_model_path) / (1024 * 1024)
    quantized_size = os.path.getsize(output_path) / (1024 * 1024)

    print(f"\n--- Size Comparison ---")
    print(f"Original:    {original_size:.2f} MB")
    print(f"Quantized:   {quantized_size:.2f} MB")
    print(f"Compression: {original_size / quantized_size:.2f}x")

    print("\n[INFO] Validating quantized model...")
    validate_quantized_model(str(output_path))

    return str(output_path)


def validate_quantized_model(model_path: str) -> bool:
    """Валидация статически квантованной модели"""

    try:
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        print("[OK] Model loads successfully")
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        return False

    input_info = session.get_inputs()[0]
    input_shape = [s if isinstance(s, int) else 1 for s in input_info.shape]
    dummy_input = np.random.randn(*input_shape).astype(np.float32)

    try:
        outputs = session.run(None, {input_info.name: dummy_input})
        print(f"[OK] Inference works. Output shape: {outputs[0].shape}")

        if np.isnan(outputs[0]).any():
            print("[WARN] Output contains NaN values!")
        if np.isinf(outputs[0]).any():
            print("[WARN] Output contains Inf values!")
    except Exception as e:
        print(f"[ERROR] Inference failed: {e}")
        return False

    model = onnx.load(model_path)
    qdq_ops = ["QuantizeLinear", "DequantizeLinear", "QLinearConv", "QLinearMatMul"]
    qdq_counts = {}

    for node in model.graph.node:
        if node.op_type in qdq_ops:
            qdq_counts[node.op_type] = qdq_counts.get(node.op_type, 0) + 1

    if qdq_counts:
        print(f"[INFO] QDQ operations found:")
        for op, count in qdq_counts.items():
            print(f"  {op}: {count}")

    return True


def load_calibration_from_lfw(lfw_dir: str, n_samples: int = 500) -> List[np.ndarray]:
    """Загрузка калибровочных данных из LFW"""
    import cv2

    # Добавляем insightface datasets в путь для переиспользования
    insightface_dir = Path(__file__).parent.parent / "insightface"
    sys.path.insert(0, str(insightface_dir))
    from datasets import LFWDataset

    dataset = LFWDataset(lfw_dir)
    image_paths = dataset.get_calibration_images(n_samples)

    images = []
    for path in tqdm(image_paths, desc="Loading images"):
        img = cv2.imread(path)
        if img is not None:
            images.append(img)

    return images


def main():
    parser = argparse.ArgumentParser(description="Static ONNX Quantization for FaceNet")
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--calibration-data", type=str, required=True,
                        help="Path to calibration data (LFW directory)")
    parser.add_argument("--n-calibration", type=int, default=500)
    parser.add_argument("--activation-type", type=str, default="QUInt8",
                        choices=["QUInt8", "QInt8"])
    parser.add_argument("--weight-type", type=str, default="QInt8",
                        choices=["QInt8", "QUInt8"])
    parser.add_argument("--quant-format", type=str, default="QDQ",
                        choices=["QDQ", "QOperator"])
    parser.add_argument("--calibration-method", type=str, default="MinMax",
                        choices=["MinMax", "Entropy", "Percentile"])
    parser.add_argument("--no-per-channel", action="store_true")
    parser.add_argument("--reduce-range", action="store_true")

    args = parser.parse_args()

    if args.output is None:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_int8_static_qdq.onnx")

    print("[INFO] Loading calibration data...")
    raw_images = load_calibration_from_lfw(args.calibration_data, args.n_calibration)

    calibration_data = prepare_calibration_data(
        images=raw_images,
        n_samples=args.n_calibration
    )

    quantize_static(
        input_model_path=args.input,
        output_model_path=args.output,
        calibration_data=calibration_data,
        activation_type=args.activation_type,
        weight_type=args.weight_type,
        quant_format=args.quant_format,
        per_channel=not args.no_per_channel,
        reduce_range=args.reduce_range,
        calibration_method=args.calibration_method
    )


if __name__ == "__main__":
    main()
