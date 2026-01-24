# Установка зависимостей для Raspberry Pi

Полная инструкция по установке всех необходимых зависимостей.

---

## 🚀 БЫСТРАЯ УСТАНОВКА (Автоматическая)

### Вариант 1: Автоматический скрипт (РЕКОМЕНДУЕТСЯ)

```bash
# На Raspberry Pi
cd /home/pi/rp3_face_access

# Запустите скрипт установки
./install-raspberry.sh
```

**Что делает скрипт:**
- ✅ Проверяет версию Python (требуется 3.10+)
- ✅ Обновляет систему
- ✅ Устанавливает все системные пакеты
- ✅ Настраивает права GPIO и Bluetooth
- ✅ Создает виртуальное окружение
- ✅ Устанавливает Python зависимости
- ✅ Проверяет установку
- ✅ Тестирует оборудование

**Время:** ~30-40 минут

---

## 📝 РУЧНАЯ УСТАНОВКА (Пошагово)

### Шаг 1: Обновите систему

```bash
sudo apt update
sudo apt upgrade -y
```

### Шаг 2: Установите системные пакеты

#### Вариант A: Установить все из файла

```bash
cd /home/pi/rp3_face_access

# Установка всех пакетов из списка
sudo apt install -y $(grep -v '^#' system-packages.txt | grep -v '^[[:space:]]*$')
```

#### Вариант B: Установить по категориям

**Python и инструменты разработки:**
```bash
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential
```

**Компьютерное зрение (OpenCV):**
```bash
sudo apt install -y \
    python3-opencv \
    libopencv-dev \
    libjpeg-dev \
    libjpeg62-turbo-dev \
    libpng-dev \
    libtiff-dev \
    libatlas-base-dev \
    libopenblas-dev
```

**Bluetooth и BLE:**
```bash
sudo apt install -y \
    bluez \
    bluetooth \
    libbluetooth-dev \
    python3-dbus \
    libdbus-1-dev \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    libgirepository1.0-dev \
    libcairo2-dev
```

**GPIO:**
```bash
sudo apt install -y \
    gpiod \
    libgpiod2 \
    libgpiod-dev \
    python3-libgpiod
```

**RTSP камеры:**
```bash
sudo apt install -y \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    v4l-utils
```

### Шаг 3: Настройте права доступа

```bash
# Добавьте пользователя в группы
sudo usermod -a -G gpio $USER
sudo usermod -a -G bluetooth $USER
sudo usermod -a -G video $USER

# Включите Bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# ВАЖНО: Перезагрузитесь для применения прав
sudo reboot
```

### Шаг 4: Создайте виртуальное окружение

После перезагрузки:

```bash
cd /home/pi/rp3_face_access

# Создание venv
python3 -m venv venv

# Активация
source venv/bin/activate

# Обновление pip
pip install --upgrade pip setuptools wheel
```

### Шаг 5: Установите Python зависимости

#### Вариант A: Из requirements-raspberry.txt (рекомендуется)

```bash
source venv/bin/activate

# Установка всех зависимостей для Raspberry Pi
pip install -r requirements-raspberry.txt
```

**Время:** 10-15 минут на Raspberry Pi 3

#### Вариант B: Из requirements.txt (базовые зависимости)

```bash
source venv/bin/activate

pip install -r requirements.txt
```

#### Вариант C: Минимальная установка (без BLE)

```bash
source venv/bin/activate

# Только основные зависимости
pip install numpy opencv-python Pillow onnxruntime PyYAML pytest
```

### Шаг 6: Проверьте установку

```bash
source venv/bin/activate

# Тест импортов
python3 << 'EOF'
# Обязательные
import numpy
import cv2
import PIL
import yaml
import onnxruntime
import pytest
print("✅ Основные пакеты OK")

# BLE (опционально)
try:
    import dbus
    import gi
    from gi.repository import GLib
    print("✅ BLE сервер: dbus и gi OK")
except ImportError as e:
    print(f"⚠️  BLE сервер: {e} (опционально)")

try:
    import bleak
    print("✅ BLE клиент: bleak OK")
except ImportError:
    print("⚠️  BLE клиент: bleak не установлен (опционально)")

print("\n🎉 Все проверки пройдены!")
EOF
```

---

## 📦 СПИСОК ФАЙЛОВ ЗАВИСИМОСТЕЙ

### requirements.txt
Базовые зависимости + BLE поддержка

```bash
pip install -r requirements.txt
```

### requirements-raspberry.txt
Оптимизированные зависимости для Raspberry Pi

```bash
pip install -r requirements-raspberry.txt
```

### system-packages.txt
Список системных пакетов для apt

```bash
sudo apt install -y $(grep -v '^#' system-packages.txt | grep -v '^[[:space:]]*$')
```

---

## 🔧 РЕШЕНИЕ ПРОБЛЕМ

### Проблема: "No module named 'cv2'"

