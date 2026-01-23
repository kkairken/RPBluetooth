# Быстрый деплой на Raspberry Pi 3

Краткая инструкция для деплоя системы распознавания лиц.

---

## 🚀 Шаг 1: Подготовка системы (10 мин)

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install -y \
    python3-pip python3-venv \
    libopencv-dev python3-opencv \
    libatlas-base-dev libjpeg-dev libopenblas-dev \
    gpiod libgpiod2 python3-libgpiod \
    bluez bluetooth libbluetooth-dev

# Добавление в группу gpio
sudo usermod -a -G gpio $USER

# ВАЖНО: Перезагрузка для применения прав
sudo reboot
```

---

## 📦 Шаг 2: Установка проекта (5 мин)

```bash
# Переход в директорию проекта
cd /home/pi/rp3_face_access

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка Python зависимостей
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🎯 Шаг 3: Скачивание ONNX модели (КРИТИЧНО!)

```bash
# Создайте директорию models
mkdir -p models
cd models

# ВАРИАНТ 1: Скачайте модель вручную
# Перейдите на: https://github.com/deepinsight/insightface
# Скачайте buffalo_m или buffalo_l
# Поместите .onnx файл в models/

# ВАРИАНТ 2: Используйте wget (если есть прямая ссылка)
# wget <URL_МОДЕЛИ>
# unzip buffalo_m.zip
# mv buffalo_m/w600k_r50.onnx insightface_medium.onnx

# Проверьте наличие модели
cd ..
ls -lh models/*.onnx
```

---

## ⚙️ Шаг 4: Настройка конфигурации (5 мин)

```bash
# Скопируйте шаблон конфига
cp config/usb_config.yaml config/my_config.yaml

# Сгенерируйте секретный ключ
echo "Секретный ключ для конфига:"
python3 -c "import os; print(os.urandom(32).hex())"
# Скопируйте вывод

# Отредактируйте конфиг
nano config/my_config.yaml
```

**Измените следующие параметры:**

```yaml
face:
  # ОБЯЗАТЕЛЬНО: Укажите правильное имя файла модели
  onnx_model_path: "models/ВАШ_ФАЙЛ.onnx"

ble:
  # ОБЯЗАТЕЛЬНО: Вставьте сгенерированный секрет
  shared_secret: "ВАШ_СЕКРЕТ_64_СИМВОЛА"

camera:
  type: usb
  device_id: 0  # Измените на 1 или 2 если камера не работает

lock:
  gpio_pin: 17
  mock_mode: true  # Для первых тестов БЕЗ реле
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 🧪 Шаг 5: Тестирование (5 мин)

### Тест 1: Проверка конфига

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from config import load_config

config = load_config('config/my_config.yaml')
print(f"✅ Конфиг загружен")
print(f"Модель: {config.face.onnx_model_path}")
print(f"Камера: {config.camera.type} (ID: {config.camera.device_id})")
print(f"Mock mode: {config.lock.mock_mode}")
EOF
```

### Тест 2: Проверка модели

```bash
python3 << 'EOF'
import onnxruntime as ort
import numpy as np

# ИЗМЕНИТЕ на имя вашей модели!
model_path = "models/ВАШ_ФАЙЛ.onnx"

session = ort.InferenceSession(model_path)
print("✅ Модель загружена")
print(f"Вход: {session.get_inputs()[0].shape}")
print(f"Выход: {session.get_outputs()[0].shape}")

# Тест инференса
dummy = np.random.randn(1, 3, 112, 112).astype(np.float32)
output = session.run(None, {session.get_inputs()[0].name: dummy})
print(f"✅ Инференс работает: {output[0].shape}")
EOF
```

### Тест 3: Проверка камеры

```bash
python3 << 'EOF'
import cv2

cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✅ Камера работает")
    ret, frame = cap.read()
    if ret:
        print(f"Разрешение: {frame.shape[1]}x{frame.shape[0]}")
    cap.release()
else:
    print("❌ Камера не работает, попробуйте device_id: 1 или 2")
EOF
```

### Тест 4: Первый запуск системы

```bash
source venv/bin/activate
python src/main.py --config config/my_config.yaml --log-level DEBUG
```

**Ожидаемый вывод:**
```
INFO - Initializing Face Access Control System...
INFO - Database initialized at data/access_control.db
INFO - USB camera 0 opened: 640x480 @ 15 FPS
INFO - ONNX model loaded: models/...
INFO - Lock controller in MOCK mode
INFO - System initialized successfully
INFO - Starting recognition loop
```

Остановите: `Ctrl+C`

