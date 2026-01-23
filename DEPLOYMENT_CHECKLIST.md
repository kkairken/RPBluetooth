# Чек-лист деплоя и решение типичных проблем

Полный чек-лист проверки кода и конфигурации перед деплоем на Raspberry Pi 3.

---

## ⚠️ КРИТИЧЕСКИЕ ПРОБЛЕМЫ (Обязательно исправить)

### 1. ONNX модель отсутствует ❌

**Проблема**: В проекте нет ONNX модели, она должна быть скачана отдельно.

**Решение**:
```bash
# Скачайте InsightFace модель (buffalo_s, buffalo_m или buffalo_l)
cd models/
# Вариант 1: Скачать вручную с GitHub:
# https://github.com/deepinsight/insightface/tree/master/model_zoo

# Вариант 2: Использовать wget (пример)
wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip
unzip buffalo_m.zip
mv buffalo_m/w600k_r50.onnx insightface_medium.onnx
```

**Проверка**:
```bash
ls -lh models/*.onnx
# Должен быть файл размером 50-200 MB
```

---

### 2. Путь к модели в конфигурации ⚠️

**Проблема**: В `config/usb_config.yaml` указан путь `models/insightface_medium.onnx`, но ваша модель может называться по-другому.

**Решение**:
```bash
# Проверьте имя файла модели
ls models/

# Обновите config/usb_config.yaml:
nano config/usb_config.yaml
```

Измените:
```yaml
face:
  onnx_model_path: "models/ВАШ_ФАЙЛ.onnx"  # Укажите правильное имя
```

---

### 3. Секретный ключ по умолчанию 🔒

**Проблема**: В конфиге используется стандартный секрет `"change_this_secret_key_in_production"`.

**Решение**:
```bash
# Сгенерируйте случайный секрет
python3 -c "import os; print(os.urandom(32).hex())"
# Скопируйте вывод

# Обновите config
nano config/usb_config.yaml
```

Измените:
```yaml
ble:
  shared_secret: "ВАШ_НОВЫЙ_СЕКРЕТ_64_СИМВОЛА"
```

---

### 4. Импорты в main.py (потенциальная проблема)

**Проблема**: В `src/main.py` используются относительные импорты без явного указания пакета:
```python
from config import load_config  # Строка 16
from db import Database          # Строка 17
# и т.д.
```

**Текущий статус**: ✅ Код работает, но есть риск проблем при запуске.

**Решение (если возникнут проблемы)**:

**Вариант 1**: Запускать как модуль:
```bash
# Вместо:
python src/main.py --config config/usb_config.yaml

# Используйте:
python -m src.main --config config/usb_config.yaml
```

**Вариант 2**: Добавить src в PYTHONPATH:
```bash
export PYTHONPATH="/home/pi/rp3_face_access/src:$PYTHONPATH"
python src/main.py --config config/usb_config.yaml
```

**Вариант 3**: Установить как пакет:
```bash
pip install -e .
face-access --config config/usb_config.yaml
```

---

### 5. Signal handler в asyncio (проблема на Python 3.9)

**Проблема**: В `src/main.py:402-407` signal handler использует `asyncio.create_task()` вне event loop:
```python
def signal_handler(sig, frame):
    logger.info("Received shutdown signal")
    asyncio.create_task(system.stop())  # ❌ Может не работать
```

**Решение**: Код уже использует `asyncio.run()`, но при ошибках обработки сигналов может потребоваться исправление.

**Если появляется ошибка "no running event loop"**, обратитесь к разработчику для исправления.

---

## 📋 СИСТЕМНЫЕ ТРЕБОВАНИЯ

### Python версия

**Требуется**: Python 3.10+ (указано в setup.py:27)

**Проверка**:
```bash
python3 --version
# Должно быть: Python 3.10.x или 3.11.x
```

**Решение для Raspberry Pi OS**:
- Raspberry Pi OS Bullseye: Python 3.9 (не подходит!)
- Raspberry Pi OS Bookworm: Python 3.11 ✅

**Если у вас Python 3.9**:
```bash
# Обновите до Bookworm или соберите Python 3.10+ вручную
# (см. INSTALL_OFFLINE.md)
```

---

### Системные зависимости

**Проверка установки**:
```bash
# Проверьте наличие библиотек
dpkg -l | grep -E "python3-opencv|libgpiod|bluetooth"

# OpenCV
python3 -c "import cv2; print(cv2.__version__)"

# libgpiod
gpiodetect

# Python packages
python3 -c "import numpy, onnxruntime, yaml; print('OK')"
```

