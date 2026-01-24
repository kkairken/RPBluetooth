# Сводка зависимостей - Requirements Summary

## ✅ ЧТО БЫЛО ДОБАВЛЕНО

### 1. Обновлен requirements.txt
Добавлены зависимости для настоящего BLE сервера:
- **dbus-python** >=1.3.2 - DBus для BlueZ
- **PyGObject** >=3.42.0 - GLib mainloop для BLE
- **bleak** >=0.20.0 - BLE клиент

### 2. Создан requirements-raspberry.txt
Специализированный файл для Raspberry Pi с:
- Подробными комментариями
- Рекомендациями по установке
- Опциональными зависимостями
- Зависимостями для разработки

### 3. Создан system-packages.txt
Список всех системных пакетов для apt:
- Python и инструменты
- OpenCV и обработка изображений
- Bluetooth и BLE (BlueZ, DBus, GLib)
- GPIO (libgpiod)
- RTSP камеры (ffmpeg)
- Утилиты

### 4. Создан install-raspberry.sh
Автоматический скрипт установки:
- Проверка системы
- Установка всех зависимостей
- Настройка прав доступа
- Проверка установки
- Тестирование оборудования

### 5. Создан INSTALL_DEPENDENCIES.md
Подробная инструкция по установке

---

## 📦 ФАЙЛЫ ЗАВИСИМОСТЕЙ

### requirements.txt
**Назначение**: Базовые зависимости + BLE
**Использование**: `pip install -r requirements.txt`

**Содержит**:
- numpy, opencv-python, Pillow
- onnxruntime
- PyYAML
- **dbus-python** (для BLE сервера)
- **PyGObject** (для BLE сервера)
- **bleak** (для BLE клиента)
- pytest, pytest-asyncio

### requirements-raspberry.txt
**Назначение**: Оптимизированные зависимости для Raspberry Pi
**Использование**: `pip install -r requirements-raspberry.txt`

**Особенности**:
- Подробные комментарии
- Рекомендации использовать системные пакеты
- Инструкции по установке сложных зависимостей
- Опциональные пакеты закомментированы

### system-packages.txt
**Назначение**: Системные пакеты для apt
**Использование**: `sudo apt install -y $(grep -v '^#' system-packages.txt | grep -v '^[[:space:]]*$')`

**Категории**:
- Python и dev tools
- Computer vision (OpenCV)
- Bluetooth и BLE (BlueZ, DBus, GLib)
- GPIO (libgpiod)
- Networking и media (ffmpeg)
- Database (sqlite3)
- Utilities

---

## 🚀 КАК УСТАНОВИТЬ

### Вариант 1: Автоматическая установка (РЕКОМЕНДУЕТСЯ)

```bash
cd /home/pi/rp3_face_access
./install-raspberry.sh
```

### Вариант 2: Ручная установка

```bash
# 1. Системные пакеты
sudo apt update
sudo apt install -y $(grep -v '^#' system-packages.txt | grep -v '^[[:space:]]*$')

# 2. Права доступа
sudo usermod -a -G gpio,bluetooth,video $USER
sudo reboot

# 3. Python окружение
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 4. Python зависимости
pip install -r requirements-raspberry.txt
```

---

## 📋 ПОЛНЫЙ СПИСОК ЗАВИСИМОСТЕЙ

### Python пакеты (pip)

#### Обязательные:
- **numpy** >=1.23.0,<2.0.0 - Численные вычисления
- **opencv-python** >=4.8.0 - Компьютерное зрение
- **Pillow** >=10.0.0 - Обработка изображений
- **onnxruntime** >=1.15.0 - ONNX модели для распознавания
- **PyYAML** >=6.0 - Конфигурационные файлы

#### BLE сервер:
- **dbus-python** >=1.3.2 - DBus для BlueZ
- **PyGObject** >=3.42.0 - GLib mainloop

#### BLE клиент:
- **bleak** >=0.20.0 - BLE клиент (ble_register_client.py)

#### Тестирование:
- **pytest** >=7.4.0
- **pytest-asyncio** >=0.21.0
- **pytest-cov** >=4.1.0

#### Опциональные:
- **mediapipe** >=0.10.0 - Продвинутая детекция лиц
- **bluezero** >=0.7.0 - Альтернативная BLE библиотека

### Системные пакеты (apt)

#### Python:
- python3, python3-pip, python3-venv, python3-dev
- build-essential

#### Computer Vision:
- python3-opencv, libopencv-dev
- libjpeg-dev, libpng-dev, libtiff-dev
- libatlas-base-dev, libopenblas-dev

#### Bluetooth:
- bluez, bluetooth, libbluetooth-dev
- python3-dbus, libdbus-1-dev, libdbus-glib-1-dev
- python3-gi, python3-gi-cairo, gir1.2-gtk-3.0
- libgirepository1.0-dev, libcairo2-dev

