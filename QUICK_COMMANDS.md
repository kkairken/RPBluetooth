# Шпаргалка команд

Быстрый справочник по основным командам для Raspberry Pi.

## 🚀 Быстрый старт (5 команд)

```bash
# 1. Установка зависимостей
sudo apt install -y python3-venv libopencv-dev python3-opencv gpiod libgpiod2 python3-libgpiod && sudo usermod -a -G gpio $USER && sudo reboot

# 2. После перезагрузки - создание окружения
cd /home/pi/rp3_face_access && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 3. Настройка конфига
cp config/usb_config.yaml config/my_config.yaml && nano config/my_config.yaml

# 4. Тест камеры
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('✅ OK' if cap.isOpened() else '❌ FAIL'); cap.release()"

# 5. Запуск системы
python src/main.py --config config/my_config.yaml
```

---

## 📦 Установка

```bash
# Системные пакеты
sudo apt update && sudo apt install -y \
    python3-pip python3-venv libopencv-dev python3-opencv \
    libatlas-base-dev libjpeg-dev libopenblas-dev \
    gpiod libgpiod2 python3-libgpiod

# GPIO права
sudo usermod -a -G gpio $USER && sudo reboot

# Python окружение
cd /home/pi/rp3_face_access
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Конфигурация

```bash
# Создать свой конфиг
cp config/usb_config.yaml config/my_config.yaml

# Редактировать
nano config/my_config.yaml

# Сгенерировать секретный ключ
python3 -c "import os; print(os.urandom(32).hex())"
```

---

## 🎥 Проверка камеры

```bash
# Список камер
v4l2-ctl --list-devices

# Тест камеры Python
python3 -c "import cv2; cap = cv2.VideoCapture(0); ret, frame = cap.read(); print(f'✅ {frame.shape}' if ret else '❌ FAIL'); cap.release()"

# Попробовать другие ID
python3 -c "import cv2; [print(f'ID {i}: {\"✅\" if cv2.VideoCapture(i).isOpened() else \"❌\"}') for i in range(5)]"
```

---

## 🔌 Проверка GPIO

```bash
# Список чипов
gpiodetect

# Информация о чипе
gpioinfo gpiochip0

# Проверка прав
ls -l /dev/gpiochip0

# Тест GPIO
python3 tools/test_gpio.py --line 17

# Установка значения (через командную строку)
gpioset gpiochip0 17=1  # HIGH
gpioset gpiochip0 17=0  # LOW
```

---

## 🤖 Запуск системы

```bash
# Активировать окружение
cd /home/pi/rp3_face_access
source venv/bin/activate

# Запуск с логами
python src/main.py --config config/my_config.yaml

# Запуск с отладкой
python src/main.py --config config/my_config.yaml --log-level DEBUG

# Остановка
Ctrl+C
```

---

## 👤 Регистрация сотрудника

```bash
# Симулятор регистрации
python tools/ble_client_simulator.py \
  --action register \
  --employee-id EMP001 \
  --display-name "Иван Иванов" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos photo1.jpg photo2.jpg photo3.jpg \
  --shared-secret "ВАШ_СЕКРЕТ"

# Деактивация
python tools/ble_client_simulator.py \
  --action deactivate \
  --employee-id EMP001 \
  --shared-secret "ВАШ_СЕКРЕТ"
```

---

## 📊 База данных

```bash
# Список сотрудников
sqlite3 data/access_control.db "SELECT * FROM employees;"

# Количество эмбеддингов
sqlite3 data/access_control.db "SELECT employee_id, COUNT(*) FROM embeddings GROUP BY employee_id;"

# Последние 10 логов
sqlite3 data/access_control.db "SELECT timestamp, employee_id, result, reason FROM audit_log ORDER BY timestamp DESC LIMIT 10;"

# Статистика
sqlite3 data/access_control.db "SELECT COUNT(*) as total, SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active FROM employees;"

# Экспорт логов
python src/main.py --config config/my_config.yaml --export-logs audit.json
```

---

## 📝 Логи

```bash
# Просмотр логов
tail -f face_access.log

# Последние 100 строк
tail -100 face_access.log

# Поиск ошибок
grep ERROR face_access.log

# Поиск по сотруднику
grep "EMP001" face_access.log

# Фильтр только GRANTED/DENIED
tail -f face_access.log | grep -E "GRANTED|DENIED"
```

---

## 🔄 Systemd сервис

```bash
# Статус
sudo systemctl status face-access.service

