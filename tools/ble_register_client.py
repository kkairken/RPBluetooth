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

Protocol: Length-prefixed framing
┌─────────────────┬──────────────┬─────────────────────┐
│ Total Length    │ Sequence #   │ Payload (JSON)      │
│ 2 bytes BE      │ 1 byte       │ N bytes             │
└─────────────────┴──────────────┴─────────────────────┘
"""
import asyncio
import argparse
import json
import hmac
import hashlib
import struct
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

# Protocol constants
HEADER_SIZE = 3  # 2 bytes length + 1 byte sequence

# Параметры - ОЧЕНЬ консервативные для диагностики
CHUNK_SIZE = 256  # Маленькие чанки - меньше BLE пакетов
DEFAULT_MTU = 185
SLEEP_BETWEEN_CHUNKS_MS = 150  # Большая пауза между командами
INTER_PACKET_DELAY_MS = 30  # Большая пауза между BLE пакетами
DEVICE_NAME = "RP3_FaceAccess"
MAX_RETRIES = 3


class BLERegistrationClient:
    """BLE клиент для регистрации сотрудников"""

    def __init__(self, device_address: str, shared_secret: str, mtu: int = DEFAULT_MTU,
                 packet_delay_ms: int = INTER_PACKET_DELAY_MS):
        self.device_address = device_address
        self.shared_secret = shared_secret
        self.client: Optional[BleakClient] = None
        self.last_response = None
        self.response_event = asyncio.Event()
        self._seq = 0  # Sequence number for framing protocol
        self._mtu = mtu
        self._write_chunk_size = mtu - 3  # ATT header overhead
        self._disconnected = False
        self._packet_delay_ms = packet_delay_ms  # Delay between BLE packets

    def _on_disconnect(self, client):
        """Callback when device disconnects"""
        print("⚠️  Соединение разорвано!")
        self._disconnected = True
        self.response_event.set()  # Unblock any waiting responses

    async def ensure_connected(self) -> bool:
        """Check connection and reconnect if needed"""
        if self._disconnected or not self.client or not self.client.is_connected:
            print("🔄 Попытка переподключения...")
            try:
                await self.connect()
                self._disconnected = False
                return True
            except Exception as e:
                print(f"❌ Переподключение не удалось: {e}")
                return False
        return True

    def generate_hmac(self, command: dict) -> tuple[str, str]:
        """
        Генерация HMAC подписи для команды.

        Returns:
            tuple: (hmac_signature, nonce) - оба должны быть добавлены в команду
        """
        # Генерируем nonce
        nonce = f"{int(time.time())}_{os.urandom(8).hex()}"

        # Создаём копию с nonce для подписи
        command_with_nonce = command.copy()
        command_with_nonce['nonce'] = nonce

        # Сортируем ключи и сериализуем
        message = json.dumps(command_with_nonce, sort_keys=True).encode('utf-8')

        # Вычисляем HMAC
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        return signature, nonce

    def notification_handler(self, sender, data):
        """Обработчик уведомлений от сервера"""
        try:
            response_str = data.decode('utf-8')
            response = json.loads(response_str)
            self.last_response = response
            self.response_event.set()

            # Логируем только важные ответы (не ACK)
            resp_type = response.get('type')
            if resp_type in ('OK', 'ERROR', 'STATUS'):
                print(f"\n📩 Ответ: {json.dumps(response, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"\n❌ Ошибка обработки ответа: {e}")

    def clear_response(self):
        """Очистить предыдущий ответ перед новой операцией"""
        self.response_event.clear()
        self.last_response = None

    async def wait_for_response(self, timeout=10.0):
        """Ожидание ответа от сервера"""
        try:
            await asyncio.wait_for(self.response_event.wait(), timeout)
            return self.last_response
        except asyncio.TimeoutError:
            print(f"⏱️  Таймаут ожидания ответа")
            return None

    async def connect(self):
        """Подключение к BLE устройству"""
        print(f"🔄 Подключение к {self.device_address}...")
        self.client = BleakClient(
            self.device_address,
            disconnected_callback=self._on_disconnect
        )
        await self.client.connect()
        self._disconnected = False
        print(f"✅ Подключено к {self.device_address}")

        # Get negotiated MTU
        try:
            mtu = self.client.mtu_size
            if mtu and mtu > 23:
                self._mtu = mtu
                self._write_chunk_size = mtu - 3
                print(f"   MTU: {mtu} байт (chunk size: {self._write_chunk_size})")
        except Exception as e:
            print(f"   MTU: используем значение по умолчанию {self._mtu}")

        # Подписка на уведомления
        await self.client.start_notify(RESPONSE_CHAR_UUID, self.notification_handler)
        print(f"✅ Подписка на уведомления активирована")

    async def disconnect(self):
        """Отключение от BLE устройства"""
        if self.client and self.client.is_connected:
            await self.client.stop_notify(RESPONSE_CHAR_UUID)
            await self.client.disconnect()
            print("🔌 Отключено от устройства")

    async def send_command(self, command: dict, sleep_ms: int = SLEEP_BETWEEN_CHUNKS_MS):
        """
        Отправка команды на сервер с length-prefix фреймингом.

        Protocol:
        ┌─────────────────┬──────────────┬─────────────────────┐
        │ Total Length    │ Sequence #   │ Payload (JSON)      │
        │ 2 bytes BE      │ 1 byte       │ N bytes             │
        └─────────────────┴──────────────┴─────────────────────┘
        """
        # Ensure we're connected
        if not await self.ensure_connected():
            raise ConnectionError("Not connected to BLE device")

        # Serialize payload
        payload = json.dumps(command, separators=(',', ':')).encode('utf-8')

        # Build framed packet: header + payload
        header = struct.pack('>HB', len(payload), self._seq & 0xFF)
        packet = header + payload
        self._seq += 1

        cmd_name = command.get('command', 'unknown')
        num_ble_packets = (len(packet) + self._write_chunk_size - 1) // self._write_chunk_size
        print(f"📤 Отправка: {cmd_name} ({len(payload)} байт, seq={self._seq - 1}, {num_ble_packets} BLE пакетов)")

        # Split into MTU-sized chunks and send
        for i in range(0, len(packet), self._write_chunk_size):
            chunk = packet[i:i + self._write_chunk_size]

            for attempt in range(MAX_RETRIES):
                try:
                    # Check if still connected before write
                    if self._disconnected:
                        if not await self.ensure_connected():
                            raise ConnectionError("Connection lost during transfer")

                    await self.client.write_gatt_char(
                        COMMAND_CHAR_UUID,
                        chunk,
                        response=True
                    )
                    break  # Success
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        print(f"   ⚠️  Write retry {attempt + 1}/{MAX_RETRIES}: {e}")
                        await asyncio.sleep(0.2)
                        # Try to reconnect on retry
                        if self._disconnected:
                            await self.ensure_connected()
                    else:
                        raise

            # Delay between BLE packets within one command (critical for BlueZ stability)
            if i + self._write_chunk_size < len(packet):
                await asyncio.sleep(self._packet_delay_ms / 1000.0)

    async def send_command_no_wait(self, command: dict):
        """
        Отправка команды с BLE ACK, но без ожидания notification от сервера.
        Используется для streaming режима.
        """
        # Ensure we're connected
        if not await self.ensure_connected():
            raise ConnectionError("Not connected to BLE device")

        # Serialize payload
        payload = json.dumps(command, separators=(',', ':')).encode('utf-8')

        # Build framed packet: header + payload
        header = struct.pack('>HB', len(payload), self._seq & 0xFF)
        packet = header + payload
        self._seq += 1

        # Split into MTU-sized chunks and send WITH response (reliable delivery)
        for i in range(0, len(packet), self._write_chunk_size):
            chunk = packet[i:i + self._write_chunk_size]

            for attempt in range(MAX_RETRIES):
                try:
                    if self._disconnected:
                        if not await self.ensure_connected():
                            raise ConnectionError("Connection lost during transfer")

                    # Write WITH response for reliable delivery
                    await self.client.write_gatt_char(
                        COMMAND_CHAR_UUID,
                        chunk,
                        response=True  # Wait for BLE ACK
                    )
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(0.1)
                    else:
                        raise

            # Small delay between BLE packets
            if i + self._write_chunk_size < len(packet):
                await asyncio.sleep(self._packet_delay_ms / 1000.0)

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

        # Генерируем HMAC и nonce
        hmac_sig, nonce = self.generate_hmac(command)
        command['nonce'] = nonce
        command['hmac'] = hmac_sig

        self.clear_response()  # Очищаем перед отправкой
        await self.send_command(command)
        response = await self.wait_for_response()

        if response and response.get('type') == 'OK':
            print(f"✅ Сессия начата")
            return True
        else:
            print(f"❌ Ошибка: {response.get('message') if response else 'No response'}")
            return False

    async def send_photo(self, photo_path: str, photo_index: int,
                         chunk_size: int = CHUNK_SIZE,
                         sleep_ms: int = SLEEP_BETWEEN_CHUNKS_MS):
        """Отправка фотографии чанками — синхронный режим с подтверждением каждого чанка"""
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

        print(f"   Чанков: {total_chunks} (по {chunk_size} символов)")

        # Вычисление хэша
        photo_hash = hashlib.sha256(photo_data).hexdigest()

        # Синхронный режим: отправляем и ждём ACK на каждый чанк
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

            # Отправляем и ждём подтверждение
            self.clear_response()
            await self.send_command(command)
            response = await self.wait_for_response(timeout=10.0)

            if not response:
                print(f"\n   ❌ Нет ответа на чанк {i+1}/{total_chunks}")
                return False

            if response.get('type') == 'ERROR':
                print(f"\n   ❌ Ошибка: {response.get('message')}")
                return False

            # Показываем прогресс
            print(f"   📊 Прогресс: {i+1}/{total_chunks}", end='\r')

            if is_last and response.get('type') == 'OK':
                print(f"\n   ✅ Фото {photo_index} отправлено")
                return True

            # Пауза между чанками
            await asyncio.sleep(sleep_ms / 1000.0)

        return True

    async def end_upsert(self):
        """Завершение регистрации"""
        print(f"\n{'='*60}")
        print(f"✔️  END_UPSERT")
        print(f"{'='*60}")

        command = {"command": "END_UPSERT"}
        self.clear_response()
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
    parser.add_argument('--chunk-size', type=int, default=CHUNK_SIZE, help=f'Размер base64 чанка фото (по умолчанию: {CHUNK_SIZE})')
    parser.add_argument('--sleep-ms', type=int, default=SLEEP_BETWEEN_CHUNKS_MS, help=f'Пауза между командами в мс (по умолчанию: {SLEEP_BETWEEN_CHUNKS_MS})')
    parser.add_argument('--packet-delay-ms', type=int, default=INTER_PACKET_DELAY_MS, help=f'Пауза между BLE пакетами в мс (по умолчанию: {INTER_PACKET_DELAY_MS})')
    parser.add_argument('--mtu', type=int, default=DEFAULT_MTU, help=f'BLE MTU (по умолчанию: {DEFAULT_MTU}, будет перезаписан при подключении)')

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

    client = BLERegistrationClient(
        device_address, args.secret,
        mtu=args.mtu,
        packet_delay_ms=args.packet_delay_ms
    )

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
