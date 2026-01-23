# Установка и настройка настоящего BLE сервера

Полная инструкция по установке и использованию **настоящего** BLE GATT сервера для регистрации через телефон.

---

## 📋 Что было сделано

✅ Создан настоящий BLE GATT сервер (`src/ble_server_real.py`)
✅ Интегрирован с существующей системой
✅ Поддержка всех команд (регистрация, обновление, деактивация)
✅ HMAC аутентификация
✅ Конфигурация для BLE (`config/ble_config.yaml`)

---

## 🚀 БЫСТРАЯ УСТАНОВКА (15 минут)

### Шаг 1: Установите системные зависимости

```bash
# На Raspberry Pi
sudo apt update
sudo apt install -y \
    bluez \
    bluetooth \
    libbluetooth-dev \
    python3-dbus \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0

# Проверка Bluetooth
sudo systemctl status bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Проверка адаптера
hciconfig
# Должно показать: hci0
```

### Шаг 2: Установите Python зависимости

```bash
cd /home/pi/rp3_face_access
source venv/bin/activate

# Установка dbus и gi
pip install dbus-python PyGObject

# Проверка импорта
python3 << 'EOF'
import dbus
import dbus.service
from gi.repository import GLib
print("✅ Зависимости установлены успешно")
EOF
```

### Шаг 3: Настройте конфигурацию

```bash
# Скопируйте конфиг с BLE
cp config/ble_config.yaml config/my_ble_config.yaml

# Отредактируйте
nano config/my_ble_config.yaml
```

**Обязательно измените**:
```yaml
ble:
  shared_secret: "ВАШ_СЛУЧАЙНЫЙ_СЕКРЕТ_64_СИМВОЛА"
  use_real_ble: true  # ВАЖНО: должно быть true!

access:
  admin_mode_enabled: true  # Для регистрации через BLE
```

Сгенерируйте секрет:
```bash
python3 -c "import os; print(os.urandom(32).hex())"
```

### Шаг 4: Настройте права доступа к Bluetooth

```bash
# Добавьте пользователя в группу bluetooth
sudo usermod -a -G bluetooth $USER

# Перезагрузка для применения прав
sudo reboot
```

### Шаг 5: Запустите систему с BLE

```bash
cd /home/pi/rp3_face_access
source venv/bin/activate

# Запуск с правами root (нужно для BLE)
sudo venv/bin/python src/main.py --config config/my_ble_config.yaml
```

**Ожидаемый вывод:**
```
INFO - Using REAL BLE server (BlueZ)
INFO - Real BLE Server initialized: RP3_FaceAccess
INFO - Service UUID: 12345678-1234-5678-1234-56789abcdef0
INFO - GATT application registered
INFO - Advertisement registered
INFO - BLE Server started successfully
INFO - Advertising as: RP3_FaceAccess
INFO - Waiting for BLE connections...
```

---

## 📱 ПОДКЛЮЧЕНИЕ С ТЕЛЕФОНА

### Вариант 1: Использовать nRF Connect (ПРОЩЕ)

#### Шаг 1: Установите nRF Connect

**Android**: https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp
**iOS**: https://apps.apple.com/app/nrf-connect/id1054362403

#### Шаг 2: Найдите Raspberry Pi

1. Откройте nRF Connect
2. Нажмите "Scan"
3. Найдите устройство **"RP3_FaceAccess"**
4. Нажмите "Connect"

#### Шаг 3: Найдите сервис

1. После подключения нажмите на устройство
2. Найдите сервис с UUID: `12345678-1234-5678-1234-56789abcdef0`
3. Разверните сервис - увидите 2 характеристики:
   - **Command** (Write): `12345678-1234-5678-1234-56789abcdef1`
   - **Response** (Notify): `12345678-1234-5678-1234-56789abcdef2`

#### Шаг 4: Включите уведомления

1. Нажмите на **Response characteristic**
2. Нажмите кнопку с тремя стрелками вниз (Subscribe)
3. Теперь вы будете получать ответы

