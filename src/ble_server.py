"""
BLE GATT server for employee registration.
Implements peripheral mode with command protocol and photo chunking.
"""
import asyncio
import logging
import json
import hashlib
import hmac
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


class BLEProtocol:
    """BLE protocol handler for employee registration commands."""

    # Command types
    CMD_BEGIN_UPSERT = "BEGIN_UPSERT"
    CMD_PHOTO_CHUNK = "PHOTO_CHUNK"
    CMD_END_UPSERT = "END_UPSERT"
    CMD_UPDATE_PERIOD = "UPDATE_PERIOD"
    CMD_DEACTIVATE = "DEACTIVATE"
    CMD_DELETE = "DELETE"
    CMD_GET_STATUS = "GET_STATUS"
    CMD_LIST_EMPLOYEES = "LIST_EMPLOYEES"
    CMD_GET_AUDIT_LOGS = "GET_AUDIT_LOGS"

    # Response types
    RESP_OK = "OK"
    RESP_ERROR = "ERROR"
    RESP_PROGRESS = "PROGRESS"
    RESP_STATUS = "STATUS"
    RESP_EMPLOYEES = "EMPLOYEES"
    RESP_AUDIT_LOGS = "AUDIT_LOGS"

    def __init__(
        self,
        shared_secret: Optional[str],
        hmac_enabled: bool,
        max_photo_size: int,
        admin_mode_enabled: bool
    ):
        """
        Initialize BLE protocol handler.

        Args:
            shared_secret: Shared secret for HMAC (if enabled)
            hmac_enabled: Whether to use HMAC authentication
            max_photo_size: Maximum photo size in bytes
            admin_mode_enabled: Whether admin mode is enabled
        """
        self.shared_secret = shared_secret
        self.hmac_enabled = hmac_enabled
        self.max_photo_size = max_photo_size
        self.admin_mode_enabled = admin_mode_enabled

        # Current session state
        self.current_session: Optional[Dict[str, Any]] = None
        self.photo_buffer = BytesIO()
        self.used_nonces: set = set()

        logger.info(
            f"BLE Protocol initialized (HMAC: {hmac_enabled}, admin_mode: {admin_mode_enabled})"
        )

    def verify_hmac(self, command: Dict[str, Any]) -> bool:
        """
        Verify HMAC signature of a command.

        Args:
            command: Command dictionary

        Returns:
            True if valid, False otherwise
        """
        if not self.hmac_enabled:
            return True

        if not self.shared_secret:
            logger.error("HMAC enabled but no shared secret configured")
            return False

        try:
            # Extract signature and nonce
            signature = command.get('hmac')
            nonce = command.get('nonce')

            if not signature or not nonce:
                logger.warning("Missing HMAC signature or nonce")
                return False

            # Check nonce reuse
            if nonce in self.used_nonces:
                logger.warning(f"Nonce reuse detected: {nonce}")
                return False

            # Verify nonce freshness (within 5 minutes)
            try:
                nonce_timestamp = int(nonce.split('_')[0])
                current_time = int(time.time())
                if abs(current_time - nonce_timestamp) > 300:  # 5 minutes
                    logger.warning("Nonce too old or from future")
                    return False
            except (ValueError, IndexError):
                logger.warning("Invalid nonce format")
                return False

            # Compute expected HMAC
            command_copy = command.copy()
            command_copy.pop('hmac', None)

            message = json.dumps(command_copy, sort_keys=True).encode('utf-8')
            expected_hmac = hmac.new(
                self.shared_secret.encode('utf-8'),
                message,
                hashlib.sha256
            ).hexdigest()

            # Compare
            if not hmac.compare_digest(signature, expected_hmac):
                logger.warning("HMAC signature mismatch")
                return False

            # Add nonce to used set (limit size to prevent memory issues)
            self.used_nonces.add(nonce)
            if len(self.used_nonces) > 1000:
                self.used_nonces = set(list(self.used_nonces)[-500:])

            return True

        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False

    def check_admin_permission(self) -> bool:
        """
        Check if admin operations are allowed.

        Returns:
            True if allowed, False otherwise
        """
        if not self.admin_mode_enabled:
            logger.warning("Admin mode not enabled")
            return False

        return True

    def handle_begin_upsert(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle BEGIN_UPSERT command.

        Args:
            command: Command dictionary

        Returns:
            Response dictionary
        """
        try:
            # Check admin permission
            if not self.check_admin_permission():
                return {'type': self.RESP_ERROR, 'message': 'Admin mode not enabled'}

            # Verify HMAC
            if not self.verify_hmac(command):
                return {'type': self.RESP_ERROR, 'message': 'HMAC verification failed'}

            # Extract parameters
            employee_id = command.get('employee_id')
            display_name = command.get('display_name')
            access_start = command.get('access_start')
            access_end = command.get('access_end')
            num_photos = command.get('num_photos', 1)

            if not employee_id or not access_start or not access_end:
                return {'type': self.RESP_ERROR, 'message': 'Missing required parameters'}

            if num_photos < 1 or num_photos > 5:
                return {'type': self.RESP_ERROR, 'message': 'Invalid num_photos (must be 1-5)'}

            # Initialize session
            self.current_session = {
                'employee_id': employee_id,
                'display_name': display_name,
                'access_start': access_start,
                'access_end': access_end,
                'num_photos': num_photos,
                'photos_received': 0,
                'photos': []
            }

            self.photo_buffer = BytesIO()

            logger.info(f"Started upsert session for employee {employee_id}")

            return {
                'type': self.RESP_OK,
                'message': f'Session started for {employee_id}',
                'session_id': employee_id
            }

        except Exception as e:
            logger.error(f"BEGIN_UPSERT error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_photo_chunk(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle PHOTO_CHUNK command.

        Args:
            command: Command dictionary with base64 encoded chunk

        Returns:
            Response dictionary (only for last chunk or error), None for intermediate chunks
        """
        try:
            if not self.current_session:
                return {'type': self.RESP_ERROR, 'message': 'No active session'}

            import base64

            chunk_index = command.get('chunk_index', 0)
            total_chunks = command.get('total_chunks', 1)
            chunk_data = command.get('data')
            is_last = command.get('is_last', False)

            if not chunk_data:
                return {'type': self.RESP_ERROR, 'message': 'Missing chunk data'}

            # Decode base64
            try:
                chunk_bytes = base64.b64decode(chunk_data)
            except Exception as e:
                return {'type': self.RESP_ERROR, 'message': f'Invalid base64: {e}'}

            # Check size limit
            if self.photo_buffer.tell() + len(chunk_bytes) > self.max_photo_size:
                self.photo_buffer = BytesIO()
                return {'type': self.RESP_ERROR, 'message': 'Photo size exceeds limit'}

            # Write chunk
            self.photo_buffer.write(chunk_bytes)

            # Calculate progress
            progress_pct = int((chunk_index + 1) / total_chunks * 100)

            if is_last:
                # Photo complete - verify hash if provided
                photo_data = self.photo_buffer.getvalue()
                expected_hash = command.get('sha256')

                if expected_hash:
                    actual_hash = hashlib.sha256(photo_data).hexdigest()
                    if actual_hash != expected_hash:
                        self.photo_buffer = BytesIO()
                        return {'type': self.RESP_ERROR, 'message': 'Photo hash mismatch'}

                # Save photo to session
                self.current_session['photos'].append(photo_data)
                self.current_session['photos_received'] += 1

                logger.info(
                    f"Photo {self.current_session['photos_received']}/{self.current_session['num_photos']} received "
                    f"({len(photo_data)} bytes, {total_chunks} chunks)"
                )

                # Reset buffer for next photo
                self.photo_buffer = BytesIO()

                return {
                    'type': self.RESP_OK,
                    'message': f"Photo {self.current_session['photos_received']} received",
                    'photos_received': self.current_session['photos_received'],
                    'photos_total': self.current_session['num_photos']
                }
            else:
                # Intermediate chunk - NO notification (rely on BLE-level ACK)
                # This minimizes BLE traffic and prevents disconnections
                return None

        except Exception as e:
            logger.error(f"PHOTO_CHUNK error: {e}")
            self.photo_buffer = BytesIO()
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_end_upsert(
        self,
        command: Dict[str, Any],
        callback: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Handle END_UPSERT command.

        Args:
            command: Command dictionary
            callback: Callback function to process the upsert

        Returns:
            Response dictionary
        """
        try:
            if not self.current_session:
                return {'type': self.RESP_ERROR, 'message': 'No active session'}

            # Verify all photos received
            if self.current_session['photos_received'] != self.current_session['num_photos']:
                return {
                    'type': self.RESP_ERROR,
                    'message': f"Expected {self.current_session['num_photos']} photos, got {self.current_session['photos_received']}"
                }

            # Process upsert via callback
            result = callback(self.current_session)

            # Clear session
            self.current_session = None
            self.photo_buffer = BytesIO()

            return result

        except Exception as e:
            logger.error(f"END_UPSERT error: {e}")
            self.current_session = None
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_update_period(
        self,
        command: Dict[str, Any],
        callback: Callable[[str, str, str], bool]
    ) -> Dict[str, Any]:
        """
        Handle UPDATE_PERIOD command.

        Args:
            command: Command dictionary
            callback: Callback function to update period

        Returns:
            Response dictionary
        """
        try:
            if not self.check_admin_permission():
                return {'type': self.RESP_ERROR, 'message': 'Admin mode not enabled'}

            if not self.verify_hmac(command):
                return {'type': self.RESP_ERROR, 'message': 'HMAC verification failed'}

            employee_id = command.get('employee_id')
            access_start = command.get('access_start')
            access_end = command.get('access_end')

            if not employee_id or not access_start or not access_end:
                return {'type': self.RESP_ERROR, 'message': 'Missing required parameters'}

            success = callback(employee_id, access_start, access_end)

            if success:
                return {'type': self.RESP_OK, 'message': f'Period updated for {employee_id}'}
            else:
                return {'type': self.RESP_ERROR, 'message': 'Employee not found'}

        except Exception as e:
            logger.error(f"UPDATE_PERIOD error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_deactivate(
        self,
        command: Dict[str, Any],
        callback: Callable[[str], bool]
    ) -> Dict[str, Any]:
        """
        Handle DEACTIVATE command.

        Args:
            command: Command dictionary
            callback: Callback function to deactivate employee

        Returns:
            Response dictionary
        """
        try:
            if not self.check_admin_permission():
                return {'type': self.RESP_ERROR, 'message': 'Admin mode not enabled'}

            if not self.verify_hmac(command):
                return {'type': self.RESP_ERROR, 'message': 'HMAC verification failed'}

            employee_id = command.get('employee_id')

            if not employee_id:
                return {'type': self.RESP_ERROR, 'message': 'Missing employee_id'}

            success = callback(employee_id)

            if success:
                return {'type': self.RESP_OK, 'message': f'Employee {employee_id} deactivated'}
            else:
                return {'type': self.RESP_ERROR, 'message': 'Employee not found'}

        except Exception as e:
            logger.error(f"DEACTIVATE error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_get_status(self, callback: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle GET_STATUS command.

        Args:
            callback: Callback function to get system status

        Returns:
            Response dictionary
        """
        try:
            status = callback()
            return {'type': self.RESP_STATUS, 'data': status}

        except Exception as e:
            logger.error(f"GET_STATUS error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_list_employees(
        self,
        callback: Callable[[], list]
    ) -> Dict[str, Any]:
        """
        Handle LIST_EMPLOYEES command. No HMAC, no admin check.

        Args:
            callback: Callback function returning list of employee dicts

        Returns:
            Response dictionary
        """
        try:
            employees = callback()
            return {'type': self.RESP_EMPLOYEES, 'data': employees}

        except Exception as e:
            logger.error(f"LIST_EMPLOYEES error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_get_audit_logs(
        self,
        command: Dict[str, Any],
        callback: Callable
    ) -> Dict[str, Any]:
        """
        Handle GET_AUDIT_LOGS command. No HMAC.

        Args:
            command: Command dictionary with optional employee_id and limit
            callback: Callback function returning list of audit log dicts

        Returns:
            Response dictionary
        """
        try:
            employee_id = command.get('employee_id')
            limit = command.get('limit', 100)

            logs = callback(employee_id=employee_id, limit=limit)
            return {'type': self.RESP_AUDIT_LOGS, 'data': logs}

        except Exception as e:
            logger.error(f"GET_AUDIT_LOGS error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}

    def handle_delete(
        self,
        command: Dict[str, Any],
        callback: Callable[[str], bool]
    ) -> Dict[str, Any]:
        """
        Handle DELETE command. Requires admin check + HMAC.

        Args:
            command: Command dictionary
            callback: Callback function to delete employee

        Returns:
            Response dictionary
        """
        try:
            if not self.check_admin_permission():
                return {'type': self.RESP_ERROR, 'message': 'Admin mode not enabled'}

            if not self.verify_hmac(command):
                return {'type': self.RESP_ERROR, 'message': 'HMAC verification failed'}

            employee_id = command.get('employee_id')

            if not employee_id:
                return {'type': self.RESP_ERROR, 'message': 'Missing employee_id'}

            success = callback(employee_id)

            if success:
                return {'type': self.RESP_OK, 'message': f'Employee {employee_id} deleted'}
            else:
                return {'type': self.RESP_ERROR, 'message': 'Employee not found'}

        except Exception as e:
            logger.error(f"DELETE error: {e}")
            return {'type': self.RESP_ERROR, 'message': str(e)}


class BLEServer:
    """
    BLE GATT server implementation.
    Note: This is a placeholder/mock implementation as full BLE peripheral
    support on Linux requires complex dbus/bluez integration.
    For production, use bleak, bluezero, or python-gatt libraries.
    """

    def __init__(self, config, protocol: BLEProtocol):
        """
        Initialize BLE server.

        Args:
            config: BLE configuration
            protocol: Protocol handler
        """
        self.config = config
        self.protocol = protocol
        self.running = False

        logger.info(f"BLE Server initialized: {config.device_name}")
        logger.warning("BLE Server is a mock implementation. Use bleak/bluezero for production.")

    async def start(self):
        """Start BLE GATT server."""
        self.running = True
        logger.info("BLE Server started (mock)")

        # In production, this would:
        # 1. Initialize BlueZ adapter
        # 2. Register GATT service and characteristics
        # 3. Start advertising
        # 4. Handle connections and characteristic reads/writes

        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop BLE GATT server."""
        self.running = False
        logger.info("BLE Server stopped")

    def send_notification(self, data: Dict[str, Any]):
        """
        Send notification to connected client.

        Args:
            data: Response data to send
        """
        # In production, this would send a BLE notification
        logger.debug(f"BLE notification: {data}")
