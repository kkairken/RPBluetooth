"""
Tests for BLE protocol photo chunking.
"""
import unittest
import base64
import hashlib

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ble_server import BLEProtocol


class TestProtocolChunking(unittest.TestCase):
    """Test photo chunking protocol."""

    def setUp(self):
        """Set up protocol without HMAC for simpler testing."""
        self.protocol = BLEProtocol(
            shared_secret=None,
            hmac_enabled=False,
            max_photo_size=1024 * 1024,
            admin_mode_enabled=True
        )

    def test_begin_upsert(self):
        """Test BEGIN_UPSERT command."""
        command = {
            'command': 'BEGIN_UPSERT',
            'employee_id': 'EMP001',
            'display_name': 'Test User',
            'access_start': '2025-01-01T00:00:00Z',
            'access_end': '2025-12-31T23:59:59Z',
            'num_photos': 2
        }

        response = self.protocol.handle_begin_upsert(command)

        self.assertEqual(response['type'], 'OK')
        self.assertIsNotNone(self.protocol.current_session)
        self.assertEqual(self.protocol.current_session['employee_id'], 'EMP001')

    def test_photo_chunking(self):
        """Test photo chunking process."""
        # Start session
        begin_cmd = {
            'command': 'BEGIN_UPSERT',
            'employee_id': 'EMP002',
            'access_start': '2025-01-01T00:00:00Z',
            'access_end': '2025-12-31T23:59:59Z',
            'num_photos': 1
        }
        self.protocol.handle_begin_upsert(begin_cmd)

        # Create fake photo data
        photo_data = b'FAKE_JPEG_DATA_' + os.urandom(100)
        photo_hash = hashlib.sha256(photo_data).hexdigest()

        # Split into chunks
        chunk_size = 50
        chunks = [photo_data[i:i+chunk_size] for i in range(0, len(photo_data), chunk_size)]

        # Send chunks
        for i, chunk in enumerate(chunks):
            chunk_cmd = {
                'command': 'PHOTO_CHUNK',
                'chunk_index': i,
                'total_chunks': len(chunks),
                'data': base64.b64encode(chunk).decode('ascii'),
                'is_last': (i == len(chunks) - 1),
                'sha256': photo_hash if (i == len(chunks) - 1) else None
            }

            response = self.protocol.handle_photo_chunk(chunk_cmd)

            if i == len(chunks) - 1:
                # Last chunk
                self.assertEqual(response['type'], 'OK')
                self.assertEqual(response['photos_received'], 1)
            else:
                # Progress
                self.assertEqual(response['type'], 'PROGRESS')

        # Verify photo stored in session
        self.assertEqual(len(self.protocol.current_session['photos']), 1)
        self.assertEqual(self.protocol.current_session['photos'][0], photo_data)

    def test_photo_hash_mismatch(self):
        """Test photo hash verification failure."""
        # Start session
        begin_cmd = {
            'command': 'BEGIN_UPSERT',
            'employee_id': 'EMP003',
            'access_start': '2025-01-01T00:00:00Z',
            'access_end': '2025-12-31T23:59:59Z',
            'num_photos': 1
        }
        self.protocol.handle_begin_upsert(begin_cmd)

        # Send photo with wrong hash
        photo_data = b'FAKE_JPEG_DATA'
        wrong_hash = 'wrong_hash_value'

        chunk_cmd = {
            'command': 'PHOTO_CHUNK',
            'chunk_index': 0,
            'total_chunks': 1,
            'data': base64.b64encode(photo_data).decode('ascii'),
            'is_last': True,
            'sha256': wrong_hash
        }

        response = self.protocol.handle_photo_chunk(chunk_cmd)

        self.assertEqual(response['type'], 'ERROR')
        self.assertIn('hash mismatch', response['message'].lower())

    def test_max_photo_size_exceeded(self):
        """Test photo size limit enforcement."""
        # Start session
        begin_cmd = {
            'command': 'BEGIN_UPSERT',
            'employee_id': 'EMP004',
            'access_start': '2025-01-01T00:00:00Z',
            'access_end': '2025-12-31T23:59:59Z',
            'num_photos': 1
        }
        self.protocol.handle_begin_upsert(begin_cmd)

        # Try to send too much data
        large_chunk = b'X' * (self.protocol.max_photo_size + 1000)

        chunk_cmd = {
            'command': 'PHOTO_CHUNK',
            'chunk_index': 0,
            'total_chunks': 1,
            'data': base64.b64encode(large_chunk).decode('ascii'),
            'is_last': True
        }

        response = self.protocol.handle_photo_chunk(chunk_cmd)

        self.assertEqual(response['type'], 'ERROR')
        self.assertIn('exceeds limit', response['message'].lower())


if __name__ == '__main__':
    unittest.main()
