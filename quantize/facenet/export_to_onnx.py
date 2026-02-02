#!/usr/bin/env python3
"""
export_to_onnx.py - Загрузка и экспорт FaceNet (InceptionResNetV1) в ONNX

1. Скачивает предобученную модель через facenet-pytorch
2. Экспортирует в ONNX формат
3. Валидирует структуру модели

Использование:
    python export_to_onnx.py
    python export_to_onnx.py --pretrained vggface2 --output-dir ./models
    python export_to_onnx.py --validate-only ./models/facenet_fp32.onnx
"""

import os
import sys
import argparse
from pathlib import Path


def export_facenet_to_onnx(
    pretrained: str = "vggface2",
    output_dir: str = "./models",
    opset_version: int = 14
) -> str:
    """
    Экспорт FaceNet (InceptionResNetV1) в ONNX

    Args:
        pretrained: предобученные веса ('vggface2' или 'casia-webface')
        output_dir: директория для сохранения
        opset_version: версия ONNX opset

    Returns:
        путь к сохранённой ONNX модели
    """
    try:
        import torch
        from facenet_pytorch import InceptionResnetV1
    except ImportError:
        print("Установите зависимости: pip install facenet-pytorch torch")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Загрузка FaceNet (pretrained={pretrained})...")

    # Загружаем модель
    model = InceptionResnetV1(pretrained=pretrained)
    model.eval()

    print(f"[INFO] Модель загружена: InceptionResNetV1")
    print(f"[INFO] Параметров: {sum(p.numel() for p in model.parameters()):,}")

    # Dummy input для трассировки (FaceNet использует 160x160)
    dummy_input = torch.randn(1, 3, 160, 160)

    # Путь для сохранения
    output_file = output_path / "facenet_fp32.onnx"

    print(f"[INFO] Экспорт в ONNX (opset={opset_version})...")

    torch.onnx.export(
        model,
        dummy_input,
        str(output_file),
        input_names=['input'],
        output_names=['embedding'],
        dynamic_axes={
            'input': {0: 'batch_size'},
            'embedding': {0: 'batch_size'}
        },
        opset_version=opset_version,
        do_constant_folding=True
    )

    print(f"[INFO] Модель сохранена: {output_file}")

    # Верификация
    print("[INFO] Проверка ONNX модели...")
    import onnx
    model_onnx = onnx.load(str(output_file))
    onnx.checker.check_model(model_onnx)
    print("[OK] ONNX модель валидна")

    # Проверка инференса
    import onnxruntime as ort
    import numpy as np

    session = ort.InferenceSession(str(output_file), providers=['CPUExecutionProvider'])
    test_input = np.random.randn(1, 3, 160, 160).astype(np.float32)
    outputs = session.run(None, {'input': test_input})

    print(f"[OK] Инференс работает. Output shape: {outputs[0].shape}")

    # Сравнение с PyTorch
    with torch.no_grad():
        torch_output = model(dummy_input).numpy()

    onnx_output = outputs[0]
    diff = np.abs(torch_output - onnx_output).max()
    print(f"[INFO] Max difference PyTorch vs ONNX: {diff:.6f}")

    file_size = os.path.getsize(output_file) / (1024 * 1024)
    print(f"[INFO] Размер файла: {file_size:.2f} MB")

    return str(output_file)


def validate_onnx_model(model_path: str):
    """Валидация ONNX модели"""
    import onnx
    from onnx import checker

    print(f"\n[INFO] Валидация модели: {model_path}")

    model = onnx.load(model_path)

    try:
        checker.check_model(model)
        print("[OK] Модель прошла валидацию ONNX")
    except Exception as e:
        print(f"[WARN] Ошибка валидации: {e}")

    print("\n=== Информация о модели ===")
    print(f"IR Version: {model.ir_version}")
    print(f"Producer: {model.producer_name} {model.producer_version}")
    print(f"Opset: {[op.version for op in model.opset_import]}")

    print("\n--- Входы ---")
    for inp in model.graph.input:
        shape = [d.dim_value if d.dim_value else d.dim_param
                 for d in inp.type.tensor_type.shape.dim]
        dtype = inp.type.tensor_type.elem_type
        dtype_name = onnx.TensorProto.DataType.Name(dtype)
        print(f"  {inp.name}: {shape} ({dtype_name})")

    print("\n--- Выходы ---")
    for out in model.graph.output:
        shape = [d.dim_value if d.dim_value else d.dim_param
                 for d in out.type.tensor_type.shape.dim]
        dtype = out.type.tensor_type.elem_type
        dtype_name = onnx.TensorProto.DataType.Name(dtype)
        print(f"  {out.name}: {shape} ({dtype_name})")

    op_counts = {}
    for node in model.graph.node:
        op_counts[node.op_type] = op_counts.get(node.op_type, 0) + 1

    print("\n--- Операции (топ-10) ---")
    for op, count in sorted(op_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {op}: {count}")

    file_size = os.path.getsize(model_path) / (1024 * 1024)
    print(f"\n[INFO] Размер файла: {file_size:.2f} MB")

    return model


def main():
    parser = argparse.ArgumentParser(description="Экспорт FaceNet в ONNX")
    parser.add_argument("--pretrained", type=str, default="vggface2",
                        choices=["vggface2", "casia-webface"],
                        help="Предобученные веса")
    parser.add_argument("--output-dir", type=str, default="./models",
                        help="Директория для сохранения")
    parser.add_argument("--validate-only", type=str, default=None,
                        help="Только валидация существующей модели")

    args = parser.parse_args()

    if args.validate_only:
        validate_onnx_model(args.validate_only)
    else:
        model_path = export_facenet_to_onnx(args.pretrained, args.output_dir)
        validate_onnx_model(model_path)


if __name__ == "__main__":
    main()