#### GPIO:
- gpiod, libgpiod2, libgpiod-dev
- python3-libgpiod

#### Media:
- ffmpeg, libavcodec-dev, libavformat-dev
- v4l-utils

#### Database:
- sqlite3, libsqlite3-dev

---

## 💡 ВАЖНЫЕ ЗАМЕЧАНИЯ

### 1. dbus-python и PyGObject

⚠️ **ВАЖНО**: Эти пакеты сложно устанавливать через pip!

**Рекомендация**: Используйте системные пакеты
```bash
sudo apt install python3-dbus python3-gi
```

**Если нужен pip** (для venv):
```bash
# Установите зависимости для компиляции
sudo apt install libdbus-1-dev libdbus-glib-1-dev \
                 libgirepository1.0-dev libcairo2-dev

pip install dbus-python PyGObject
```

### 2. OpenCV

**Рекомендация для Raspberry Pi**: Системный пакет быстрее
```bash
sudo apt install python3-opencv
```

**Альтернатива через pip**:
```bash
pip install opencv-python
```

### 3. libgpiod

**Рекомендация**: Системный пакет
```bash
sudo apt install python3-libgpiod
```

**Альтернатива через pip**:
```bash
sudo apt install libgpiod-dev
pip install libgpiod
```

### 4. Права доступа

После установки ОБЯЗАТЕЛЬНО:
```bash
sudo usermod -a -G gpio,bluetooth,video $USER
sudo reboot
```

---

## 🔍 ПРОВЕРКА УСТАНОВКИ

### Быстрая проверка:

```bash
source venv/bin/activate

python3 << 'EOF'
# Обязательные пакеты
import numpy
import cv2
import PIL
import yaml
import onnxruntime
print("✅ Основные пакеты OK")

# BLE (опционально)
try:
    import dbus, gi
    print("✅ BLE сервер OK")
except ImportError:
    print("⚠️  BLE сервер недоступен")

try:
    import bleak
    print("✅ BLE клиент OK")
except ImportError:
    print("⚠️  BLE клиент недоступен")
EOF
```

### Полная проверка:

```bash
# Запустите автоматическую проверку из install-raspberry.sh
source venv/bin/activate
python3 -c "$(grep -A 30 'packages_to_check =' install-raspberry.sh | tail -30)"
```

---

## 📊 РАЗМЕРЫ

| Компонент | Размер | Комментарий |
|-----------|--------|-------------|
| Системные пакеты | ~500 MB | Один раз |
| Python venv | ~50 MB | Базовое окружение |
| numpy, opencv | ~100 MB | Основные |
| onnxruntime | ~50 MB | ONNX модель |
| dbus, gi | ~30 MB | Для BLE |
| bleak | ~10 MB | BLE клиент |
| pytest | ~20 MB | Тесты |
| **ИТОГО** | **~760 MB** | Полная установка |

---

## 🎯 МИНИМАЛЬНАЯ УСТАНОВКА

Если нужно экономить место:

```bash
# Только основное (без BLE)
pip install numpy opencv-python Pillow onnxruntime PyYAML

# ~200 MB вместо 760 MB
```

**Что будет работать**:
- ✅ Распознавание лиц
- ✅ GPIO управление замком
- ✅ Прямая регистрация
- ❌ BLE сервер
- ❌ BLE клиент

---

## 🆘 TROUBLESHOOTING

### "No module named 'cv2'"
→ `sudo apt install python3-opencv`

### "No module named 'dbus'"
→ `sudo apt install python3-dbus`

### "No module named 'gi'"
→ `sudo apt install python3-gi`

### "Permission denied /dev/gpiochip0"
→ `sudo usermod -a -G gpio $USER && sudo reboot`

### pip установка dbus-python падает
→ Используйте системный пакет: `sudo apt install python3-dbus`

---

## ✅ ИТОГОВЫЙ ЧЕК-ЛИСТ

- [ ] requirements.txt обновлен (добавлены dbus, gi, bleak)
- [ ] requirements-raspberry.txt создан
- [ ] system-packages.txt создан
- [ ] install-raspberry.sh создан и исполняемый
- [ ] INSTALL_DEPENDENCIES.md создан
- [ ] Все зависимости задокументированы

---

## 📚 СВЯЗАННЫЕ ДОКУМЕНТЫ

- **INSTALL_DEPENDENCIES.md** - Подробная инструкция
- **RASPBERRY_PI_GUIDE.md** - Полный гайд по Pi
- **BLE_SETUP_GUIDE.md** - Настройка BLE
- **DEPLOY_QUICK.md** - Быстрый деплой

---

**Версия**: 1.0
**Дата**: 2026-01-24
**Статус**: Production Ready