# Запуск
sudo systemctl start face-access.service

# Остановка
sudo systemctl stop face-access.service

# Перезапуск
sudo systemctl restart face-access.service

# Включить автозапуск
sudo systemctl enable face-access.service

# Отключить автозапуск
sudo systemctl disable face-access.service

# Логи
sudo journalctl -u face-access.service -f

# Последние 100 строк
sudo journalctl -u face-access.service -n 100 --no-pager
```

---

## 🧪 Тестирование

```bash
# Все тесты
python -m pytest tests/ -v

# Конкретный тест
python -m pytest tests/test_db.py -v

# С покрытием
python -m pytest tests/ --cov=src --cov-report=html
```

---

## 🔧 Диагностика

```bash
# Температура CPU
vcgencmd measure_temp

# CPU/RAM
top
# или
htop

# Версии
python3 --version
pip list | grep opencv
pip list | grep onnx

# Проверка модели ONNX
python3 -c "import onnxruntime as ort; s=ort.InferenceSession('models/ВАШ_ФАЙЛ.onnx'); print('✅ OK')"

# Свободное место
df -h
```

---

## 🛠️ Troubleshooting

```bash
# Камера не работает
sudo usermod -a -G video $USER && sudo reboot

# GPIO permission denied
sudo usermod -a -G gpio $USER && sudo reboot

# Переустановка зависимостей
pip install --force-reinstall -r requirements.txt

# Очистка кэша pip
pip cache purge

# Очистка логов
> face_access.log

# Сброс БД (ОСТОРОЖНО!)
rm data/access_control.db
```

---

## 📦 Backup

```bash
# Бэкап БД
cp data/access_control.db data/backup_$(date +%Y%m%d).db

# Бэкап конфига
cp config/my_config.yaml config/backup_config_$(date +%Y%m%d).yaml

# Полный бэкап
tar -czf backup_$(date +%Y%m%d).tar.gz data/ config/my_config.yaml face_access.log

# Восстановление
tar -xzf backup_20250122.tar.gz
```

---

## 🔄 Обновление системы

```bash
# Обновление ОС
sudo apt update && sudo apt upgrade -y

# Обновление Python пакетов
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --upgrade

# Перезагрузка
sudo reboot
```

---

## 📱 Полезные алиасы (добавить в ~/.bashrc)

```bash
# Добавить в ~/.bashrc:
alias face-start='cd /home/pi/rp3_face_access && source venv/bin/activate && python src/main.py --config config/my_config.yaml'
alias face-logs='tail -f /home/pi/rp3_face_access/face_access.log'
alias face-status='sudo systemctl status face-access.service'
alias face-restart='sudo systemctl restart face-access.service'
alias face-db='sqlite3 /home/pi/rp3_face_access/data/access_control.db'

# Применить изменения
source ~/.bashrc

# Теперь можно использовать:
# face-start    - запуск системы
# face-logs     - просмотр логов
# face-status   - статус сервиса
# face-restart  - перезапуск сервиса
# face-db       - открыть БД
```

---

## 📞 Быстрая диагностика

```bash
# Одной командой проверить всё
echo "=== Камера ===" && \
python3 -c "import cv2; print('✅' if cv2.VideoCapture(0).isOpened() else '❌')" && \
echo "=== GPIO ===" && \
gpiodetect && \
echo "=== Модель ===" && \
ls -lh models/*.onnx && \
echo "=== БД ===" && \
sqlite3 data/access_control.db "SELECT COUNT(*) FROM employees;" && \
echo "=== Память ===" && \
free -h && \
echo "=== Температура ===" && \
vcgencmd measure_temp
```

---

## 🎯 Часто используемые комбинации

```bash
# Проверка + запуск
gpiodetect && python3 tools/test_gpio.py --line 17 && python src/main.py --config config/my_config.yaml

# Бэкап + очистка логов + запуск
cp data/access_control.db data/backup_$(date +%Y%m%d).db && > face_access.log && python src/main.py --config config/my_config.yaml

# Статус всего
echo "Сотрудники:" && sqlite3 data/access_control.db "SELECT COUNT(*) FROM employees WHERE is_active=1;" && \
echo "Попытки (1ч):" && sqlite3 data/access_control.db "SELECT COUNT(*) FROM audit_log WHERE timestamp >= datetime('now', '-1 hour');" && \
vcgencmd measure_temp
```

---

**Сохраните эту шпаргалку на Raspberry Pi:**
```bash
nano ~/commands.txt
# Вставьте команды
```