**Установка (если отсутствуют)**:
```bash
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    libopencv-dev \
    python3-opencv \
    libatlas-base-dev \
    libjpeg-dev \
    libopenblas-dev \
    gpiod \
    libgpiod2 \
    python3-libgpiod \
    bluez \
    bluetooth \
    libbluetooth-dev
```

---

## 🔧 ПРОБЛЕМЫ С ЗАПУСКОМ

### Проблема 1: "ImportError: No module named 'config'"

**Причина**: Python не может найти модули в src/.

**Решение**:
```bash
# Запускайте из корневой директории проекта
cd /home/pi/rp3_face_access
python -m src.main --config config/usb_config.yaml

# Или добавьте src в PYTHONPATH
export PYTHONPATH="$PWD/src:$PYTHONPATH"
python src/main.py --config config/usb_config.yaml
```

---

### Проблема 2: "Config file not found"

**Причина**: Неправильный путь к конфигу.

**Решение**:
```bash
# Используйте абсолютный путь
python src/main.py --config /home/pi/rp3_face_access/config/usb_config.yaml

# Или убедитесь что запускаете из корня проекта
cd /home/pi/rp3_face_access
python src/main.py --config config/usb_config.yaml
```

---

### Проблема 3: "FileNotFoundError: models/insightface_medium.onnx"

**Причина**: Модель не найдена или неправильный путь.

**Решение**:
```bash
# Проверьте наличие модели
ls -lh models/

# Убедитесь что путь в конфиге правильный
grep onnx_model_path config/usb_config.yaml

# Если путь относительный, запускайте из корня проекта
cd /home/pi/rp3_face_access
```

---

### Проблема 4: "PermissionError: /dev/gpiochip0"

**Причина**: Пользователь не в группе gpio.

**Решение**:
```bash
# Добавьте пользователя в группу gpio
sudo usermod -a -G gpio $USER

# Перезагрузитесь
sudo reboot

# После перезагрузки проверьте
groups
# Должно включать: gpio
```

**Временное решение (для тестов)**:
```yaml
# В config/usb_config.yaml включите mock режим
lock:
  mock_mode: true
```

---

### Проблема 5: "Camera not opened"

**Причина**: Неправильный device_id или камера не подключена.

**Решение**:
```bash
# Проверьте доступные камеры
v4l2-ctl --list-devices

# Попробуйте разные ID
python3 -c "import cv2; [print(f'ID {i}: {cv2.VideoCapture(i).isOpened()}') for i in range(5)]"

# Обновите device_id в конфиге
nano config/usb_config.yaml
# camera:
#   device_id: 1  # Измените на найденный ID
```

---

### Проблема 6: "sqlite3.OperationalError: unable to open database"

**Причина**: Директория data/ не существует или нет прав.

**Решение**:
```bash
# Создайте директорию
mkdir -p data

# Проверьте права
chmod 755 data
```

---

## 🧪 ТЕСТИРОВАНИЕ ПЕРЕД ДЕПЛОЕМ

### 1. Тест импортов

```bash
cd /home/pi/rp3_face_access
source venv/bin/activate

python3 << EOF
import sys
sys.path.insert(0, 'src')
from config import load_config
from db import Database
from camera.usb_camera import USBCamera
from face.detector import FaceDetector
from face.embedder_onnx import FaceEmbedder
from lock import LockController
print("✅ Все импорты работают")
EOF
```

---

### 2. Тест загрузки конфига

```bash
python3 << EOF
import sys
sys.path.insert(0, 'src')
from config import load_config

try:
    config = load_config('config/usb_config.yaml')
    print("✅ Конфиг загружен")
    print(f"   Модель: {config.face.onnx_model_path}")
    print(f"   Камера: {config.camera.type}")
    print(f"   GPIO pin: {config.lock.gpio_pin}")
    print(f"   Mock mode: {config.lock.mock_mode}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
EOF
```

---

### 3. Тест ONNX модели

```bash
python3 << EOF
import onnxruntime as ort
import numpy as np

model_path = "models/ВАШ_ФАЙЛ.onnx"  # Измените на свой файл

try:
    session = ort.InferenceSession(model_path)
    print("✅ Модель загружена")
    print(f"   Вход: {session.get_inputs()[0].shape}")
    print(f"   Выход: {session.get_outputs()[0].shape}")

    # Тест инференса
    dummy = np.random.randn(1, 3, 112, 112).astype(np.float32)
    output = session.run(None, {session.get_inputs()[0].name: dummy})
    print(f"✅ Инференс работает: {output[0].shape}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
EOF
```

