import asyncio
from bleak import BleakScanner, BleakClient

TARGET_UUID = "12345678-1234-5678-1234-56789abcdef0"

async def main():
  devices = await BleakScanner.discover(timeout=8.0)
  print(f"Found {len(devices)} devices. Checking...")
  for d in devices:
      addr = d.address
      name = d.name
      try:
          async with BleakClient(addr, timeout=6.0) as client:
              svcs = await client.get_services()
              if any(s.uuid.lower() == TARGET_UUID.lower() for s in svcs):
                  print("FOUND TARGET:", addr, name)
                  return
      except Exception:
          pass
  print("Target device not found")

asyncio.run(main())