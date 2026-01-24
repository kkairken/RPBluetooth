# Команды установки - скопируйте и выполните

## 📋 ВСЕ КОМАНДЫ ДЛЯ КОПИРОВАНИЯ

### ШАГ 1: Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

---

### ШАГ 2: Установка МИНИМАЛЬНЫХ системных пакетов

**Скопируйте и выполните:**

```bash
sudo apt install -y \
  python3 python3-pip python3-venv python3-dev \
  build-essential gcc g++ make cmake pkg-config git \
  libjpeg-dev libpng-dev libtiff-dev \
  libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
  libatlas-base-dev libopenblas-dev liblapack-dev gfortran \
  bluez bluetooth libbluetooth-dev libdbus-1-dev libdbus-glib-1-dev \
  libgirepository1.0-dev libcairo2-dev gir1.2-glib-2.0 \
  libgpiod-dev libgpiod2 \
  v4l-utils sqlite3
```

**Время**: ~5-10 минут
**Размер**: ~150-200 MB

---

### ШАГ 3: Настройка прав доступа

```bash
sudo usermod -a -G gpio,bluetooth,video $USER
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

**⚠️ ВАЖНО: Перезагрузитесь после этого шага!**

```bash
sudo reboot
```

---

### ШАГ 4: После перезагрузки - создание venv

```bash
cd /home/pi/rp3_face_access
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

---

### ШАГ 5: Установка ВСЕХ Python зависимостей

**Скопируйте и выполните:**

```bash
source venv/bin/activate

pip install \
  "numpy>=1.23.0,<2.0.0" \
  "opencv-python>=4.8.0" \
  "opencv-contrib-python>=4.8.0" \
  "Pillow>=10.0.0" \
  "onnxruntime>=1.15.0" \
  "PyYAML>=6.0" \
  "dbus-python>=1.3.2" \
  "PyGObject>=3.42.0" \
  "bleak>=0.20.0" \
  "gpiod>=2.0.0" \
  "aiohttp>=3.8.0" \
  "pytest>=7.4.0" \
  "pytest-asyncio>=0.21.0" \
  "pytest-cov>=4.1.0" \
  "tqdm>=4.65.0" \
  "colorlog>=6.7.0"
```

**ИЛИ используйте файл requirements:**

```bash
pip install -r requirements-pip-only.txt
```

**Время**: ~10-15 минут на Raspberry Pi 3
**Размер**: ~300-400 MB

---

### ШАГ 6: Проверка установки

```bash
python3 << 'EOF'
print("Проверка установки...\n")

# Обязательные
try:
    import numpy
    print(f"✅ NumPy {numpy.__version__}")
except ImportError as e:
    print(f"❌ NumPy: {e}")

try:
    import cv2
    print(f"✅ OpenCV {cv2.__version__}")
except ImportError as e:
    print(f"❌ OpenCV: {e}")

try:
    import PIL
    print(f"✅ Pillow {PIL.__version__}")
except ImportError as e:
    print(f"❌ Pillow: {e}")

try:
    import yaml
    print(f"✅ PyYAML")
except ImportError as e:
    print(f"❌ PyYAML: {e}")

try:
    import onnxruntime
    print(f"✅ ONNX Runtime {onnxruntime.__version__}")
except ImportError as e:
    print(f"❌ ONNX Runtime: {e}")

# BLE
try:
    import dbus
    print(f"✅ dbus-python")
except ImportError as e:
    print(f"❌ dbus-python: {e}")

try:
    import gi
    from gi.repository import GLib
    print(f"✅ PyGObject (GLib)")
except ImportError as e:
    print(f"❌ PyGObject: {e}")

try:
    import bleak
    print(f"✅ bleak {bleak.__version__}")
except ImportError as e:
    print(f"❌ bleak: {e}")

# GPIO
try:
    import gpiod
    print(f"✅ gpiod")
except ImportError as e:
    print(f"❌ gpiod: {e}")

# Тесты
try:
    import pytest
    print(f"✅ pytest {pytest.__version__}")
except ImportError as e:
    print(f"❌ pytest: {e}")

print("\n🎉 Проверка завершена!")
EOF
```

