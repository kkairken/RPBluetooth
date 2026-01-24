#!/usr/bin/env python3
"""
BLE клиент для получения статуса устройства.

Protocol: Length-prefixed framing
┌─────────────────┬──────────────┬─────────────────────┐
│ Total Length    │ Sequence #   │ Payload (JSON)      │
│ 2 bytes BE      │ 1 byte       │ N bytes             │
└─────────────────┴──────────────┴─────────────────────┘
"""
import asyncio
import json
import struct
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "RP3_FaceAccess"
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
COMMAND_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
RESPONSE_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"

HEADER_SIZE = 3  # 2 bytes length + 1 byte sequence

last_response = None
response_event = asyncio.Event()
seq_counter = 0


def notification_handler(sender, data):
    global last_response
    try:
        last_response = json.loads(data.decode("utf-8"))
        print("RESPONSE:", json.dumps(last_response, indent=2, ensure_ascii=False))
        response_event.set()
    except Exception as e:
        print("BAD RESPONSE:", e, data)


def build_framed_packet(command: dict, seq: int) -> bytes:
    """Build a length-prefixed framed packet"""
    payload = json.dumps(command, separators=(',', ':')).encode('utf-8')
    header = struct.pack('>HB', len(payload), seq & 0xFF)
    return header + payload


async def send_command(client: BleakClient, command: dict, seq: int):
    """Send a framed command"""
    packet = build_framed_packet(command, seq)
    mtu = getattr(client, 'mtu_size', 185)
    chunk_size = mtu - 3

    print(f"Sending: {command.get('command')} ({len(packet)} bytes, seq={seq})")

    for i in range(0, len(packet), chunk_size):
        chunk = packet[i:i + chunk_size]
        await client.write_gatt_char(
            COMMAND_CHAR_UUID,
            chunk,
            response=True
        )
        if i + chunk_size < len(packet):
            await asyncio.sleep(0.05)


async def main():
    global seq_counter

    print(f"Scanning for {DEVICE_NAME}...")
    devices = await BleakScanner.discover(timeout=8.0)
    target = None
    for d in devices:
        if d.name and DEVICE_NAME in d.name:
            target = d
            break

    if not target:
        print("Device not found. Available:")
        for d in devices:
            if d.name:
                print(" -", d.name, d.address)
        return

    print("Connecting to", target.name, target.address)
    async with BleakClient(target.address) as client:
        mtu = getattr(client, 'mtu_size', None)
        print(f"Connected. MTU: {mtu}")

        await client.start_notify(RESPONSE_CHAR_UUID, notification_handler)

        cmd = {"command": "GET_STATUS"}
        await send_command(client, cmd, seq_counter)
        seq_counter += 1

        try:
            await asyncio.wait_for(response_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            print("No response (timeout)")

        await client.stop_notify(RESPONSE_CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())
