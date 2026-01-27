#!/usr/bin/env python3
"""
Прямая регистрация сотрудника без BLE.
Использует прямой доступ к базе данных и системе распознавания лиц.

Использование:
    python tools/register_employee_direct.py \
        --employee-id "EMP001" \
        --display-name "Адиль Хан" \
        --access-start "2025-01-01T00:00:00Z" \
        --access-end "2026-12-31T23:59:59Z" \
        --photos photo1.jpg photo2.jpg photo3.jpg
"""
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import argparse
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np

from db import Database
from face.detector import FaceDetector
from face.align import FaceAligner
try:
    from face.embedder_onnx import FaceEmbedder
except ImportError:
    from face.embedder_opencv import FaceEmbedderOpenCV as FaceEmbedder
from face.quality import FaceQualityChecker


def register_employee(
    employee_id: str,
    display_name: str,
    access_start: str,
    access_end: str,
    photo_paths: list,
    config_path: str = "config/usb_config.yaml"
):
    """
    Регистрация сотрудника с фотографиями.

    Args:
        employee_id: ID сотрудника
        display_name: Отображаемое имя
        access_start: Начало периода доступа (ISO 8601)
        access_end: Конец периода доступа (ISO 8601)
        photo_paths: Список путей к фотографиям
        config_path: Путь к конфигурационному файлу

    Returns:
        True если успешно, False иначе
    """

    print("="*60)
    print(f"🔄 Регистрация сотрудника")
    print("="*60)
    print(f"ID: {employee_id}")
    print(f"Имя: {display_name}")
    print(f"Период: {access_start} до {access_end}")
    print(f"Фотографий: {len(photo_paths)}")
    print("="*60)

    # Загрузка конфигурации
    print("\n📋 Загрузка конфигурации...")
    from config import load_config
    try:
        config = load_config(config_path)
        print(f"   ✅ Конфиг загружен: {config_path}")
        print(f"   Модель: {config.face.onnx_model_path}")
    except Exception as e:
        print(f"   ❌ Ошибка загрузки конфига: {e}")
        return False

    # Инициализация компонентов
    print("\n🔧 Инициализация компонентов...")
    try:
        db = Database(config.database.path)
        print(f"   ✅ База данных: {config.database.path}")

        detector = FaceDetector(
            detector_type=config.face.detector_type,
            scale_factor=config.face.detector_scale_factor,
            min_neighbors=config.face.detector_min_neighbors,
            min_face_size=config.face.detector_min_face_size
        )
        print(f"   ✅ Детектор лиц: {config.face.detector_type}")

        aligner = FaceAligner(output_size=(112, 112))
        print(f"   ✅ Выравнивание лиц")

        embedder = FaceEmbedder(
            model_path=config.face.onnx_model_path,
            embedding_dim=config.face.embedding_dim
        )
        print(f"   ✅ ONNX модель загружена")

        quality_checker = FaceQualityChecker(
            min_face_size=config.face.quality_min_face_size,
            blur_threshold=config.face.quality_blur_threshold
        )
        print(f"   ✅ Проверка качества")

    except Exception as e:
        print(f"   ❌ Ошибка инициализации: {e}")
        return False

    # Обработка фотографий
    print("\n📸 Обработка фотографий...")
    embeddings = []

    for i, photo_path in enumerate(photo_paths):
        print(f"\n  [{i+1}/{len(photo_paths)}] {photo_path}")

        # Проверка существования файла
        if not Path(photo_path).exists():
            print(f"     ❌ Файл не найден")
            continue

        # Загрузка изображения
        frame = cv2.imread(photo_path)
        if frame is None:
            print(f"     ❌ Не удалось загрузить изображение")
            continue

        h, w = frame.shape[:2]
        print(f"     Размер: {w}x{h}")

        # Детекция лица
        faces = detector.detect(frame)
        if not faces:
            print(f"     ❌ Лицо не обнаружено")
            continue

        print(f"     ✅ Обнаружено лиц: {len(faces)}")

        # Используем самое большое лицо
        largest_face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = largest_face
        print(f"     Лицо: {w}x{h} пикселей")

        # Проверка качества
        valid, reason = quality_checker.validate_for_registration(frame, faces)
        if not valid:
            print(f"     ⚠️  Предупреждение: {reason}")
            print(f"     Продолжаем обработку...")

        # Выравнивание
        aligned = aligner.align(frame, largest_face)
        if aligned is None:
            print(f"     ❌ Не удалось выровнять лицо")
            continue

        print(f"     ✅ Лицо выровнено: 112x112")

        # Вычисление эмбеддинга
        embedding = embedder.compute_embedding(aligned)
        if embedding is None:
            print(f"     ❌ Не удалось вычислить эмбеддинг")
            continue

        embeddings.append(embedding)
        print(f"     ✅ Эмбеддинг извлечён (размерность: {len(embedding)})")

    # Проверка результатов
    if not embeddings:
        print("\n❌ ОШИБКА: Не удалось извлечь ни одного эмбеддинга!")
        print("\nВозможные причины:")
        print("  - Лица не обнаружены на фотографиях")
        print("  - Фотографии слишком маленькие или размытые")
        print("  - Неправильный формат файлов")
        print("\nРекомендации:")
        print("  - Используйте фотографии с чётким изображением лица")
        print("  - Размер лица должен быть не менее 80x80 пикселей")
        print("  - Фронтальные фотографии с хорошим освещением")
        return False

    print(f"\n✅ Успешно обработано {len(embeddings)} фотографий")

    # Сохранение в базу данных
    print("\n💾 Сохранение в базу данных...")

    try:
        # Преобразование дат
        start_dt = datetime.fromisoformat(access_start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(access_end.replace('Z', '+00:00'))

        # Добавление/обновление сотрудника
        db.upsert_employee(
            employee_id=employee_id,
            access_start=start_dt,
            access_end=end_dt,
            display_name=display_name,
            is_active=True
        )
        print(f"   ✅ Сотрудник добавлен/обновлён: {employee_id}")

        # Удаление старых эмбеддингов
        db.delete_embeddings(employee_id)
        print(f"   ✅ Старые эмбеддинги удалены")

        # Добавление новых эмбеддингов
        for emb in embeddings:
            db.add_embedding(employee_id, emb)
        print(f"   ✅ Добавлено {len(embeddings)} новых эмбеддингов")

        db.close()

    except Exception as e:
        print(f"   ❌ Ошибка сохранения: {e}")
        return False

    # Итог
    print("\n" + "="*60)
    print("🎉 РЕГИСТРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
    print("="*60)
    print(f"ID сотрудника:     {employee_id}")
    print(f"Имя:               {display_name}")
    print(f"Начало доступа:    {access_start}")
    print(f"Конец доступа:     {access_end}")
    print(f"Эмбеддингов:       {len(embeddings)}")
    print("="*60)
    print("\n✅ Сотрудник готов к распознаванию!")
    print("   Запустите систему и проверьте распознавание.")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Прямая регистрация сотрудника без BLE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Регистрация с 3 фотографиями
  python tools/register_employee_direct.py \\
      --employee-id "EMP001" \\
      --display-name "Адиль Хан" \\
      --access-start "2025-01-01T00:00:00Z" \\
      --access-end "2026-12-31T23:59:59Z" \\
      --photos photo1.jpg photo2.jpg photo3.jpg

  # Регистрация с указанием конфига
  python tools/register_employee_direct.py \\
      --employee-id "EMP002" \\
      --display-name "Иван Петров" \\
      --access-start "2025-06-01T00:00:00Z" \\
      --access-end "2025-12-31T23:59:59Z" \\
      --photos ivan1.jpg ivan2.jpg \\
      --config config/my_config.yaml

Требования к фотографиям:
  - Формат: JPEG или PNG
  - Минимальный размер: 640x480 пикселей
  - Размер лица: не менее 80x80 пикселей
  - Освещение: хорошее, равномерное
  - Количество: 2-5 фотографий одного человека
  - Разные ракурсы: фронтально, небольшой поворот
        """
    )

    parser.add_argument(
        '--employee-id',
        required=True,
        help='ID сотрудника (например: EMP001)'
    )
    parser.add_argument(
        '--display-name',
        required=True,
        help='Отображаемое имя сотрудника'
    )
    parser.add_argument(
        '--access-start',
        required=True,
        help='Начало периода доступа в формате ISO 8601 (например: 2025-01-01T00:00:00Z)'
    )
    parser.add_argument(
        '--access-end',
        required=True,
        help='Конец периода доступа в формате ISO 8601 (например: 2026-12-31T23:59:59Z)'
    )
    parser.add_argument(
        '--photos',
        nargs='+',
        required=True,
        help='Пути к фотографиям (минимум 1, рекомендуется 2-3)'
    )
    parser.add_argument(
        '--config',
        default='config/usb_config.yaml',
        help='Путь к конфигурационному файлу (по умолчанию: config/usb_config.yaml)'
    )

    args = parser.parse_args()

    # Проверка существования фотографий
    print("\n🔍 Проверка файлов...")
    all_files_exist = True
    for photo in args.photos:
        if Path(photo).exists():
            size = Path(photo).stat().st_size
            print(f"   ✅ {photo} ({size:,} байт)")
        else:
            print(f"   ❌ {photo} - ФАЙЛ НЕ НАЙДЕН!")
            all_files_exist = False

    if not all_files_exist:
        print("\n❌ Некоторые файлы не найдены. Проверьте пути.")
        sys.exit(1)

    # Проверка конфига
    if not Path(args.config).exists():
        print(f"\n❌ Конфигурационный файл не найден: {args.config}")
        sys.exit(1)

    # Регистрация
    success = register_employee(
        employee_id=args.employee_id,
        display_name=args.display_name,
        access_start=args.access_start,
        access_end=args.access_end,
        photo_paths=args.photos,
        config_path=args.config
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
