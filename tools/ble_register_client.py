#!/usr/bin/env python3
"""
BLE клиент для регистрации сотрудников через Bluetooth.
Использует bleak для подключения к BLE GATT серверу на Raspberry Pi.

Требования:
    pip install bleak pillow

Использование:
    python tools/ble_register_client.py \
        --employee-id "EMP001" \
        --display-name "Адиль Хан" \
        --access-start "2025-01-01T00:00:00Z" \
        --access-end "2026-12-31T23:59:59Z" \
        --photos photo1.jpg photo2.jpg \
        --secret "your_shared_secret"
"""
import asyncio
import argparse
import json
import hmac
import hashlib
import time
import os
import base64
from pathlib import Path
from typing import Optional, List

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("❌ Ошибка: bleak не установлен")
    print("   Установите: pip install bleak")
    exit(1)

# UUID сервиса и характеристик
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
COMMAND_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
RESPONSE_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"

# Параметры
CHUNK_SIZE = 60
SLEEP_BETWEEN_CHUNKS_MS = 20
DEVICE_NAME = "RP3_FaceAccess"


class BLERegistrationClient:
    """BLE клиент для регистрации сотрудников"""

    def __init__(self, device_address: str, shared_secret: str):
        self.device_address = device_address
        self.shared_secret = shared_secret
        self.client: Optional[BleakClient] = None
        self.last_response = None
        self.response_event = asyncio.Event()

    def generate_hmac(self, command: dict) -> str:
        """Генерация HMAC подписи для команды"""
        # Добавляем nonce
        command['nonce'] = f"{int(time.time())}_{os.urandom(8).hex()}"

        # Сортируем ключи и сериализуем
        message = json.dumps(command, sort_keys=True).encode('utf-8')

        # Вычисляем HMAC
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        return signature

    def notification_handler(self, sender, data):
        """Обработчик уведомлений от сервера"""
        try:
            response_str = data.decode('utf-8')
            self.last_response = json.loads(response_str)
            print(f"📩 Ответ: {json.dumps(self.last_response, indent=2, ensure_ascii=False)}")
            self.response_event.set()
        except Exception as e:
            print(f"❌ Ошибка обработки ответа: {e}")

    async def wait_for_response(self, timeout=10.0):
        """Ожидание ответа от сервера"""
        self.response_event.clear()
        try:
            await asyncio.wait_for(self.response_event.wait(), timeout)
            return self.last_response
        except asyncio.TimeoutError:
            print(f"⏱️  Таймаут ожидания ответа")
            return None

    async def connect(self):
        """Подключение к BLE устройству"""
        print(f"🔄 Подключение к {self.device_address}...")
        self.client = BleakClient(self.device_address)
        await self.client.connect()
        print(f"✅ Подключено к {self.device_address}")

        # Подписка на уведомления
        await self.client.start_notify(RESPONSE_CHAR_UUID, self.notification_handler)
        print(f"✅ Подписка на уведомления активирована")

    async def disconnect(self):
        """Отключение от BLE устройства"""
        if self.client and self.client.is_connected:
            await self.client.stop_notify(RESPONSE_CHAR_UUID)
            await self.client.disconnect()
            print("🔌 Отключено от устройства")

    async def send_command(self, command: dict):
        """Отправка команды на сервер"""
        command_json = json.dumps(command)
        command_bytes = command_json.encode('utf-8')

        print(f"📤 Отправка: {command.get('command')} ({len(command_bytes)} байт)")
        await self.client.write_gatt_char(COMMAND_CHAR_UUID, command_bytes, response=True)

    async def begin_upsert(self, employee_id: str, display_name: str,
                          access_start: str, access_end: str, num_photos: int):
        """Начало регистрации сотрудника"""
        print(f"\n{'='*60}")
        print(f"📝 BEGIN_UPSERT")
        print(f"{'='*60}")

        command = {
            "command": "BEGIN_UPSERT",
            "employee_id": employee_id,
            "display_name": display_name,
            "access_start": access_start,
            "access_end": access_end,
            "num_photos": num_photos
        }

        # Добавляем HMAC
        command['hmac'] = self.generate_hmac(command.copy())

        await self.send_command(command)
        response = await self.wait_for_response()

        if response and response.get('type') == 'OK':
            print(f"✅ Сессия начата")
            return True
        else:
            print(f"❌ Ошибка: {response.get('message') if response else 'No response'}")
            return False

    async def send_photo(self, photo_path: str, photo_index: int, chunk_size: int, sleep_ms: int):
        """Отправка фотографии чанками"""
        print(f"\n{'='*60}")
        print(f"📸 Отправка фото {photo_index}: {photo_path}")
        print(f"{'='*60}")

        # Загрузка фото
        with open(photo_path, 'rb') as f:
            photo_data = f.read()

        print(f"   Размер: {len(photo_data):,} байт")

        # Конвертация в base64
        photo_b64 = base64.b64encode(photo_data).decode('utf-8')

        # Разбивка на чанки
        chunks = [photo_b64[i:i+chunk_size] for i in range(0, len(photo_b64), chunk_size)]
        total_chunks = len(chunks)

        print(f"   Чанков: {total_chunks}")

        # Вычисление хэша
        photo_hash = hashlib.sha256(photo_data).hexdigest()

        # Отправка чанков
        for i, chunk in enumerate(chunks):
            is_last = (i == total_chunks - 1)

            command = {
                "command": "PHOTO_CHUNK",
                "chunk_index": i,
                "total_chunks": total_chunks,
                "data": chunk,
                "is_last": is_last
            }

            if is_last:
                command['sha256'] = photo_hash

            await self.send_command(command)
            response = await self.wait_for_response()

            if not response:
                print(f"   ❌ Нет ответа на чанк {i+1}/{total_chunks}")
                return False

            if response.get('type') == 'ERROR':
                print(f"   ❌ Ошибка: {response.get('message')}")
                return False

            if response.get('type') == 'PROGRESS':
                progress = response.get('progress', 0)
                print(f"   📊 Прогресс: {progress}% ({i+1}/{total_chunks})", end='\r')

            if is_last and response.get('type') == 'OK':
                print(f"\n   ✅ Фото {photo_index} отправлено ({response.get('photos_received')}/{response.get('photos_total')})")

            if sleep_ms > 0:
                await asyncio.sleep(sleep_ms / 1000.0)

        return True

    async def end_upsert(self):
        """Завершение регистрации"""
        print(f"\n{'='*60}")
        print(f"✔️  END_UPSERT")
        print(f"{'='*60}")

        command = {"command": "END_UPSERT"}
        await self.send_command(command)
        response = await self.wait_for_response(timeout=30.0)  # Больше времени на обработку

        if response and response.get('type') == 'OK':
            print(f"✅ {response.get('message')}")
            return True
        else:
            print(f"❌ Ошибка: {response.get('message') if response else 'No response'}")
            return False

    async def register_employee(self, employee_id: str, display_name: str,
                               access_start: str, access_end: str,
                               photo_paths: List[str],
                               chunk_size: int,
                               sleep_ms: int):
        """Полная регистрация сотрудника"""
        try:
            # 1. BEGIN_UPSERT
            success = await self.begin_upsert(
                employee_id, display_name,
                access_start, access_end,
                len(photo_paths)
            )
            if not success:
                return False

            # 2. Отправка фотографий
            for i, photo_path in enumerate(photo_paths, 1):
                success = await self.send_photo(photo_path, i, chunk_size=chunk_size, sleep_ms=sleep_ms)
                if not success:
                    return False

            # 3. END_UPSERT
            success = await self.end_upsert()
            return success

        except Exception as e:
            print(f"❌ Ошибка регистрации: {e}")
            return False