---

### ШАГ 7: Создание директорий

```bash
mkdir -p data models logs photos
```

---

### ШАГ 8: Проверка оборудования

```bash
# Проверка камеры
v4l2-ctl --list-devices

# Проверка GPIO
gpiodetect
ls -l /dev/gpiochip0

# Проверка Bluetooth
hciconfig
sudo systemctl status bluetooth

# Проверка прав
groups
# Должно включать: gpio bluetooth video
```

---

## ✅ ФИНАЛЬНЫЙ ЧЕК-ЛИСТ

После выполнения всех команд проверьте:

- [ ] Система обновлена
- [ ] Минимальные системные пакеты установлены (~150-200 MB)
- [ ] Пользователь в группах gpio, bluetooth, video
- [ ] Система перезагружена
- [ ] Virtual environment создан
- [ ] Все Python пакеты установлены (~300-400 MB)
- [ ] Проверка импортов прошла успешно
- [ ] Директории созданы
- [ ] Оборудование работает

**ИТОГО размер**: ~500-600 MB (вместо ~850 MB с полными системными пакетами)

---

## 🚀 БЫСТРАЯ УСТАНОВКА ОДНОЙ КОМАНДОЙ

Если хотите всё сразу (после перезагрузки):

```bash
cd /home/pi/rp3_face_access && \
python3 -m venv venv && \
source venv/bin/activate && \
pip install --upgrade pip setuptools wheel && \
pip install \
  "numpy>=1.23.0,<2.0.0" \
  "opencv-python>=4.8.0" \
  "opencv-contrib-python>=4.8.0" \
  "Pillow>=10.0.0" \
  "onnxruntime>=1.15.0" \
  "PyYAML>=6.0" \
  "dbus-python>=1.3.2" \
  "PyGObject>=3.42.0" \
  "bleak>=0.20.0" \
  "gpiod>=2.0.0" \
  "aiohttp>=3.8.0" \
  "pytest>=7.4.0" \
  "pytest-asyncio>=0.21.0" && \
mkdir -p data models logs photos && \
echo "✅ Установка завершена!"
```

---

## 📝 СПИСОК ВСЕХ PIP ПАКЕТОВ

Основные:
- numpy>=1.23.0,<2.0.0
- opencv-python>=4.8.0
- opencv-contrib-python>=4.8.0
- Pillow>=10.0.0
- onnxruntime>=1.15.0
- PyYAML>=6.0

BLE:
- dbus-python>=1.3.2
- PyGObject>=3.42.0
- bleak>=0.20.0

GPIO:
- gpiod>=2.0.0

Async:
- aiohttp>=3.8.0

Testing:
- pytest>=7.4.0
- pytest-asyncio>=0.21.0
- pytest-cov>=4.1.0

Utilities:
- tqdm>=4.65.0
- colorlog>=6.7.0

---

## 📦 РАЗМЕРЫ

| Компонент | Размер |
|-----------|--------|
| Системные пакеты (минимум) | ~150-200 MB |
| Python venv | ~50 MB |
| Python пакеты (pip) | ~300-400 MB |
| **ИТОГО** | **~500-600 MB** |

**Сравнение с полной установкой:**
- Было: ~850 MB
- Стало: ~500-600 MB
- **Экономия: ~250-350 MB**

---

## 🎯 СЛЕДУЮЩИЕ ШАГИ

1. Скачайте ONNX модель (см. TODO_USER.md)
2. Настройте конфиг:
   ```bash
   cp config/usb_config.yaml config/my_config.yaml
   nano config/my_config.yaml
   ```
3. Запустите систему:
   ```bash
   source venv/bin/activate
   python src/main.py --config config/my_config.yaml
   ```

---

**Готово!** 🚀
