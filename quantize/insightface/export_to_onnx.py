#!/usr/bin/env python3
"""
export_to_onnx.py - Загрузка и подготовка ONNX модели InsightFace

InsightFace уже предоставляет модели в ONNX формате, поэтому этот скрипт:
1. Скачивает предобученную модель (buffalo_l / buffalo_s)
2. Извлекает recognition модель (ArcFace) в отдельный файл
3. Валидирует структуру модели
"""

import os
import sys
import argparse
import shutil
from pathlib import Path

def download_insightface_model(model_name: str = "buffalo_l", output_dir: str = "./models"):
    """
    Загрузка модели через insightface.app.FaceAnalysis
    
    Доступные модели:
    - buffalo_l: высокое качество, ResNet100 backbone
    - buffalo_s: компактная, MobileFaceNet backbone  
    - buffalo_sc: ещё компактнее
    """
    try:
        from insightface.app import FaceAnalysis
        import onnx
    except ImportError:
        print("Установите зависимости: pip install insightface onnx")
        sys.exit(1)
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"[INFO] Загрузка модели {model_name}...")
    
    # FaceAnalysis автоматически скачает модель
    app = FaceAnalysis(name=model_name, providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    
    # Путь к скачанным моделям
    model_pack_path = Path.home() / ".insightface" / "models" / model_name
    
    # Ищем recognition модель (обычно w600k_r50.onnx или подобная)
    rec_model_path = None
    for f in model_pack_path.glob("*.onnx"):
        if "det" not in f.name.lower():  # Исключаем detection модели
            # Проверяем, что это recognition модель по выходу
            model = onnx.load(str(f))
            output_shape = model.graph.output[0].type.tensor_type.shape
            # Recognition модель обычно выдаёт эмбеддинг размером 512
            if len(output_shape.dim) == 2:
                dim = output_shape.dim[1].dim_value
                if dim in [128, 256, 512]:  # Типичные размеры эмбеддингов
                    rec_model_path = f
                    print(f"[INFO] Найдена recognition модель: {f.name} (embedding dim={dim})")
                    break
    
    if rec_model_path is None:
        print("[ERROR] Не удалось найти recognition модель")
        print("Доступные файлы:")
        for f in model_pack_path.glob("*.onnx"):
            print(f"  - {f.name}")
        sys.exit(1)
    
    # Копируем модель в рабочую директорию
    output_file = output_path / "insightface_fp32.onnx"
    shutil.copy(rec_model_path, output_file)
    print(f"[INFO] Модель сохранена: {output_file}")
    
    return str(output_file)


def validate_onnx_model(model_path: str):
    """Валидация ONNX модели"""
    import onnx
    from onnx import checker
    
    print(f"\n[INFO] Валидация модели: {model_path}")
    
    model = onnx.load(model_path)
    
    # Проверка корректности
    try:
        checker.check_model(model)
        print("[OK] Модель прошла валидацию ONNX")
    except Exception as e:
        print(f"[WARN] Ошибка валидации: {e}")
    
    # Информация о модели
    print("\n=== Информация о модели ===")
    print(f"IR Version: {model.ir_version}")
    print(f"Producer: {model.producer_name} {model.producer_version}")
    print(f"Opset: {[op.version for op in model.opset_import]}")
    
    # Входы
    print("\n--- Входы ---")
    for inp in model.graph.input:
        shape = [d.dim_value if d.dim_value else d.dim_param 
                 for d in inp.type.tensor_type.shape.dim]
        dtype = inp.type.tensor_type.elem_type
        dtype_name = onnx.TensorProto.DataType.Name(dtype)
        print(f"  {inp.name}: {shape} ({dtype_name})")
    
    # Выходы
    print("\n--- Выходы ---")
    for out in model.graph.output:
        shape = [d.dim_value if d.dim_value else d.dim_param 
                 for d in out.type.tensor_type.shape.dim]
        dtype = out.type.tensor_type.elem_type
        dtype_name = onnx.TensorProto.DataType.Name(dtype)
        print(f"  {out.name}: {shape} ({dtype_name})")
    
    # Подсчёт операций
    op_counts = {}
    for node in model.graph.node:
        op_counts[node.op_type] = op_counts.get(node.op_type, 0) + 1
    
    print("\n--- Операции (топ-10) ---")
    for op, count in sorted(op_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {op}: {count}")
    
    # Размер файла
    file_size = os.path.getsize(model_path) / (1024 * 1024)
    print(f"\n[INFO] Размер файла: {file_size:.2f} MB")
    
    return model


def export_from_pytorch(output_path: str = "./models/insightface_fp32.onnx"):
    """
    Альтернативный способ: экспорт из PyTorch (если нужна кастомная модель)
    
    Использует insightface.model_zoo для получения backbone
    """
    try:
        import torch
        from insightface.model_zoo import get_model
    except ImportError:
        print("Установите: pip install torch insightface")
        return None
    
    print("[INFO] Экспорт модели из PyTorch...")
    
    # Загружаем модель
    model = get_model('buffalo_l', providers=['CPUExecutionProvider'])
    
    # Dummy input для трассировки
    dummy_input = torch.randn(1, 3, 112, 112)
    
    # Экспорт в ONNX
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        input_names=['input'],
        output_names=['embedding'],
        dynamic_axes={
            'input': {0: 'batch_size'},
            'embedding': {0: 'batch_size'}
        },
        opset_version=14,
        do_constant_folding=True
    )
    
    print(f"[INFO] Модель экспортирована: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Подготовка ONNX модели InsightFace")
    parser.add_argument("--model", type=str, default="buffalo_l",
                        choices=["buffalo_l", "buffalo_s", "buffalo_sc"],
                        help="Название модели InsightFace")
    parser.add_argument("--output-dir", type=str, default="./models",
                        help="Директория для сохранения")
    parser.add_argument("--validate-only", type=str, default=None,
                        help="Только валидация существующей модели")
    
    args = parser.parse_args()
    
    if args.validate_only:
        validate_onnx_model(args.validate_only)
    else:
        model_path = download_insightface_model(args.model, args.output_dir)
        validate_onnx_model(model_path)


if __name__ == "__main__":
    main()
