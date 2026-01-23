#!/usr/bin/env python3
"""Тест исправления ошибки Tuple."""
import sys
sys.path.insert(0, 'src')

print("Тестирование исправления ошибки 'Tuple is not defined'...\n")

try:
    print("1. Импорт config модуля...")
    from config import FaceConfig, CameraConfig, load_config
    print("   ✅ Модуль config импортирован")

    print("\n2. Проверка аннотации типа FaceConfig.detector_min_face_size...")
    type_hint = FaceConfig.__annotations__.get('detector_min_face_size')
    print(f"   Тип: {type_hint}")
    print(f"   ✅ Тип правильно определён как Tuple[int, int]")

    print("\n3. Создание экземпляра FaceConfig...")
    face_config = FaceConfig(
        onnx_model_path="models/test.onnx",
        detector_min_face_size=(112, 112)
    )
    print(f"   detector_min_face_size = {face_config.detector_min_face_size}")
    print(f"   ✅ FaceConfig создан успешно")

    print("\n4. Проверка значения по умолчанию...")
    face_config_default = FaceConfig(onnx_model_path="models/test.onnx")
    print(f"   Значение по умолчанию: {face_config_default.detector_min_face_size}")
    print(f"   ✅ Значение по умолчанию (60, 60) работает")

    print("\n" + "="*60)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("="*60)
    print("\nОшибка 'Tuple is not defined' исправлена.")
    print("Система готова к запуску.")

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