---

### 4. Тест камеры

```bash
python3 << EOF
import cv2

device_id = 0  # Измените при необходимости
cap = cv2.VideoCapture(device_id)

if not cap.isOpened():
    print(f"❌ Камера {device_id} не открылась")
    print("   Попробуйте другой ID: 1, 2, ...")
else:
    print(f"✅ Камера {device_id} работает")
    ret, frame = cap.read()
    if ret and frame is not None:
        print(f"   Разрешение: {frame.shape[1]}x{frame.shape[0]}")
    cap.release()
EOF
```

---

### 5. Тест GPIO

```bash
# Только если есть доступ к GPIO (не в mock mode)
python3 tools/test_gpio.py --line 17
```

---

### 6. Полный тест запуска (сухой прогон)

```bash
# Запуск с DEBUG логами для проверки
python src/main.py --config config/usb_config.yaml --log-level DEBUG
# Нажмите Ctrl+C через 10 секунд

# Проверьте логи
tail -50 face_access.log
```

---

## 📝 РЕКОМЕНДАЦИИ ПО ДЕПЛОЮ

### 1. Используйте mock режим для первых тестов

```yaml
# config/usb_config.yaml
lock:
  mock_mode: true  # Включите для тестов без GPIO
```

---

### 2. Настройте systemd сервис

Создайте `/etc/systemd/system/face-access.service`:

```ini
[Unit]
Description=Face Access Control System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rp3_face_access
Environment="PYTHONPATH=/home/pi/rp3_face_access/src"
ExecStart=/home/pi/rp3_face_access/venv/bin/python src/main.py --config /home/pi/rp3_face_access/config/usb_config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активируйте:
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-access
sudo systemctl start face-access
sudo systemctl status face-access
```

---

### 3. Логирование

```bash
# Логи приложения
tail -f face_access.log

# Логи systemd
sudo journalctl -u face-access.service -f
```

---

### 4. Безопасность

```bash
# Защитите конфиг с секретом
chmod 600 config/usb_config.yaml

# Защитите базу данных
chmod 700 data/
```

---

## ✅ ФИНАЛЬНЫЙ ЧЕК-ЛИСТ

Перед запуском в production проверьте:

- [ ] ONNX модель скачана и находится в `models/`
- [ ] Путь к модели в конфиге правильный
- [ ] Секретный ключ изменен на случайный
- [ ] Python 3.10+ установлен
- [ ] Все системные зависимости установлены
- [ ] Пользователь в группе gpio (если используется GPIO)
- [ ] Камера работает (протестирована)
- [ ] База данных создается (директория data/ существует)
- [ ] Конфиг загружается без ошибок
- [ ] Модель загружается и делает инференс
- [ ] Импорты работают
- [ ] Mock режим протестирован
- [ ] GPIO протестирован (если не mock)
- [ ] Systemd сервис настроен
- [ ] Логирование работает
- [ ] Права доступа к файлам настроены

---

## 🆘 ПОЛУЧЕНИЕ ПОМОЩИ

### Сбор диагностической информации

```bash
#!/bin/bash
echo "=== System Info ==="
uname -a
python3 --version
cat /etc/os-release | grep VERSION

echo -e "\n=== Python Packages ==="
pip list | grep -E "numpy|opencv|onnx|yaml"

echo -e "\n=== GPIO ==="
gpiodetect
ls -l /dev/gpiochip0
groups $USER

echo -e "\n=== Camera ==="
v4l2-ctl --list-devices

echo -e "\n=== Project Files ==="
ls -lh models/
ls -ld data/

echo -e "\n=== Config ==="
grep -E "onnx_model_path|device_id|gpio_pin|mock_mode" config/usb_config.yaml

echo -e "\n=== Recent Logs ==="
tail -20 face_access.log
```

Запустите и отправьте вывод для диагностики.

---

## 📚 ДОПОЛНИТЕЛЬНЫЕ МАТЕРИАЛЫ

- **RASPBERRY_PI_GUIDE.md** - Пошаговая инструкция установки
- **TODO_USER.md** - Чек-лист настройки
- **README.md** - Основная документация
- **docs/GPIO_SETUP.md** - Детали по GPIO

---

**Версия**: 1.0
**Дата**: 2026-01-24
**Автор**: Claude Code Analysis
