#!/usr/bin/env python3
"""
Real BLE GATT server implementation using BlueZ DBus API.
Works on Linux (Raspberry Pi) with BlueZ 5.50+.
"""
import asyncio
import logging
import json
import struct
import dbus
import dbus.service
import dbus.mainloop.glib
from typing import Optional, Dict, Any, Callable
from enum import IntEnum
from gi.repository import GLib

from ble_server import BLEProtocol

logger = logging.getLogger(__name__)


class RxState(IntEnum):
    """State machine for receiving fragmented messages"""
    WAIT_HEADER = 0
    WAIT_PAYLOAD = 1

# DBus paths and interfaces
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'


class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'


class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(dbus.service.Object):
    """
    org.bluez.GattService1 interface implementation
    """
    PATH_BASE = '/org/bluez/face_access/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """
    org.bluez.GattCharacteristic1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE,
                         in_signature='a{sv}',
                         out_signature='ay')
    def ReadValue(self, options):
        logger.debug(f'ReadValue called on {self.uuid}')
        return self.value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        logger.debug(f'WriteValue called on {self.uuid}')
        self.value = value

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        logger.debug(f'StartNotify called on {self.uuid}')

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        logger.debug(f'StopNotify called on {self.uuid}')

    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class CommandCharacteristic(Characteristic):
    """
    Command characteristic (Write)
    Receives commands from BLE client.

    Protocol: Length-prefixed framing
    ┌─────────────────┬──────────────┬─────────────────────┐
    │ Total Length    │ Sequence #   │ Payload (JSON)      │
    │ 2 bytes BE      │ 1 byte       │ N bytes             │
    └─────────────────┴──────────────┴─────────────────────┘
    """
    HEADER_SIZE = 3  # 2 bytes length (big-endian) + 1 byte sequence
    RX_TIMEOUT_MS = 5000  # Reset buffer if no data for 5 seconds

    def __init__(self, bus, index, service, protocol: BLEProtocol, response_chrc):
        Characteristic.__init__(
            self, bus, index,
            '12345678-1234-5678-1234-56789abcdef1',
            ['write', 'write-without-response'],
            service
        )
        self.protocol = protocol
        self.response_chrc = response_chrc
        self._rx_buffer = bytearray()
        self._rx_state = RxState.WAIT_HEADER
        self._expected_len = 0
        self._last_seq = -1
        self._timeout_handle = None
        self._max_command_size = 64 * 1024  # 64KB max

    def _reset_timeout(self):
        """Reset inactivity timeout - clears buffer if no data arrives"""
        if self._timeout_handle:
            GLib.source_remove(self._timeout_handle)
        self._timeout_handle = GLib.timeout_add(
            self.RX_TIMEOUT_MS,
            self._on_timeout
        )

    def _on_timeout(self):
        """Called when no data received for RX_TIMEOUT_MS"""
        if len(self._rx_buffer) > 0:
            logger.warning(f"RX timeout, discarding {len(self._rx_buffer)} bytes")
        self._rx_buffer = bytearray()
        self._rx_state = RxState.WAIT_HEADER
        self._expected_len = 0
        self._timeout_handle = None
        return False  # Don't repeat

    def reset_state(self):
        """Reset receiver state - call on new connection"""
        logger.info("Resetting BLE receiver state")
        self._rx_buffer = bytearray()
        self._rx_state = RxState.WAIT_HEADER
        self._expected_len = 0
        self._last_seq = -1
        if self._timeout_handle:
            GLib.source_remove(self._timeout_handle)
            self._timeout_handle = None

    def WriteValue(self, value, options):
        """Handle incoming data with length-prefixed framing"""
        try:
            self._reset_timeout()
            self._rx_buffer.extend(bytes(value))

            # Process all complete messages in buffer
            while True:
                if self._rx_state == RxState.WAIT_HEADER:
                    if len(self._rx_buffer) < self.HEADER_SIZE:
                        return  # Wait for more header bytes

                    # Parse header: 2 bytes length (BE) + 1 byte sequence
                    self._expected_len, seq = struct.unpack(
                        '>HB',
                        self._rx_buffer[:self.HEADER_SIZE]
                    )

                    # Sanity check: if length looks wrong, might be garbage data
                    if self._expected_len == 0 or self._expected_len > self._max_command_size:
                        logger.error(f"Invalid message length: {self._expected_len}, resetting buffer")
                        self._rx_buffer = bytearray()
                        self._rx_state = RxState.WAIT_HEADER
                        if self._expected_len > 0:
                            error_response = {'type': 'ERROR', 'message': 'Command too large'}
                            self.response_chrc.send_notification(json.dumps(error_response))
                        return

                    # Detect new connection: if seq resets to 0 but we had higher seq before
                    # This indicates a new client session - clear any stale data
                    if seq == 0 and self._last_seq > 0:
                        logger.info(f"New session detected (seq reset), clearing buffer")
                        self._rx_buffer = self._rx_buffer[:self.HEADER_SIZE + self._expected_len] \
                            if len(self._rx_buffer) >= self.HEADER_SIZE else bytearray()

                    # Check for duplicate (same sequence number)
                    if seq == self._last_seq and self._last_seq >= 0:
                        logger.debug(f"Duplicate message seq={seq}, ignoring")
                        # Skip this message entirely
                        skip_len = self.HEADER_SIZE + self._expected_len
                        if len(self._rx_buffer) >= skip_len:
                            self._rx_buffer = self._rx_buffer[skip_len:]
                        else:
                            self._rx_buffer = bytearray()
                        continue

                    self._last_seq = seq
                    self._rx_buffer = self._rx_buffer[self.HEADER_SIZE:]
                    self._rx_state = RxState.WAIT_PAYLOAD
                    logger.debug(f"Header: len={self._expected_len}, seq={seq}")

                if self._rx_state == RxState.WAIT_PAYLOAD:
                    if len(self._rx_buffer) < self._expected_len:
                        return  # Wait for more payload bytes

                    # Extract complete payload
                    payload = bytes(self._rx_buffer[:self._expected_len])
                    self._rx_buffer = self._rx_buffer[self._expected_len:]
                    self._rx_state = RxState.WAIT_HEADER

                    # Process the message
                    self._process_message(payload)

        except Exception as e:
            logger.error(f"WriteValue error: {e}")
            self._rx_buffer = bytearray()
            self._rx_state = RxState.WAIT_HEADER
            error_response = {'type': 'ERROR', 'message': str(e)}
            self.response_chrc.send_notification(json.dumps(error_response))

    def _process_message(self, payload: bytes):
        """Process a complete message payload"""
        try:
            command_str = payload.decode('utf-8')
            command = json.loads(command_str)

            logger.info(f"Received command: {command_str[:100]}...")
            command_type = command.get('command')

            # Process command
            response = self.process_command(command_type, command)

            # Send response via notification
            response_json = json.dumps(response)
            self.response_chrc.send_notification(response_json)

        except json.JSONDecodeError as e:
            # Log first bytes for debugging
            logger.error(f"Invalid JSON: {e}")
            logger.error(f"Payload hex (first 50 bytes): {payload[:50].hex()}")
            logger.error(f"Payload repr (first 100 chars): {repr(payload[:100])}")
            # Reset state on parse error - likely corrupted data
            self.reset_state()
            error_response = {'type': 'ERROR', 'message': f'Invalid JSON: {e}'}
            self.response_chrc.send_notification(json.dumps(error_response))
        except UnicodeDecodeError as e:
            logger.error(f"Invalid UTF-8: {e}")
            logger.error(f"Payload hex (first 50 bytes): {payload[:50].hex()}")
            self.reset_state()
            error_response = {'type': 'ERROR', 'message': 'Invalid encoding'}
            self.response_chrc.send_notification(json.dumps(error_response))

    def process_command(self, command_type: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """Process BLE command"""
        if command_type == self.protocol.CMD_BEGIN_UPSERT:
            return self.protocol.handle_begin_upsert(command)

        elif command_type == self.protocol.CMD_PHOTO_CHUNK:
            return self.protocol.handle_photo_chunk(command)

        elif command_type == self.protocol.CMD_END_UPSERT:
            # Need callback - will be set by server
            if hasattr(self, 'end_upsert_callback'):
                return self.protocol.handle_end_upsert(command, self.end_upsert_callback)
            else:
                return {'type': 'ERROR', 'message': 'Callback not set'}

        elif command_type == self.protocol.CMD_UPDATE_PERIOD:
            if hasattr(self, 'update_period_callback'):
                return self.protocol.handle_update_period(command, self.update_period_callback)
            else:
                return {'type': 'ERROR', 'message': 'Callback not set'}

        elif command_type == self.protocol.CMD_DEACTIVATE:
            if hasattr(self, 'deactivate_callback'):
                return self.protocol.handle_deactivate(command, self.deactivate_callback)
            else:
                return {'type': 'ERROR', 'message': 'Callback not set'}

        elif command_type == self.protocol.CMD_GET_STATUS:
            if hasattr(self, 'status_callback'):
                return self.protocol.handle_get_status(self.status_callback)
            else:
                return {'type': 'ERROR', 'message': 'Callback not set'}

        else:
            return {'type': 'ERROR', 'message': f'Unknown command: {command_type}'}


class ResponseCharacteristic(Characteristic):
    """
    Response characteristic (Notify)
    Sends responses to BLE client
    """
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            '12345678-1234-5678-1234-56789abcdef2',
            ['notify'],
            service
        )
        self.notifying = False
        self.command_chrc = None  # Set by RealBLEServer after creation

    def send_notification(self, message: str):
        """Send notification to client"""
        if not self.notifying:
            logger.warning("Client not subscribed to notifications")
            return

        try:
            # Convert string to bytes
            value = [dbus.Byte(c) for c in message.encode('utf-8')]
            self.value = value

            # Emit PropertiesChanged signal
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {'Value': self.value},
                []
            )
            logger.debug(f"Sent notification: {message[:100]}...")

        except Exception as e:
            logger.error(f"Notification error: {e}")

    def StartNotify(self):
        """Client subscribed to notifications - indicates new connection"""
        if self.notifying:
            logger.warning('Already notifying')
            return

        self.notifying = True
        logger.info('Notifications enabled - new client connected')

        # Reset command characteristic buffer on new connection
        if self.command_chrc:
            self.command_chrc.reset_state()

    def StopNotify(self):
        """Client unsubscribed from notifications - client disconnecting"""
        if not self.notifying:
            logger.warning('Not notifying')
            return

        self.notifying = False
        logger.info('Notifications disabled - client disconnected')

        # Reset command characteristic buffer on disconnect
        if self.command_chrc:
            self.command_chrc.reset_state()


