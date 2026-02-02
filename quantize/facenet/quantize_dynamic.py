#!/usr/bin/env python3
"""
quantize_dynamic.py - Динамическое квантование ONNX модели FaceNet

Динамическое квантование:
- Веса квантуются статически (при сохранении модели)
- Активации квантуются динамически (во время инференса)
- Не требует калибровочного датасета
"""

import os
import sys
import argparse
from pathlib import Path
import onnx
from onnx import TensorProto
import onnxruntime as ort


def quantize_dynamic(
    input_model_path: str,
    output_model_path: str,
    weight_type: str = "QInt8",
    optimize_model: bool = True,
    per_channel: bool = False,
    reduce_range: bool = False,
    extra_options: dict = None
) -> str:
    """
    Применение динамического квантования к ONNX модели FaceNet

    Args:
        input_model_path: путь к FP32 модели
        output_model_path: путь для сохранения INT8 модели
        weight_type: тип квантования весов (QInt8 или QUInt8)
        optimize_model: применить оптимизации перед квантованием
        per_channel: использовать per-channel квантование весов
        reduce_range: уменьшить диапазон для лучшей совместимости
        extra_options: дополнительные опции

    Returns:
        путь к квантованной модели
    """
    from onnxruntime.quantization import quantize_dynamic as ort_quantize_dynamic
    from onnxruntime.quantization import QuantType

    input_path = Path(input_model_path)
    output_path = Path(output_model_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Model not found: {input_model_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if weight_type.upper() == "QINT8":
        quant_type = QuantType.QInt8
    elif weight_type.upper() == "QUINT8":
        quant_type = QuantType.QUInt8
    else:
        raise ValueError(f"Invalid weight type: {weight_type}")

    print(f"\n{'='*60}")
    print("FaceNet Dynamic Quantization")
    print(f"{'='*60}")
    print(f"Input model:  {input_path}")
    print(f"Output model: {output_path}")
    print(f"Weight type:  {weight_type}")
    print(f"Per-channel:  {per_channel}")
    print(f"Reduce range: {reduce_range}")
    print(f"{'='*60}\n")

    extra_opts = extra_options or {}

    if optimize_model:
        print("[INFO] Optimizing model before quantization...")
        optimized_path = output_path.parent / f"{input_path.stem}_optimized.onnx"

        sess_options = ort.SessionOptions()
        sess_options.optimized_model_filepath = str(optimized_path)
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED

        _ = ort.InferenceSession(
            str(input_path),
            sess_options=sess_options,
            providers=['CPUExecutionProvider']
        )

        if optimized_path.exists():
            input_to_quantize = str(optimized_path)
            print(f"[INFO] Optimized model saved to: {optimized_path}")
        else:
            input_to_quantize = str(input_path)
            print("[WARN] Optimization did not produce a new file, using original")
    else:
        input_to_quantize = str(input_path)

    print("[INFO] Applying dynamic quantization...")

    try:
        ort_quantize_dynamic(
            model_input=input_to_quantize,
            model_output=str(output_path),
            weight_type=quant_type,
            per_channel=per_channel,
            reduce_range=reduce_range,
            extra_options=extra_opts
        )
        print(f"[OK] Quantized model saved to: {output_path}")

    except Exception as e:
        print(f"[ERROR] Quantization failed: {e}")
        if per_channel:
            print("[INFO] Retrying without per-channel quantization...")
            ort_quantize_dynamic(
                model_input=input_to_quantize,
                model_output=str(output_path),
                weight_type=quant_type,
                per_channel=False,
                reduce_range=reduce_range,
                extra_options=extra_opts
            )
            print(f"[OK] Quantized model saved to: {output_path}")
        else:
            raise

    original_size = os.path.getsize(input_model_path) / (1024 * 1024)
    quantized_size = os.path.getsize(output_path) / (1024 * 1024)
    compression_ratio = original_size / quantized_size

    print(f"\n--- Size Comparison ---")
    print(f"Original:    {original_size:.2f} MB")
    print(f"Quantized:   {quantized_size:.2f} MB")
    print(f"Compression: {compression_ratio:.2f}x")

    print("\n[INFO] Validating quantized model...")
    validate_quantized_model(str(output_path))

    if optimize_model and Path(optimized_path).exists():
        os.remove(optimized_path)

    return str(output_path)


def validate_quantized_model(model_path: str):
    """Валидация квантованной модели"""
    import numpy as np

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
        output_shape = outputs[0].shape
        print(f"[OK] Inference works. Output shape: {output_shape}")
    except Exception as e:
        print(f"[ERROR] Inference failed: {e}")
        return False

    model = onnx.load(model_path)

    quantized_ops = set()
    all_ops = set()

    for node in model.graph.node:
        all_ops.add(node.op_type)
        if "Quant" in node.op_type or "QLinear" in node.op_type:
            quantized_ops.add(node.op_type)

    print(f"\n[INFO] Operations in model: {len(all_ops)}")
    if quantized_ops:
        print(f"[INFO] Quantized operations: {quantized_ops}")
    else:
        print("[WARN] No explicitly quantized operations found (weights may be quantized inline)")

    return True


def analyze_model_for_quantization(model_path: str):
    """Анализ модели для выбора стратегии квантования"""
    model = onnx.load(model_path)

    print("\n=== FaceNet Model Analysis for Quantization ===\n")

    op_counts = {}
    for node in model.graph.node:
        op_counts[node.op_type] = op_counts.get(node.op_type, 0) + 1

    dynamic_friendly = ['MatMul', 'Gemm', 'Conv']
    static_friendly = ['Conv', 'MaxPool', 'AveragePool', 'BatchNormalization']

    print("Operation counts:")
    for op, count in sorted(op_counts.items(), key=lambda x: -x[1])[:15]:
        marker = ""
        if op in dynamic_friendly:
            marker = " [Dynamic]"
        if op in static_friendly:
            marker = " [Static]"
        print(f"  {op}: {count}{marker}")

    print("\n=== Recommendations ===")

    n_matmul = op_counts.get('MatMul', 0) + op_counts.get('Gemm', 0)
    n_conv = op_counts.get('Conv', 0)

    if n_matmul > n_conv * 2:
        print("Model is FC-heavy -> Dynamic quantization recommended")
    elif n_conv > n_matmul:
        print("Model is Conv-heavy -> Static quantization recommended")
    else:
        print("Mixed architecture -> Try both and compare")

    total_params = 0
    for initializer in model.graph.initializer:
        if initializer.data_type == TensorProto.FLOAT:
            params = 1
            for dim in initializer.dims:
                params *= dim
            total_params += params

    print(f"\nTotal FP32 parameters: {total_params:,}")
    print(f"Estimated FP32 size: {total_params * 4 / (1024*1024):.2f} MB")
    print(f"Estimated INT8 size: {total_params * 1 / (1024*1024):.2f} MB")


def main():
    parser = argparse.ArgumentParser(description="Dynamic ONNX Quantization for FaceNet")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to input FP32 ONNX model")
    parser.add_argument("--output", type=str, default=None,
                        help="Path for output INT8 model")
    parser.add_argument("--weight-type", type=str, default="QInt8",
                        choices=["QInt8", "QUInt8"])
    parser.add_argument("--per-channel", action="store_true")
    parser.add_argument("--reduce-range", action="store_true")
    parser.add_argument("--no-optimize", action="store_true")
    parser.add_argument("--analyze", action="store_true",
                        help="Only analyze model, don't quantize")

    args = parser.parse_args()

    if args.analyze:
        analyze_model_for_quantization(args.input)
        return

    if args.output is None:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_int8_dynamic.onnx")

    quantize_dynamic(
        input_model_path=args.input,
        output_model_path=args.output,
        weight_type=args.weight_type,
        optimize_model=not args.no_optimize,
        per_channel=args.per_channel,
        reduce_range=args.reduce_range
    )


if __name__ == "__main__":
    main()