async def scan_for_device(device_name: str = DEVICE_NAME, timeout: float = 10.0):
    """Поиск BLE устройства"""
    print(f"🔍 Поиск устройства '{device_name}'...")

    devices = await BleakScanner.discover(timeout=timeout)

    for device in devices:
        if device.name and device_name in device.name:
            print(f"✅ Найдено: {device.name} ({device.address})")
            return device.address

    print(f"❌ Устройство '{device_name}' не найдено")
    print(f"\nДоступные устройства:")
    for device in devices:
        if device.name:
            print(f"  - {device.name} ({device.address})")

    return None


async def main():
    parser = argparse.ArgumentParser(
        description='BLE клиент для регистрации сотрудников',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:

  # Автоматический поиск устройства
  python tools/ble_register_client.py \\
      --employee-id "EMP001" \\
      --display-name "Адиль Хан" \\
      --access-start "2025-01-01T00:00:00Z" \\
      --access-end "2026-12-31T23:59:59Z" \\
      --photos photo1.jpg photo2.jpg \\
      --secret "your_shared_secret"

  # Указание MAC адреса устройства
  python tools/ble_register_client.py \\
      --device "AA:BB:CC:DD:EE:FF" \\
      --employee-id "EMP002" \\
      --display-name "Иван Петров" \\
      --access-start "2025-06-01T00:00:00Z" \\
      --access-end "2025-12-31T23:59:59Z" \\
      --photos ivan.jpg \\
      --secret "your_shared_secret"
        """
    )

    parser.add_argument('--device', help='MAC адрес BLE устройства (или будет найдено автоматически)')
    parser.add_argument('--employee-id', required=True, help='ID сотрудника')
    parser.add_argument('--display-name', required=True, help='Имя сотрудника')
    parser.add_argument('--access-start', required=True, help='Начало доступа (ISO 8601)')
    parser.add_argument('--access-end', required=True, help='Конец доступа (ISO 8601)')
    parser.add_argument('--photos', nargs='+', required=True, help='Пути к фотографиям')
    parser.add_argument('--secret', required=True, help='Shared secret для HMAC')
    parser.add_argument('--device-name', default=DEVICE_NAME, help=f'Имя BLE устройства (по умолчанию: {DEVICE_NAME})')
    parser.add_argument('--chunk-size', type=int, default=CHUNK_SIZE, help=f'Размер чанка (по умолчанию: {CHUNK_SIZE})')
    parser.add_argument('--sleep-ms', type=int, default=SLEEP_BETWEEN_CHUNKS_MS, help=f'Пауза между чанками в мс (по умолчанию: {SLEEP_BETWEEN_CHUNKS_MS})')

    args = parser.parse_args()

    # Проверка фотографий
    print("🔍 Проверка файлов...")
    for photo in args.photos:
        if not Path(photo).exists():
            print(f"❌ Файл не найден: {photo}")
            return 1
        size = Path(photo).stat().st_size
        print(f"   ✅ {photo} ({size:,} байт)")

    # Поиск устройства
    device_address = args.device
    if not device_address:
        device_address = await scan_for_device(args.device_name)
        if not device_address:
            return 1

    # Регистрация
    print(f"\n{'='*60}")
    print(f"🚀 НАЧАЛО РЕГИСТРАЦИИ")
    print(f"{'='*60}")
    print(f"Сотрудник: {args.display_name} ({args.employee_id})")
    print(f"Период: {args.access_start} - {args.access_end}")
    print(f"Фотографий: {len(args.photos)}")
    print(f"{'='*60}\n")

    client = BLERegistrationClient(device_address, args.secret)

    try:
        await client.connect()

        success = await client.register_employee(
            args.employee_id,
            args.display_name,
            args.access_start,
            args.access_end,
            args.photos,
            chunk_size=args.chunk_size,
            sleep_ms=args.sleep_ms
        )

        if success:
            print(f"\n{'='*60}")
            print(f"🎉 РЕГИСТРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
            print(f"{'='*60}")
            print(f"Сотрудник {args.employee_id} зарегистрирован")
            print(f"Теперь {args.display_name} может использовать систему")
            return 0
        else:
            print(f"\n{'='*60}")
            print(f"❌ РЕГИСТРАЦИЯ НЕ УДАЛАСЬ")
            print(f"{'='*60}")
            return 1

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        return 1

    finally:
        await client.disconnect()


if __name__ == '__main__':
    exit(asyncio.run(main()))