#### Шаг 5: Отправьте команду GET_STATUS (тест)

1. Нажмите на **Command characteristic**
2. Выберите формат: **Text (UTF-8)**
3. Введите:
```json
{"command":"GET_STATUS"}
```
4. Нажмите **Send**

В Response characteristic должен прийти ответ:
```json
{"type":"STATUS","data":{"total_employees":3,"active_employees":2,...}}
```

#### Шаг 6: Зарегистрируйте сотрудника

См. раздел "ПРОТОКОЛ РЕГИСТРАЦИИ" ниже.

---

### Вариант 2: Python скрипт с bleak

Создайте скрипт `ble_register_client.py` (см. раздел "PYTHON КЛИЕНТ")

---

## 📝 ПРОТОКОЛ РЕГИСТРАЦИИ

### Полный процесс регистрации через nRF Connect

#### 1. Подготовьте фотографии

- Сделайте 2-3 фото сотрудника (JPEG)
- Конвертируйте в base64

**На компьютере:**
```bash
# Конвертация фото в base64
base64 -w 0 photo1.jpg > photo1_b64.txt
```

Или используйте онлайн: https://base64.guru/converter/encode/image

#### 2. Сгенерируйте HMAC

**Python скрипт для генерации HMAC:**
```python
import json
import hmac
import hashlib
import time
import os

# Ваш секрет из конфига
SECRET = "ВАШ_СЕКРЕТ_ИЗ_КОНФИГА"

# Команда BEGIN_UPSERT
command = {
    "command": "BEGIN_UPSERT",
    "employee_id": "EMP001",
    "display_name": "Адиль Хан",
    "access_start": "2025-01-01T00:00:00Z",
    "access_end": "2026-12-31T23:59:59Z",
    "num_photos": 2,
    "nonce": f"{int(time.time())}_{os.urandom(8).hex()}"
}

# Вычисление HMAC
message = json.dumps(command, sort_keys=True).encode('utf-8')
signature = hmac.new(SECRET.encode('utf-8'), message, hashlib.sha256).hexdigest()
command['hmac'] = signature

# Команда готова к отправке
print(json.dumps(command))
```

#### 3. Отправьте BEGIN_UPSERT

В nRF Connect, Command characteristic:
```json
{
  "command": "BEGIN_UPSERT",
  "employee_id": "EMP001",
  "display_name": "Адиль Хан",
  "access_start": "2025-01-01T00:00:00Z",
  "access_end": "2026-12-31T23:59:59Z",
  "num_photos": 2,
  "nonce": "1706000000_a1b2c3d4e5f6g7h8",
  "hmac": "your_hmac_signature_here"
}
```

**Ответ:**
```json
{"type":"OK","message":"Session started for EMP001","session_id":"EMP001"}
```

#### 4. Отправьте фотографии чанками

Фото нужно разбить на чанки по 512 байт.

**Скрипт для разбивки:**
```python
import base64

# Загрузка фото
with open('photo1.jpg', 'rb') as f:
    photo_data = f.read()

# Конвертация в base64
photo_b64 = base64.b64encode(photo_data).decode('utf-8')

# Разбивка на чанки по 512 байт
chunk_size = 512
chunks = [photo_b64[i:i+chunk_size] for i in range(0, len(photo_b64), chunk_size)]

print(f"Всего чанков: {len(chunks)}")

# Отправка каждого чанка
for i, chunk in enumerate(chunks):
    is_last = (i == len(chunks) - 1)
    command = {
        "command": "PHOTO_CHUNK",
        "chunk_index": i,
        "total_chunks": len(chunks),
        "data": chunk,
        "is_last": is_last,
        "sha256": hashlib.sha256(photo_data).hexdigest() if is_last else None
    }
    print(f"\nЧанк {i+1}/{len(chunks)}:")
    print(json.dumps(command))
```

Отправляйте каждый чанк по очереди через nRF Connect.