class Advertisement(dbus.service.Object):
    """
    org.bluez.LEAdvertisement1 interface implementation
    """
    PATH_BASE = '/org/bluez/face_access/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = False
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids, signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data, signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.data is not None:
            properties['Data'] = dbus.Dictionary(self.data, signature='yv')
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        logger.info(f'Advertisement released: {self.path}')


class FaceAccessAdvertisement(Advertisement):
    """
    Advertisement for Face Access Control service
    """
    def __init__(self, bus, index, device_name):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.service_uuids = ['12345678-1234-5678-1234-56789abcdef0']
        self.local_name = device_name
        self.include_tx_power = True


class RealBLEServer:
    """
    Real BLE GATT server implementation using BlueZ
    """
    def __init__(self, config, protocol: BLEProtocol):
        """
        Initialize real BLE server.

        Args:
            config: BLE configuration
            protocol: Protocol handler
        """
        self.config = config
        self.protocol = protocol
        self.running = False
        self.mainloop = None

        # DBus setup
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()

        # GATT Application
        self.app = Application(self.bus)
        self.service = Service(self.bus, 0, config.service_uuid, True)

        # Response characteristic (must be created first for reference)
        self.response_chrc = ResponseCharacteristic(self.bus, 1, self.service)

        # Command characteristic
        self.command_chrc = CommandCharacteristic(
            self.bus, 0, self.service,
            protocol, self.response_chrc
        )

        # Link response to command for connection state management
        self.response_chrc.command_chrc = self.command_chrc

        # Add characteristics to service
        self.service.add_characteristic(self.command_chrc)
        self.service.add_characteristic(self.response_chrc)

        # Add service to application
        self.app.add_service(self.service)

        # Advertisement
        self.ad = FaceAccessAdvertisement(self.bus, 0, config.device_name)

        logger.info(f"Real BLE Server initialized: {config.device_name}")
        logger.info(f"Service UUID: {config.service_uuid}")

    def set_callbacks(self,
                     end_upsert_cb: Callable,
                     update_period_cb: Callable,
                     deactivate_cb: Callable,
                     status_cb: Callable):
        """Set callback functions for command handling"""
        self.command_chrc.end_upsert_callback = end_upsert_cb
        self.command_chrc.update_period_callback = update_period_cb
        self.command_chrc.deactivate_callback = deactivate_cb
        self.command_chrc.status_callback = status_cb

    def register_app_cb(self):
        logger.info('GATT application registered')

    def register_app_error_cb(self, error):
        logger.error(f'Failed to register application: {error}')
        self.mainloop.quit()

    def register_ad_cb(self):
        logger.info('Advertisement registered')

    def register_ad_error_cb(self, error):
        logger.error(f'Failed to register advertisement: {error}')
        self.mainloop.quit()

    async def start(self):
        """Start BLE GATT server"""
        try:
            # Get adapter
            adapter = self.find_adapter()
            if not adapter:
                logger.error('No Bluetooth adapter found')
                return

            logger.info(f'Using adapter: {adapter}')

            # Get adapter object
            adapter_obj = self.bus.get_object(BLUEZ_SERVICE_NAME, adapter)

            # Register GATT application
            service_manager = dbus.Interface(
                adapter_obj,
                GATT_MANAGER_IFACE
            )
            service_manager.RegisterApplication(
                self.app.get_path(), {},
                reply_handler=self.register_app_cb,
                error_handler=self.register_app_error_cb
            )

            # Register advertisement
            ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)
            ad_manager.RegisterAdvertisement(
                self.ad.get_path(), {},
                reply_handler=self.register_ad_cb,
                error_handler=self.register_ad_error_cb
            )

            logger.info('BLE Server started successfully')
            logger.info(f'Advertising as: {self.config.device_name}')
            logger.info('Waiting for BLE connections...')

            self.running = True

            # Run GLib mainloop in thread-safe way
            self.mainloop = GLib.MainLoop()

            # Run mainloop in executor to not block asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.mainloop.run)

        except Exception as e:
            logger.error(f'Failed to start BLE server: {e}')
            raise

    async def stop(self):
        """Stop BLE GATT server"""
        logger.info('Stopping BLE server...')
        self.running = False

        if self.mainloop:
            self.mainloop.quit()

        logger.info('BLE server stopped')

    def find_adapter(self):
        """Find Bluetooth adapter"""
        remote_om = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, '/'),
            DBUS_OM_IFACE
        )
        objects = remote_om.GetManagedObjects()

        for o, props in objects.items():
            if GATT_MANAGER_IFACE in props and LE_ADVERTISING_MANAGER_IFACE in props:
                return o

        return None