---

## 👤 Шаг 6: Регистрация тестового пользователя

```bash
# Подготовьте 2-3 фотографии одного человека
mkdir -p test_photos
# Скопируйте фото в test_photos/ (через SCP или USB)

# Запустите систему в отдельном терминале
source venv/bin/activate
python src/main.py --config config/my_config.yaml

# В ДРУГОМ терминале запустите симулятор регистрации
python tools/ble_client_simulator.py \
  --action register \
  --employee-id TEST001 \
  --display-name "Тестовый Пользователь" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos test_photos/photo1.jpg test_photos/photo2.jpg \
  --shared-secret "ВАШ_СЕКРЕТ_ИЗ_КОНФИГА"

# Проверьте регистрацию
sqlite3 data/access_control.db "SELECT * FROM employees;"
```

---

## 🎭 Шаг 7: Тест распознавания

```bash
# Система уже запущена из Шага 6
# Встаньте перед камерой

# В другом терминале смотрите логи:
tail -f face_access.log

# Ожидаемый вывод при успехе:
# Access GRANTED: TEST001 (Тестовый Пользователь) - score: 0.752
# [MOCK] Lock state: UNLOCKED
```

---

## 🔄 Шаг 8: Автозапуск (опционально)

```bash
# Создайте systemd сервис
sudo nano /etc/systemd/system/face-access.service
```

Вставьте:
```ini
[Unit]
Description=Face Access Control System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rp3_face_access
Environment="PYTHONPATH=/home/pi/rp3_face_access/src"
ExecStart=/home/pi/rp3_face_access/venv/bin/python src/main.py --config /home/pi/rp3_face_access/config/my_config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохраните и активируйте:
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-access
sudo systemctl start face-access
sudo systemctl status face-access
```

Просмотр логов:
```bash
sudo journalctl -u face-access -f
```

---

## 🐛 Быстрое решение проблем

### Проблема: "ImportError: No module named 'config'"

```bash
# Запускайте с PYTHONPATH
cd /home/pi/rp3_face_access
export PYTHONPATH="$PWD/src:$PYTHONPATH"
python src/main.py --config config/my_config.yaml
```

### Проблема: "FileNotFoundError: models/..."

```bash
# Проверьте путь к модели
ls models/
grep onnx_model_path config/my_config.yaml
# Убедитесь что имя файла совпадает
```

### Проблема: "PermissionError: /dev/gpiochip0"

```bash
# Проверьте группу
groups
# Если нет gpio, добавьте и перезагрузитесь:
sudo usermod -a -G gpio $USER
sudo reboot

# Или временно включите mock режим в конфиге:
# lock.mock_mode: true
```

### Проблема: "Camera not opened"

```bash
# Проверьте доступные камеры
v4l2-ctl --list-devices

# Попробуйте разные ID
python3 -c "import cv2; [print(f'ID {i}: {cv2.VideoCapture(i).isOpened()}') for i in range(5)]"

# Обновите device_id в конфиге
```

### Проблема: Система медленная

```yaml
# Понизьте разрешение в конфиге
camera:
  width: 320
  height: 240

# Или измените frame_skip в src/main.py:225
# frame_skip = 3  # Обрабатывать каждый 3-й кадр
```

---

## ✅ Чек-лист готовности

- [ ] Система обновлена и перезагружена
- [ ] Зависимости установлены
- [ ] Пользователь в группе gpio
- [ ] ONNX модель скачана
- [ ] Конфиг настроен (путь к модели, секрет, camera ID)
- [ ] Все тесты пройдены (конфиг, модель, камера)
- [ ] Система запускается без ошибок
- [ ] Тестовый пользователь зарегистрирован
- [ ] Распознавание работает
- [ ] (Опционально) Systemd сервис настроен

---

## 📚 Дополнительная документация

- **DEPLOYMENT_CHECKLIST.md** - Полный чек-лист с решением проблем
- **RASPBERRY_PI_GUIDE.md** - Пошаговая инструкция (15 шагов)
- **TODO_USER.md** - Детальный чек-лист настройки
- **README.md** - Основная документация
- **QUICK_COMMANDS.md** - Шпаргалка команд

---

## 🆘 Нужна помощь?

1. Проверьте логи: `tail -f face_access.log`
2. Прочитайте **DEPLOYMENT_CHECKLIST.md**
3. Запустите диагностику (см. DEPLOYMENT_CHECKLIST.md)
4. Откройте issue на GitHub с логами

---

**Время деплоя**: ~30-40 минут
**Версия**: 1.0
**Дата**: 2026-01-24