**Вариант 1**: Использовать системный OpenCV (рекомендуется)
```bash
sudo apt install python3-opencv
# Проверка
python3 -c "import cv2; print(cv2.__version__)"
```

**Вариант 2**: Установить через pip
```bash
pip install opencv-python
```

### Проблема: "No module named 'dbus'"

**Решение**: Использовать системный пакет
```bash
sudo apt install python3-dbus
# dbus-python сложно компилируется через pip
```

### Проблема: "No module named 'gi'"

**Решение**: Использовать системный пакет
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
# PyGObject сложно компилируется через pip
```

### Проблема: pip установка dbus-python или PyGObject падает

**Причина**: Нужны системные зависимости для компиляции

**Решение 1** (проще): Используйте системные пакеты
```bash
sudo apt install python3-dbus python3-gi
```

**Решение 2** (если нужен pip): Установите зависимости для компиляции
```bash
sudo apt install \
    libdbus-1-dev \
    libdbus-glib-1-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    pkg-config

pip install dbus-python PyGObject
```

### Проблема: "Permission denied" для GPIO

```bash
# Проверьте группы
groups $USER

# Если нет gpio, добавьте
sudo usermod -a -G gpio $USER

# Перезагрузитесь
sudo reboot
```

### Проблема: onnxruntime установка медленная на Pi 3

**Нормально!** ONNX Runtime большой пакет (~50MB) и компилируется долго.

Терпеливо ждите или используйте предкомпилированные wheel'ы.

---

## ✅ ПРОВЕРКА ПОСЛЕ УСТАНОВКИ

### Тест 1: Системные пакеты

```bash
# OpenCV
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"

# Bluetooth
hciconfig
sudo systemctl status bluetooth

# GPIO
gpiodetect
ls -l /dev/gpiochip0
```

### Тест 2: Python пакеты

```bash
source venv/bin/activate

# Список установленных пакетов
pip list

# Проверка основных пакетов
python3 << 'EOF'
packages = {
    'numpy': 'NumPy',
    'cv2': 'OpenCV',
    'PIL': 'Pillow',
    'yaml': 'PyYAML',
    'onnxruntime': 'ONNX Runtime',
}

for module, name in packages.items():
    try:
        mod = __import__(module)
        version = getattr(mod, '__version__', 'unknown')
        print(f'✅ {name:15} {version}')
    except ImportError:
        print(f'❌ {name:15} NOT INSTALLED')
EOF
```

### Тест 3: Оборудование

```bash
# Камера
v4l2-ctl --list-devices

# GPIO
gpiodetect

# Bluetooth
hciconfig
```

---

## 📊 РАЗМЕРЫ И ВРЕМЯ УСТАНОВКИ

| Компонент | Размер | Время (Pi 3) |
|-----------|--------|--------------|
| Системные пакеты | ~500 MB | 10-15 мин |
| Python venv | ~50 MB | 1 мин |
| Python пакеты | ~300 MB | 10-15 мин |
| **ИТОГО** | **~850 MB** | **~30 мин** |

---

## 🎯 МИНИМАЛЬНАЯ УСТАНОВКА

Если места мало или нужна только базовая функциональность:

```bash
# Системные (минимум)
sudo apt install -y \
    python3 python3-pip python3-venv \
    python3-opencv libatlas-base-dev \
    gpiod python3-libgpiod

# Python (минимум)
pip install numpy opencv-python Pillow onnxruntime PyYAML

# Размер: ~200 MB
# Время: ~10 мин
```

**Ограничения:**
- ❌ Нет BLE сервера
- ❌ Нет BLE клиента
- ✅ Основное распознавание работает
- ✅ GPIO работает
- ✅ Прямая регистрация работает

---

## 📚 ДОПОЛНИТЕЛЬНО

### Для разработки:

```bash
pip install black flake8 mypy pytest-cov
```

### Для продвинутых фич:

```bash
# MediaPipe (альтернативный детектор лиц)
pip install mediapipe

# Blue Zero (альтернативная BLE библиотека)
pip install bluezero
```

---

## 🆘 ПОМОЩЬ

Если что-то не работает:

1. Проверьте версию Python: `python3 --version` (нужна 3.10+)
2. Проверьте логи установки
3. Попробуйте установить проблемный пакет отдельно
4. Используйте системные пакеты вместо pip где возможно
5. Откройте issue на GitHub с полным выводом ошибки

---

## ✅ ИТОГОВЫЙ ЧЕК-ЛИСТ

- [ ] Система обновлена (`sudo apt update && upgrade`)
- [ ] Все системные пакеты установлены
- [ ] Пользователь в группах gpio, bluetooth, video
- [ ] Система перезагружена
- [ ] Виртуальное окружение создано
- [ ] Python зависимости установлены
- [ ] Импорты проверены (тест успешен)
- [ ] Оборудование проверено (camera, GPIO, BT)

---

**Готово к использованию!** 🎉

См. **DEPLOY_QUICK.md** для следующих шагов.
