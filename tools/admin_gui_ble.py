#!/usr/bin/env python3
"""
BLE Admin GUI - remote management of Face Access Control system via Bluetooth.
Runs on Mac, connects to BLE GATT server on Orange Pi.

Requirements:
    pip install bleak pillow

Architecture:
    Main Thread (Tkinter)              Background Thread (asyncio)
        |                                    |
        |  -- run_coroutine_threadsafe -->   |
        |                            BLEAdminClient._run_loop()
        |  <-- response_queue --> root.after(50ms, poll)
        |                                    |
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone
from pathlib import Path
import json
import asyncio
import threading
import queue
import struct
import hmac
import hashlib
import time
import base64
import math
import logging
from typing import Optional, List, Dict, Any

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("bleak not installed. Install with: pip install bleak")
    sys.exit(1)

logger = logging.getLogger(__name__)

# BLE UUIDs
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
COMMAND_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
RESPONSE_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"

# Protocol constants
HEADER_SIZE = 3
DEFAULT_MTU = 185
CHUNK_SIZE = 1024
INTER_PACKET_DELAY_MS = 80
SLEEP_BETWEEN_CHUNKS_MS = 150
MAX_RETRIES = 5
DEVICE_NAME = "RP3_FaceAccess"

# Settings
SETTINGS_FILE = "data/gui_ble_settings.json"


class BLEAdminClient:
    """BLE communication layer for admin GUI."""

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.shared_secret: str = ""
        self._seq = 0
        self._mtu = DEFAULT_MTU
        self._write_chunk_size = DEFAULT_MTU - 3
        self._disconnected = True
        self._fragment_buffer = bytearray()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.response_queue = queue.Queue()
        self._response_event: Optional[asyncio.Event] = None
        self._last_response: Optional[dict] = None
        self.connected = False
        self.device_address: Optional[str] = None

    def start(self):
        """Start asyncio event loop in background thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        """Run asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._response_event = asyncio.Event()
        self._loop.run_forever()

    def _run_coro(self, coro, timeout=30.0):
        """Submit coroutine to background loop and wait for result."""
        if not self._loop:
            raise RuntimeError("Event loop not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def notification_handler(self, sender, data):
        """Handle BLE notifications with fragment reassembly."""
        try:
            if len(data) > 0 and data[0] in (0x00, 0x01):
                is_continuation = (data[0] == 0x01)
                fragment_data = data[1:]
                self._fragment_buffer.extend(fragment_data)
                if is_continuation:
                    return
                data = bytes(self._fragment_buffer)
                self._fragment_buffer = bytearray()

            response_str = data.decode('utf-8')
            response = json.loads(response_str)
            self._last_response = response

            if self._loop and self._response_event:
                self._loop.call_soon_threadsafe(self._response_event.set)

        except Exception as e:
            logger.error(f"Notification error: {e}")
            self._fragment_buffer = bytearray()

    def _on_disconnect(self, client):
        """Handle disconnection."""
        self._disconnected = True
        self.connected = False
        self._fragment_buffer = bytearray()
        if self._loop and self._response_event:
            self._loop.call_soon_threadsafe(self._response_event.set)
        self.response_queue.put(('disconnected', None))

    # --- High-level API (called from Tkinter thread) ---

    def scan(self, timeout=10.0) -> List[Dict[str, str]]:
        """Scan for BLE devices."""
        async def _scan():
            devices = await BleakScanner.discover(timeout=timeout)
            result = []
            for d in devices:
                if d.name:
                    result.append({'name': d.name, 'address': d.address})
            return result
        return self._run_coro(_scan(), timeout=timeout + 5)

    def connect(self, address: str):
        """Connect to BLE device."""
        async def _connect():
            self._fragment_buffer = bytearray()
            self._seq = 0
            self.client = BleakClient(
                address,
                disconnected_callback=self._on_disconnect
            )
            await self.client.connect()
            self._disconnected = False
            self.connected = True
            self.device_address = address

            try:
                mtu = self.client.mtu_size
                if mtu and mtu > 23:
                    self._mtu = mtu
                    self._write_chunk_size = mtu - 3
            except Exception:
                pass

            await self.client.start_notify(RESPONSE_CHAR_UUID, self.notification_handler)
            await asyncio.sleep(0.3)

        self._run_coro(_connect())

    def disconnect(self):
        """Disconnect from BLE device."""
        async def _disconnect():
            if self.client and self.client.is_connected:
                try:
                    await self.client.stop_notify(RESPONSE_CHAR_UUID)
                except Exception:
                    pass
                await self.client.disconnect()
            self.connected = False
            self._disconnected = True

        try:
            self._run_coro(_disconnect())
        except Exception:
            self.connected = False
            self._disconnected = True

    def generate_hmac(self, command: dict) -> tuple:
        """Generate HMAC signature for a command."""
        nonce = f"{int(time.time())}_{os.urandom(8).hex()}"
        command_with_nonce = command.copy()
        command_with_nonce['nonce'] = nonce
        message = json.dumps(command_with_nonce, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        return signature, nonce

    def _send_and_wait(self, command: dict, timeout=15.0) -> Optional[dict]:
        """Send command and wait for response."""
        async def _do():
            self._response_event.clear()
            self._last_response = None
            await self._send_command(command)
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout)
            except asyncio.TimeoutError:
                return None
            return self._last_response
        return self._run_coro(_do(), timeout=timeout + 5)

    async def _send_command(self, command: dict):
        """Send framed command over BLE."""
        payload = json.dumps(command, separators=(',', ':')).encode('utf-8')
        header = struct.pack('>HB', len(payload), self._seq & 0xFF)
        packet = header + payload
        self._seq += 1

        for i in range(0, len(packet), self._write_chunk_size):
            chunk = packet[i:i + self._write_chunk_size]
            for attempt in range(MAX_RETRIES):
                try:
                    await self.client.write_gatt_char(
                        COMMAND_CHAR_UUID, chunk, response=True
                    )
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(0.2)
                    else:
                        raise
            if i + self._write_chunk_size < len(packet):
                await asyncio.sleep(INTER_PACKET_DELAY_MS / 1000.0)

    async def _send_reliable(self, command: dict) -> bool:
        """Send single command reliably (for photo chunks)."""
        payload = json.dumps(command, separators=(',', ':')).encode('utf-8')
        header = struct.pack('>HB', len(payload), self._seq & 0xFF)
        packet = header + payload
        self._seq += 1

        chunks = []
        for i in range(0, len(packet), self._write_chunk_size):
            chunks.append(packet[i:i + self._write_chunk_size])

        for chunk in chunks:
            for attempt in range(5):
                try:
                    if self._disconnected or not self.client or not self.client.is_connected:
                        return False
                    await self.client.write_gatt_char(
                        COMMAND_CHAR_UUID, chunk, response=True
                    )
                    break
                except Exception:
                    if attempt < 4:
                        await asyncio.sleep(0.3)
                    else:
                        return False
            await asyncio.sleep(0.08)
        await asyncio.sleep(0.12)
        return True

    # --- Command API ---

    def _check_response(self, resp, expected_type, command_name):
        """Check BLE response and raise on error/timeout."""
        if resp is None:
            raise ConnectionError(f"{command_name}: no response (timeout)")
        if resp.get('type') == 'ERROR':
            raise RuntimeError(f"{command_name}: {resp.get('message', 'unknown error')}")
        if resp.get('type') != expected_type:
            raise RuntimeError(f"{command_name}: unexpected response type '{resp.get('type')}'")
        return resp

    def list_employees(self) -> list:
        """Get list of all employees."""
        resp = self._send_and_wait({"command": "LIST_EMPLOYEES"})
        self._check_response(resp, 'EMPLOYEES', 'LIST_EMPLOYEES')
        return resp.get('data', [])

    def get_status(self) -> dict:
        """Get system status."""
        resp = self._send_and_wait({"command": "GET_STATUS"})
        self._check_response(resp, 'STATUS', 'GET_STATUS')
        return resp.get('data', {})

    def get_audit_logs(self, employee_id=None, limit=100) -> list:
        """Get audit logs."""
        cmd = {"command": "GET_AUDIT_LOGS", "limit": limit}
        if employee_id:
            cmd['employee_id'] = employee_id
        resp = self._send_and_wait(cmd, timeout=30.0)
        self._check_response(resp, 'AUDIT_LOGS', 'GET_AUDIT_LOGS')
        return resp.get('data', [])

    def begin_upsert(self, employee_id, display_name, access_start, access_end, num_photos):
        """Begin upsert session."""
        command = {
            "command": "BEGIN_UPSERT",
            "employee_id": employee_id,
            "display_name": display_name,
            "access_start": access_start,
            "access_end": access_end,
            "num_photos": num_photos
        }
        sig, nonce = self.generate_hmac(command)
        command['nonce'] = nonce
        command['hmac'] = sig
        resp = self._send_and_wait(command)
        return resp and resp.get('type') == 'OK'

    def send_photo(self, photo_bytes: bytes) -> bool:
        """Send a photo via BLE chunking."""
        async def _do():
            photo_b64 = base64.b64encode(photo_bytes).decode('utf-8')
            photo_hash = hashlib.sha256(photo_bytes).hexdigest()

            max_payload = self._write_chunk_size - HEADER_SIZE
            safe_chunk_size = CHUNK_SIZE
            for _ in range(3):
                total_est = max(1, math.ceil(len(photo_b64) / max(1, safe_chunk_size)))
                overhead_cmd = {
                    "command": "PHOTO_CHUNK",
                    "chunk_index": total_est - 1,
                    "total_chunks": total_est,
                    "data": "",
                    "is_last": True,
                    "sha256": photo_hash
                }
                overhead_len = len(json.dumps(overhead_cmd, separators=(',', ':')).encode('utf-8'))
                max_data_len = max_payload - overhead_len
                if max_data_len < 1:
                    return False
                max_data_len -= (max_data_len % 4)
                if max_data_len < 4:
                    return False
                if safe_chunk_size <= max_data_len:
                    break
                safe_chunk_size = max_data_len

            safe_chunk_size -= (safe_chunk_size % 4)
            if safe_chunk_size < 4:
                return False

            chunks = [photo_b64[i:i+safe_chunk_size] for i in range(0, len(photo_b64), safe_chunk_size)]
            total_chunks = len(chunks)

            self._response_event.clear()
            self._last_response = None

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

                success = await self._send_reliable(command)
                if not success:
                    return False
                await asyncio.sleep(SLEEP_BETWEEN_CHUNKS_MS / 1000.0)

            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                return False

            return self._last_response and self._last_response.get('type') == 'OK'

        return self._run_coro(_do(), timeout=120.0)

    def end_upsert(self) -> bool:
        """End upsert session."""
        resp = self._send_and_wait({"command": "END_UPSERT"}, timeout=30.0)
        return resp is not None and resp.get('type') == 'OK'

    def update_period(self, employee_id, access_start, access_end) -> bool:
        """Update employee access period."""
        command = {
            "command": "UPDATE_PERIOD",
            "employee_id": employee_id,
            "access_start": access_start,
            "access_end": access_end
        }
        sig, nonce = self.generate_hmac(command)
        command['nonce'] = nonce
        command['hmac'] = sig
        resp = self._send_and_wait(command)
        return resp is not None and resp.get('type') == 'OK'

    def deactivate(self, employee_id) -> bool:
        """Deactivate employee."""
        command = {
            "command": "DEACTIVATE",
            "employee_id": employee_id
        }
        sig, nonce = self.generate_hmac(command)
        command['nonce'] = nonce
        command['hmac'] = sig
        resp = self._send_and_wait(command)
        return resp is not None and resp.get('type') == 'OK'

    def delete_employee(self, employee_id) -> bool:
        """Delete employee."""
        command = {
            "command": "DELETE",
            "employee_id": employee_id
        }
        sig, nonce = self.generate_hmac(command)
        command['nonce'] = nonce
        command['hmac'] = sig
        resp = self._send_and_wait(command)
        return resp is not None and resp.get('type') == 'OK'


class BLEAdminGUI:
    """Tkinter GUI for remote BLE admin management."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BLE Admin - Face Access Control")
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        self.base_dir = Path(__file__).parent.parent
        self.ble_client = BLEAdminClient()
        self.ble_client.start()

        self.selected_photos: List[str] = []
        self.all_employees: List[dict] = []

        self._load_settings()
        self._create_ui()
        self._poll_queue()

    def _load_settings(self):
        """Load saved settings."""
        settings_path = self.base_dir / SETTINGS_FILE
        self.settings = {
            'device_address': '',
            'device_name': DEVICE_NAME,
            'shared_secret': ''
        }
        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception:
                pass

    def _save_settings(self):
        """Save settings."""
        settings_path = self.base_dir / SETTINGS_FILE
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _create_ui(self):
        """Create the user interface."""
        # --- BLE Connection Panel ---
        conn_frame = ttk.LabelFrame(self.root, text="BLE", padding="5")
        conn_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Device:").pack(side=tk.LEFT)
        self.device_var = tk.StringVar(value=self.settings.get('device_name', DEVICE_NAME))
        ttk.Entry(row1, textvariable=self.device_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Label(row1, text="Address:").pack(side=tk.LEFT, padx=(10, 0))
        self.address_var = tk.StringVar(value=self.settings.get('device_address', ''))
        self.address_combo = ttk.Combobox(row1, textvariable=self.address_var, width=25)
        self.address_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(row1, text="Secret:").pack(side=tk.LEFT, padx=(10, 0))
        self.secret_var = tk.StringVar(value=self.settings.get('shared_secret', ''))
        ttk.Entry(row1, textvariable=self.secret_var, width=20, show="*").pack(side=tk.LEFT, padx=5)

        row2 = ttk.Frame(conn_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Button(row2, text="Scan", command=self._on_scan).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="Connect", command=self._on_connect).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="Disconnect", command=self._on_disconnect).pack(side=tk.LEFT, padx=2)

        self.conn_status_label = ttk.Label(row2, text="Status: Disconnected", foreground="red")
        self.conn_status_label.pack(side=tk.LEFT, padx=20)

        # --- Main content ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel - employee list
        left_frame = ttk.LabelFrame(main_frame, text="Employees", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Search
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._filter_employees())
        ttk.Entry(search_frame, textvariable=self.search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=5
        )

        # Employee table
        columns = ('id', 'name', 'status', 'access_start', 'access_end', 'photos')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=20)

        self.tree.heading('id', text='ID')
        self.tree.heading('name', text='Name')
        self.tree.heading('status', text='Status')
        self.tree.heading('access_start', text='Start')
        self.tree.heading('access_end', text='End')
        self.tree.heading('photos', text='Photos')

        self.tree.column('id', width=100)
        self.tree.column('name', width=150)
        self.tree.column('status', width=80)
        self.tree.column('access_start', width=100)
        self.tree.column('access_end', width=100)
        self.tree.column('photos', width=50)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self._on_employee_select)

        # Right panel - edit form
        right_frame = ttk.Frame(main_frame, width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)

        form_frame = ttk.LabelFrame(right_frame, text="Employee Data", padding="10")
        form_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(form_frame, text="Employee ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.id_var = tk.StringVar()
        self.id_entry = ttk.Entry(form_frame, textvariable=self.id_var, width=30)
        self.id_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)

        ttk.Label(form_frame, text="Name:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.name_var, width=30).grid(
            row=1, column=1, sticky=tk.EW, pady=2
        )

        ttk.Label(form_frame, text="Access Start:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form_frame, textvariable=self.start_var, width=30).grid(
            row=2, column=1, sticky=tk.EW, pady=2
        )

        ttk.Label(form_frame, text="Access End:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.end_var = tk.StringVar(
            value=datetime(datetime.now().year + 1, 12, 31).strftime("%Y-%m-%d")
        )
        ttk.Entry(form_frame, textvariable=self.end_var, width=30).grid(
            row=3, column=1, sticky=tk.EW, pady=2
        )

        ttk.Label(form_frame, text="Active:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_frame, variable=self.active_var).grid(
            row=4, column=1, sticky=tk.W, pady=2
        )

        form_frame.columnconfigure(1, weight=1)

        # Photos
        photo_frame = ttk.LabelFrame(right_frame, text="Photos", padding="10")
        photo_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.photo_listbox = tk.Listbox(photo_frame, height=6)
        self.photo_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        photo_btn_frame = ttk.Frame(photo_frame)
        photo_btn_frame.pack(fill=tk.X)
        ttk.Button(photo_btn_frame, text="Add Photo", command=self._add_photos).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(photo_btn_frame, text="Remove", command=self._remove_photo).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(photo_btn_frame, text="Clear All", command=self._clear_photos).pack(
            side=tk.LEFT, padx=2
        )

        # Action buttons
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="New", command=self._new_employee).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Save", command=self._save_employee).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Delete", command=self._delete_employee).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Deactivate", command=self._deactivate_employee).pack(
            side=tk.LEFT, padx=2
        )

        # Bottom panel
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)

        self.status_label = ttk.Label(bottom_frame, text="")
        self.status_label.pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="Refresh", command=self._refresh_employees).pack(
            side=tk.RIGHT, padx=2
        )
        ttk.Button(bottom_frame, text="Audit Log", command=self._show_audit_log).pack(
            side=tk.RIGHT, padx=2
        )

    def _poll_queue(self):
        """Poll response queue for events from BLE thread."""
        try:
            while True:
                event_type, data = self.ble_client.response_queue.get_nowait()
                if event_type == 'disconnected':
                    self.conn_status_label.config(
                        text="Status: Disconnected", foreground="red"
                    )
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _run_in_thread(self, func, success_msg=None, error_msg="Operation failed"):
        """Run a blocking BLE operation in a thread to avoid freezing the GUI."""
        def _worker():
            try:
                result = func()
                self.root.after(0, lambda: _on_done(result))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", f"{error_msg}:\n{err_msg}"))

        def _on_done(result):
            if success_msg and result:
                self.status_label.config(text=success_msg)

        threading.Thread(target=_worker, daemon=True).start()

    # --- BLE Connection ---

    def _on_scan(self):
        """Scan for BLE devices."""
        self.conn_status_label.config(text="Status: Scanning...", foreground="orange")
        self.root.update()

        def _do_scan():
            device_name = self.device_var.get().strip() or DEVICE_NAME
            try:
                devices = self.ble_client.scan(timeout=10.0)
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._scan_done([], err_msg))
                return

            matching = [d for d in devices if device_name in (d['name'] or '')]
            all_named = [d for d in devices if d['name']]
            self.root.after(0, lambda: self._scan_done(matching, None, all_named))

        threading.Thread(target=_do_scan, daemon=True).start()

    def _scan_done(self, matching, error=None, all_devices=None):
        if error:
            self.conn_status_label.config(text=f"Status: Scan error", foreground="red")
            messagebox.showerror("Scan Error", str(error))
            return

        if all_devices:
            values = [f"{d['name']} ({d['address']})" for d in all_devices]
            self.address_combo['values'] = values

        if matching:
            self.address_var.set(matching[0]['address'])
            self.conn_status_label.config(
                text=f"Status: Found {len(matching)} device(s)", foreground="green"
            )
        else:
            self.conn_status_label.config(text="Status: Device not found", foreground="red")

    def _on_connect(self):
        """Connect to BLE device."""
        address = self.address_var.get().strip()
        # Handle combo format "Name (AA:BB:CC:DD:EE:FF)"
        if '(' in address and ')' in address:
            address = address.split('(')[-1].rstrip(')')

        if not address:
            messagebox.showerror("Error", "Enter device address or scan first")
            return

        secret = self.secret_var.get().strip()
        self.ble_client.shared_secret = secret

        self.conn_status_label.config(text="Status: Connecting...", foreground="orange")
        self.root.update()

        def _do_connect():
            try:
                self.ble_client.connect(address)
                self.settings['device_address'] = address
                self.settings['device_name'] = self.device_var.get().strip()
                self.settings['shared_secret'] = secret
                self._save_settings()
                self.root.after(0, self._connect_done)
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._connect_error(err_msg))

        threading.Thread(target=_do_connect, daemon=True).start()

    def _connect_done(self):
        self.conn_status_label.config(text="Status: Connected", foreground="green")
        self._refresh_employees()

    def _connect_error(self, error):
        self.conn_status_label.config(text="Status: Connection failed", foreground="red")
        messagebox.showerror("Connection Error", error)

    def _on_disconnect(self):
        """Disconnect from BLE device."""
        try:
            self.ble_client.disconnect()
        except Exception:
            pass
        self.conn_status_label.config(text="Status: Disconnected", foreground="red")

    def _check_connected(self) -> bool:
        if not self.ble_client.connected:
            messagebox.showerror("Error", "Not connected to BLE device")
            return False
        return True

    # --- Employee List ---

    def _refresh_employees(self):
        """Refresh employee list from BLE server."""
        if not self._check_connected():
            return

        self.status_label.config(text="Loading employees...")
        self.root.update()

        def _do():
            try:
                employees = self.ble_client.list_employees()
                self.root.after(0, lambda: self._employees_loaded(employees))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._employees_error(err_msg))

        threading.Thread(target=_do, daemon=True).start()

    def _employees_loaded(self, employees):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.all_employees = employees
        for emp in employees:
            status = "Active" if emp.get('is_active') else "Inactive"
            start = (emp.get('access_start') or '')[:10]
            end = (emp.get('access_end') or '')[:10]
            self.tree.insert('', tk.END, values=(
                emp['employee_id'],
                emp.get('display_name', emp['employee_id']),
                status, start, end,
                emp.get('embedding_count', 0)
            ))

        total = len(employees)
        active = sum(1 for e in employees if e.get('is_active'))
        self.status_label.config(text=f"Total: {total} | Active: {active}")

    def _employees_error(self, error):
        self.status_label.config(text="Error loading employees")
        messagebox.showerror("Error", f"Failed to load employees:\n{error}")

    def _filter_employees(self):
        """Filter employee list by search text."""
        search_text = self.search_var.get().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for emp in self.all_employees:
            eid = emp.get('employee_id', '').lower()
            name = emp.get('display_name', '').lower()
            if search_text in eid or search_text in name:
                status = "Active" if emp.get('is_active') else "Inactive"
                start = (emp.get('access_start') or '')[:10]
                end = (emp.get('access_end') or '')[:10]
                self.tree.insert('', tk.END, values=(
                    emp['employee_id'],
                    emp.get('display_name', emp['employee_id']),
                    status, start, end,
                    emp.get('embedding_count', 0)
                ))

    def _on_employee_select(self, event):
        """Handle employee selection in treeview."""
        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        values = item['values']
        employee_id = values[0]

        # Find in cached data
        for emp in self.all_employees:
            if emp['employee_id'] == employee_id:
                self.id_var.set(emp['employee_id'])
                self.name_var.set(emp.get('display_name') or '')
                self.start_var.set((emp.get('access_start') or '')[:10])
                self.end_var.set((emp.get('access_end') or '')[:10])
                self.active_var.set(bool(emp.get('is_active')))
                self.id_entry.config(state='disabled')
                self._clear_photos()
                break

    # --- Photos ---

    def _add_photos(self):
        files = filedialog.askopenfilenames(
            title="Select Photos",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.bmp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("All Files", "*.*")
            ]
        )
        for f in files:
            if f not in self.selected_photos:
                self.selected_photos.append(f)
                self.photo_listbox.insert(tk.END, Path(f).name)

    def _remove_photo(self):
        selection = self.photo_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        self.photo_listbox.delete(idx)
        del self.selected_photos[idx]

    def _clear_photos(self):
        self.selected_photos = []
        self.photo_listbox.delete(0, tk.END)

    # --- Employee Actions ---

    def _new_employee(self):
        self.id_var.set("")
        self.name_var.set("")
        self.start_var.set(datetime.now().strftime("%Y-%m-%d"))
        self.end_var.set(datetime(datetime.now().year + 1, 12, 31).strftime("%Y-%m-%d"))
        self.active_var.set(True)
        self.id_entry.config(state='normal')
        self._clear_photos()
        self.tree.selection_remove(*self.tree.selection())

    def _save_employee(self):
        """Save employee via BLE."""
        if not self._check_connected():
            return

        employee_id = self.id_var.get().strip()
        name = self.name_var.get().strip()
        start_str = self.start_var.get().strip()
        end_str = self.end_var.get().strip()

        if not employee_id:
            messagebox.showerror("Error", "Enter Employee ID")
            return
        if not name:
            messagebox.showerror("Error", "Enter employee name")
            return

        try:
            datetime.strptime(start_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid start date format (YYYY-MM-DD)")
            return

        try:
            datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid end date format (YYYY-MM-DD)")
            return

        access_start = f"{start_str}T00:00:00+00:00"
        access_end = f"{end_str}T23:59:59+00:00"

        if self.selected_photos:
            self._save_with_photos(employee_id, name, access_start, access_end)
        else:
            self._save_period_only(employee_id, access_start, access_end)

    def _save_with_photos(self, employee_id, name, access_start, access_end):
        """Save employee with photos via BLE (BEGIN_UPSERT -> PHOTO_CHUNK -> END_UPSERT)."""
        photos = list(self.selected_photos)

        # Progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Sending Photos")
        progress_window.geometry("400x150")
        progress_window.transient(self.root)
        progress_window.grab_set()

        progress_label = ttk.Label(progress_window, text="Starting upload...")
        progress_label.pack(pady=20)
        progress_bar = ttk.Progressbar(progress_window, length=300, mode='determinate')
        progress_bar.pack(pady=10)
        status_label = ttk.Label(progress_window, text="")
        status_label.pack(pady=10)

        def _do_upload():
            try:
                # BEGIN_UPSERT
                self.root.after(0, lambda: status_label.config(text="Starting session..."))
                success = self.ble_client.begin_upsert(
                    employee_id, name, access_start, access_end, len(photos)
                )
                if not success:
                    self.root.after(0, lambda: _upload_error("BEGIN_UPSERT failed"))
                    return

                # Send photos
                for i, photo_path in enumerate(photos):
                    self.root.after(0, lambda idx=i: (
                        progress_bar.__setattr__('value', (idx / len(photos)) * 100) if True else None,
                        status_label.config(text=f"Photo {idx + 1}/{len(photos)}: {Path(photos[idx]).name}")
                    ))

                    with open(photo_path, 'rb') as f:
                        photo_bytes = f.read()

                    success = self.ble_client.send_photo(photo_bytes)
                    if not success:
                        self.root.after(0, lambda: _upload_error(f"Photo {i+1} upload failed"))
                        return

                # END_UPSERT
                self.root.after(0, lambda: status_label.config(text="Finalizing..."))
                success = self.ble_client.end_upsert()
                if success:
                    self.root.after(0, _upload_done)
                else:
                    self.root.after(0, lambda: _upload_error("END_UPSERT failed"))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: _upload_error(err_msg))

        def _upload_done():
            progress_window.destroy()
            messagebox.showinfo("Success", f"Employee {employee_id} saved with {len(photos)} photo(s)")
            self._clear_photos()
            self._refresh_employees()

        def _upload_error(error):
            progress_window.destroy()
            messagebox.showerror("Error", f"Upload failed:\n{error}")

        threading.Thread(target=_do_upload, daemon=True).start()

    def _save_period_only(self, employee_id, access_start, access_end):
        """Update access period only via UPDATE_PERIOD."""
        def _do():
            try:
                success = self.ble_client.update_period(employee_id, access_start, access_end)
                if success:
                    self.root.after(0, lambda: (
                        messagebox.showinfo("Success", f"Period updated for {employee_id}"),
                        self._refresh_employees()
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to update period"
                    ))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))

        threading.Thread(target=_do, daemon=True).start()

    def _delete_employee(self):
        """Delete employee via BLE."""
        if not self._check_connected():
            return

        employee_id = self.id_var.get().strip()
        if not employee_id:
            messagebox.showerror("Error", "Select an employee to delete")
            return

        if not messagebox.askyesno("Confirm", f"Delete employee {employee_id}?\nThis action is irreversible!"):
            return

        def _do():
            try:
                success = self.ble_client.delete_employee(employee_id)
                if success:
                    self.root.after(0, lambda: (
                        messagebox.showinfo("Success", f"Employee {employee_id} deleted"),
                        self._new_employee(),
                        self._refresh_employees()
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to delete employee"
                    ))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))

        threading.Thread(target=_do, daemon=True).start()

    def _deactivate_employee(self):
        """Deactivate employee via BLE."""
        if not self._check_connected():
            return

        employee_id = self.id_var.get().strip()
        if not employee_id:
            messagebox.showerror("Error", "Select an employee to deactivate")
            return

        if not messagebox.askyesno(
            "Confirm",
            f"Deactivate employee {employee_id}?\nThey will lose access but remain in the system."
        ):
            return

        def _do():
            try:
                success = self.ble_client.deactivate(employee_id)
                if success:
                    self.root.after(0, lambda: (
                        messagebox.showinfo("Success", f"Employee {employee_id} deactivated"),
                        self._refresh_employees()
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to deactivate employee"
                    ))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))

        threading.Thread(target=_do, daemon=True).start()

    # --- Audit Log ---

    def _show_audit_log(self):
        """Show audit log window."""
        if not self._check_connected():
            return

        log_window = tk.Toplevel(self.root)
        log_window.title("Audit Log")
        log_window.geometry("900x500")
        log_window.transient(self.root)

        # Filters
        filter_frame = ttk.Frame(log_window, padding="10")
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Limit:").pack(side=tk.LEFT)
        limit_var = tk.StringVar(value="100")
        ttk.Combobox(
            filter_frame, textvariable=limit_var,
            values=["50", "100", "200", "500"], width=10
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Employee:").pack(side=tk.LEFT, padx=(20, 0))
        emp_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=emp_var, width=15).pack(side=tk.LEFT, padx=5)

        # Log table
        columns = ('timestamp', 'event', 'employee', 'score', 'result', 'reason')
        log_tree = ttk.Treeview(log_window, columns=columns, show='headings', height=20)

        log_tree.heading('timestamp', text='Time')
        log_tree.heading('event', text='Event')
        log_tree.heading('employee', text='Employee')
        log_tree.heading('score', text='Score')
        log_tree.heading('result', text='Result')
        log_tree.heading('reason', text='Reason')

        log_tree.column('timestamp', width=150)
        log_tree.column('event', width=120)
        log_tree.column('employee', width=100)
        log_tree.column('score', width=80)
        log_tree.column('result', width=80)
        log_tree.column('reason', width=300)

        scrollbar = ttk.Scrollbar(log_window, orient=tk.VERTICAL, command=log_tree.yview)
        log_tree.configure(yscrollcommand=scrollbar.set)

        log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        loading_label = ttk.Label(log_window, text="")

        def refresh_logs():
            for item in log_tree.get_children():
                log_tree.delete(item)
            loading_label.config(text="Loading...")

            def _do():
                try:
                    limit = int(limit_var.get())
                    emp_id = emp_var.get().strip() or None
                    logs = self.ble_client.get_audit_logs(employee_id=emp_id, limit=limit)
                    self.root.after(0, lambda: _logs_loaded(logs))
                except Exception as e:
                    err_msg = str(e)
                    self.root.after(0, lambda: (
                        loading_label.config(text=""),
                        messagebox.showerror("Error", f"Failed to load logs:\n{err_msg}")
                    ))

            def _logs_loaded(logs):
                loading_label.config(text="")
                if logs is None:
                    messagebox.showerror("Error", "Failed to get audit logs")
                    return
                for log in logs:
                    log_tree.insert('', tk.END, values=(
                        (log.get('timestamp') or '')[:19],
                        log.get('event_type', ''),
                        log.get('matched_employee_id') or log.get('employee_id') or '',
                        f"{log['similarity_score']:.2f}" if log.get('similarity_score') else '',
                        log.get('result', ''),
                        log.get('reason') or ''
                    ))

            threading.Thread(target=_do, daemon=True).start()

        ttk.Button(filter_frame, text="Refresh", command=refresh_logs).pack(side=tk.LEFT, padx=20)

        refresh_logs()


def main():
    root = tk.Tk()
    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')

    app = BLEAdminGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