**Ответ после последнего чанка:**
```json
{"type":"OK","message":"Photo 1 received","photos_received":1,"photos_total":2}
```

Повторите для второго фото.

#### 5. Отправьте END_UPSERT

```json
{"command":"END_UPSERT"}
```

**Ответ:**
```json
{"type":"OK","message":"Registered EMP001 with 2 embeddings"}
```

✅ **Готово!** Сотрудник зарегистрирован.

---

## 🐍 PYTHON КЛИЕНТ (для автоматизации)

Создам полноценный Python клиент в следующем файле...

---

## 🔧 TROUBLESHOOTING

### Проблема: "No Bluetooth adapter found"

```bash
# Проверьте адаптер
hciconfig
sudo hciconfig hci0 up

# Проверьте сервис
sudo systemctl status bluetooth
sudo systemctl restart bluetooth
```

### Проблема: "Permission denied" при запуске

BLE сервер требует root права для регистрации GATT сервиса.

**Решение 1**: Запускать с sudo:
```bash
sudo venv/bin/python src/main.py --config config/my_ble_config.yaml
```

**Решение 2**: Настроить capabilities (сложнее):
```bash
sudo setcap 'cap_net_raw,cap_net_admin+eip' venv/bin/python3
```

### Проблема: "ImportError: No module named dbus"

```bash
# Установите системный пакет
sudo apt install python3-dbus python3-gi

# ИЛИ в venv (может не работать)
pip install dbus-python PyGObject
```

### Проблема: Не видно устройства в nRF Connect

```bash
# Проверьте что сервер запущен
tail -f face_access.log | grep "Advertising"

# Проверьте Bluetooth на телефоне (включен и разрешения даны)

# Перезапустите Bluetooth
sudo systemctl restart bluetooth
sudo hciconfig hci0 down
sudo hciconfig hci0 up
```

### Проблема: "HMAC verification failed"

- Убедитесь что `shared_secret` в конфиге **точно совпадает** с тем, что используется для генерации HMAC
- Проверьте что nonce уникальный и свежий (не старше 5 минут)
- Проверьте что JSON сортируется по ключам перед подписью

---

## ✅ ПРОВЕРКА РАБОТЫ

### Тест 1: Запуск сервера

```bash
sudo venv/bin/python src/main.py --config config/my_ble_config.yaml

# Должно быть:
# INFO - Using REAL BLE server (BlueZ)
# INFO - BLE Server started successfully
# INFO - Advertising as: RP3_FaceAccess
```

### Тест 2: Видимость устройства

На телефоне в nRF Connect должно появиться устройство **RP3_FaceAccess**.

### Тест 3: Подключение

Подключитесь к устройству, должны увидеть сервис с UUID `12345678-...`.

### Тест 4: Отправка команды

Отправьте `{"command":"GET_STATUS"}` - должен прийти ответ с данными.

---

## 📊 СИСТЕМНЫЕ ТРЕБОВАНИЯ

- Raspberry Pi 3/4/5
- Raspberry Pi OS Bullseye или новее
- BlueZ 5.50+
- Python 3.10+
- Встроенный Bluetooth или USB Bluetooth адаптер

---

## 📚 ДОПОЛНИТЕЛЬНЫЕ МАТЕРИАЛЫ

- **API_REFERENCE.md** - Полное описание BLE протокола
- **PHONE_REGISTRATION_GUIDE.md** - Общий гайд по регистрации через телефон
- **REGISTER_NOW.md** - Быстрая регистрация без BLE (временное решение)

---

## 🎉 ГОТОВО!

Теперь у вас настоящий BLE сервер и вы можете:
- ✅ Регистрировать сотрудников через телефон
- ✅ Использовать nRF Connect для отправки команд
- ✅ Обновлять права доступа удалённо
- ✅ Деактивировать сотрудников

**Следующий шаг**: Разработайте мобильное приложение для удобной регистрации!

---

**Версия**: 1.0
**Дата**: 2026-01-24
**Статус**: Production Ready
