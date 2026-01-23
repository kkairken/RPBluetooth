# Регистрация пользователя через телефон по Bluetooth

Инструкция по регистрации сотрудников через мобильный телефон.

---

## 📱 ВАРИАНТЫ РЕГИСТРАЦИИ

### Вариант 1: Использовать готовые BLE приложения (САМЫЙ ПРОСТОЙ)
⏱️ Время: 5-10 минут на регистрацию
💰 Стоимость: Бесплатно
🔧 Сложность: Низкая

### Вариант 2: Python скрипт с bleak (для Android/компьютера)
⏱️ Время: 15 минут на настройку + регистрация
💰 Стоимость: Бесплатно
🔧 Сложность: Средняя

### Вариант 3: Разработать мобильное приложение
⏱️ Время: Несколько дней разработки
💰 Стоимость: Зависит от разработчика
🔧 Сложность: Высокая

---

## 🚀 ВАРИАНТ 1: Готовые BLE приложения (РЕКОМЕНДУЕТСЯ)

### Шаг 1: Установите BLE приложение на телефон

**Для iOS**:
- **LightBlue** (рекомендуется) - https://apps.apple.com/app/lightblue/id557428110
- **nRF Connect** - https://apps.apple.com/app/nrf-connect/id1054362403

**Для Android**:
- **nRF Connect** (рекомендуется) - https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp
- **BLE Scanner** - https://play.google.com/store/apps/details?id=com.macdom.ble.blescanner

### Шаг 2: Активируйте реальный BLE сервер на Raspberry Pi

⚠️ **ВАЖНО**: Сейчас BLE сервер в mock режиме и не работает!

**Нужно установить реальный BLE сервер:**

```bash
# На Raspberry Pi
sudo apt install -y bluez bluetooth libbluetooth-dev python3-dbus python3-gi

# Установите bleak для Python BLE
source venv/bin/activate
pip install bleak dbus-python

# Проверьте Bluetooth
sudo systemctl status bluetooth
hciconfig
```

### Шаг 3: Создайте реальный BLE сервер

К сожалению, текущая реализация - это mock. Для работы нужно:

**ПРОБЛЕМА**: `src/ble_server.py` на строках 422-473 - это заглушка.

**РЕШЕНИЕ**: Нужно реализовать настоящий BLE GATT сервер используя `bleak` или `bluezero`.

---

## ⚡ БЫСТРОЕ РЕШЕНИЕ: Скрипт для регистрации с компьютера

Пока нет реального BLE сервера, можно использовать **прямую регистрацию через скрипт**:

### Скрипт для регистрации с фото

```bash
# На Raspberry Pi
source venv/bin/activate

# Подготовьте 2-3 фото
# Фото должны быть в формате JPEG

# Запустите регистрацию
python tools/register_employee_direct.py \
  --employee-id "EMP001" \
  --display-name "Адиль Хан" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos photo1.jpg photo2.jpg photo3.jpg
```

Создам этот скрипт для вас...

---

## 💻 ВАРИАНТ 2: Python скрипт с bleak

Для использования с Android телефона или компьютера через Bluetooth.

### Требования
- Python 3.10+ на телефоне/компьютере с BLE
- Установленный `bleak`
- Raspberry Pi с запущенным BLE сервером

### Установка на компьютер/телефон

```bash
# На вашем компьютере или Android с Termux
pip install bleak pillow

# Скачайте скрипт ble_register_client.py (создам ниже)
```

Создам скрипт для BLE клиента...

---

## 📱 ВАРИАНТ 3: Мобильное приложение (Flutter/React Native)

Для полноценного использования нужно разработать приложение.

### Структура приложения

```
mobile_app/
├── screens/
│   ├── scan_devices.dart       # Поиск Raspberry Pi
│   ├── register_employee.dart  # Форма регистрации
│   └── take_photos.dart        # Камера для фото
├── services/
│   ├── ble_service.dart        # BLE коммуникация
│   └── hmac_service.dart       # HMAC подпись
└── models/
    └── employee.dart           # Модель сотрудника
```

### Технологии
- **Flutter** + `flutter_blue_plus` (рекомендуется)
- **React Native** + `react-native-ble-plx`
- **Native iOS/Android** + CoreBluetooth/Android BLE API

---

## 🔧 ВРЕМЕННОЕ РЕШЕНИЕ: Прямая регистрация без BLE

До реализации настоящего BLE сервера используйте **прямую регистрацию**.

### Метод 1: Через Python скрипт (на самой Raspberry Pi)

Создам скрипт `tools/register_employee_direct.py`:

```python
#!/usr/bin/env python3
"""
Прямая регистрация сотрудника без BLE.
Использует прямой доступ к базе данных и системе.
"""
import sys
sys.path.insert(0, 'src')

import argparse
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np

from db import Database
from face.detector import FaceDetector
from face.align import FaceAligner
from face.embedder_onnx import FaceEmbedder
from face.quality import FaceQualityChecker

def register_employee(
    employee_id: str,
    display_name: str,
    access_start: str,
    access_end: str,
    photo_paths: list,
    config_path: str = "config/usb_config.yaml"
):
    """Регистрация сотрудника с фотографиями."""

    print(f"🔄 Регистрация сотрудника: {employee_id} ({display_name})")

    # Загрузка конфигурации
    from config import load_config
    config = load_config(config_path)

    # Инициализация компонентов
    db = Database(config.database.path)
    detector = FaceDetector(
        detector_type=config.face.detector_type,
        scale_factor=config.face.detector_scale_factor,
        min_neighbors=config.face.detector_min_neighbors,
        min_face_size=config.face.detector_min_face_size
    )
    aligner = FaceAligner(output_size=(112, 112))
    embedder = FaceEmbedder(
        model_path=config.face.onnx_model_path,
        embedding_dim=config.face.embedding_dim
    )
    quality_checker = FaceQualityChecker(
        min_face_size=config.face.quality_min_face_size,
        blur_threshold=config.face.quality_blur_threshold
    )

    # Обработка фотографий
    embeddings = []
    for i, photo_path in enumerate(photo_paths):
        print(f"\n📸 Обработка фото {i+1}/{len(photo_paths)}: {photo_path}")

        # Загрузка изображения
        frame = cv2.imread(photo_path)
        if frame is None:
            print(f"   ❌ Не удалось загрузить {photo_path}")
            continue

        # Детекция лица
        faces = detector.detect(frame)
        if not faces:
            print(f"   ❌ Лицо не обнаружено")
            continue

        # Проверка качества
        valid, reason = quality_checker.validate_for_registration(frame, faces)
        if not valid:
            print(f"   ⚠️  Предупреждение: {reason}")
            # Продолжаем даже если качество не идеальное

        # Выравнивание
        aligned = aligner.align(frame, faces[0])
        if aligned is None:
            print(f"   ❌ Не удалось выровнять лицо")
            continue

        # Вычисление эмбеддинга
        embedding = embedder.compute_embedding(aligned)
        if embedding is None:
            print(f"   ❌ Не удалось вычислить эмбеддинг")
            continue

        embeddings.append(embedding)
        print(f"   ✅ Эмбеддинг извлечён (размерность: {len(embedding)})")

    if not embeddings:
        print("\n❌ Не удалось извлечь ни одного эмбеддинга!")
        return False

    print(f"\n✅ Извлечено {len(embeddings)} эмбеддингов")

    # Сохранение в базу данных
    print("\n💾 Сохранение в базу данных...")

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
    print(f"   ✅ Сотрудник добавлен: {employee_id}")

    # Удаление старых эмбеддингов
    db.delete_embeddings(employee_id)

    # Добавление новых эмбеддингов
    for emb in embeddings:
        db.add_embedding(employee_id, emb)
    print(f"   ✅ Добавлено {len(embeddings)} эмбеддингов")

    db.close()

    print(f"\n🎉 Регистрация завершена успешно!")
    print(f"   ID: {employee_id}")
    print(f"   Имя: {display_name}")
    print(f"   Период доступа: {access_start} - {access_end}")
    print(f"   Эмбеддингов: {len(embeddings)}")

    return True

def main():
    parser = argparse.ArgumentParser(
        description='Прямая регистрация сотрудника (без BLE)'
    )
    parser.add_argument('--employee-id', required=True, help='ID сотрудника')
    parser.add_argument('--display-name', required=True, help='Имя сотрудника')
    parser.add_argument('--access-start', required=True, help='Начало доступа (ISO 8601)')
    parser.add_argument('--access-end', required=True, help='Конец доступа (ISO 8601)')
    parser.add_argument('--photos', nargs='+', required=True, help='Пути к фотографиям')
    parser.add_argument('--config', default='config/usb_config.yaml', help='Путь к конфигу')

    args = parser.parse_args()

    # Проверка существования фотографий
    for photo in args.photos:
        if not Path(photo).exists():
            print(f"❌ Файл не найден: {photo}")
            sys.exit(1)

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
```

Этот скрипт создам в следующем сообщении.

---

## 📝 Протокол BLE (для разработки приложения)

### UUID сервиса и характеристик

```
Service UUID:        12345678-1234-5678-1234-56789abcdef0
Command Char UUID:   12345678-1234-5678-1234-56789abcdef1 (Write)
Response Char UUID:  12345678-1234-5678-1234-56789abcdef2 (Notify)
```

### Процесс регистрации

1. **Подключитесь к Raspberry Pi через BLE**
2. **Отправьте BEGIN_UPSERT** с HMAC подписью
3. **Отправьте фотографии** чанками (512 байт)
4. **Отправьте END_UPSERT** для завершения

Подробно см. `API_REFERENCE.md`

---

## ✅ ЧТО ДЕЛАТЬ СЕЙЧАС

### Немедленное решение (сегодня):

1. Используйте скрипт `register_employee_direct.py` (создам ниже)
2. Регистрируйте сотрудников напрямую на Raspberry Pi

### Краткосрочное решение (эта неделя):

1. Реализуйте настоящий BLE сервер с `bleak`
2. Используйте nRF Connect на телефоне для регистрации

### Долгосрочное решение (недели):

1. Разработайте мобильное приложение
2. Полноценная регистрация через телефон

---

## 🆘 НУЖНА ПОМОЩЬ?

**Выберите свой путь:**

✅ **"Мне нужно быстро зарегистрировать людей"**
   → Используйте `register_employee_direct.py`

✅ **"Хочу регистрировать через телефон, но нет времени на приложение"**
   → Установите nRF Connect + реализуйте настоящий BLE сервер

✅ **"Хочу полноценное мобильное приложение"**
   → Наймите разработчика или разрабатывайте сами

---

Я создам скрипт `register_employee_direct.py` для быстрой регистрации!
