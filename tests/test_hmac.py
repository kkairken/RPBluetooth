"""
Tests for HMAC authentication in BLE protocol.
"""
import unittest
import json
import hashlib
import hmac
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ble_server import BLEProtocol


class TestHMACProtocol(unittest.TestCase):
    """Test HMAC authentication."""

    def setUp(self):
        """Set up protocol with HMAC enabled."""
        self.shared_secret = "test_secret_key_12345"
        self.protocol = BLEProtocol(
            shared_secret=self.shared_secret,
            hmac_enabled=True,
            max_photo_size=5 * 1024 * 1024,
            admin_mode_enabled=True
        )

    def _sign_command(self, command: dict) -> dict:
        """Sign a command with HMAC."""
        # Generate nonce
        nonce = f"{int(time.time())}_{os.urandom(8).hex()}"
        command['nonce'] = nonce

        # Compute HMAC
        message = json.dumps(command, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        command['hmac'] = signature
        return command

    def test_verify_hmac_valid(self):
        """Test valid HMAC verification."""
        command = {
            'command': 'DEACTIVATE',
            'employee_id': 'EMP001'
        }

        signed_command = self._sign_command(command)
        result = self.protocol.verify_hmac(signed_command)

        self.assertTrue(result)

    def test_verify_hmac_invalid_signature(self):
        """Test invalid HMAC signature."""
        command = {
            'command': 'DEACTIVATE',
            'employee_id': 'EMP001',
            'nonce': f"{int(time.time())}_abc123",
            'hmac': 'invalid_signature_here'
        }

        result = self.protocol.verify_hmac(command)
        self.assertFalse(result)

    def test_verify_hmac_missing_signature(self):
        """Test missing HMAC signature."""
        command = {
            'command': 'DEACTIVATE',
            'employee_id': 'EMP001'
        }

        result = self.protocol.verify_hmac(command)
        self.assertFalse(result)

    def test_verify_hmac_nonce_reuse(self):
        """Test nonce reuse detection."""
        command = {
            'command': 'DEACTIVATE',
            'employee_id': 'EMP001'
        }

        signed_command = self._sign_command(command)

        # First verification should succeed
        result1 = self.protocol.verify_hmac(signed_command)
        self.assertTrue(result1)

        # Second verification with same nonce should fail
        result2 = self.protocol.verify_hmac(signed_command)
        self.assertFalse(result2)

    def test_verify_hmac_old_nonce(self):
        """Test old nonce rejection."""
        command = {
            'command': 'DEACTIVATE',
            'employee_id': 'EMP001',
            'nonce': f"{int(time.time()) - 600}_abc123"  # 10 minutes old
        }

        # Compute HMAC with old nonce
        message = json.dumps(command, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        command['hmac'] = signature

        result = self.protocol.verify_hmac(command)
        self.assertFalse(result)

    def test_admin_mode_check(self):
        """Test admin mode permission check."""
        result = self.protocol.check_admin_permission()
        self.assertTrue(result)

        # Disable admin mode
        self.protocol.admin_mode_enabled = False
        result = self.protocol.check_admin_permission()
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
