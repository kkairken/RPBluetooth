"""
Tests for database module.
"""
import unittest
import tempfile
import os
from datetime import datetime, timezone, timedelta
import numpy as np

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import Database


class TestDatabase(unittest.TestCase):
    """Test database operations."""

    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)

    def tearDown(self):
        """Clean up test database."""
        self.db.close()
        os.unlink(self.temp_db.name)

    def test_upsert_employee(self):
        """Test employee upsert."""
        employee_id = "EMP001"
        access_start = datetime.now(timezone.utc)
        access_end = access_start + timedelta(days=30)

        self.db.upsert_employee(
            employee_id=employee_id,
            access_start=access_start,
            access_end=access_end,
            display_name="Test User"
        )

        # Retrieve employee
        emp = self.db.get_employee(employee_id)
        self.assertIsNotNone(emp)
        self.assertEqual(emp['employee_id'], employee_id)
        self.assertEqual(emp['display_name'], "Test User")
        self.assertEqual(emp['is_active'], 1)

    def test_add_embedding(self):
        """Test adding embeddings."""
        employee_id = "EMP002"
        access_start = datetime.now(timezone.utc)
        access_end = access_start + timedelta(days=30)

        self.db.upsert_employee(
            employee_id=employee_id,
            access_start=access_start,
            access_end=access_end
        )

        # Add embedding
        embedding = np.random.rand(512).astype(np.float32)
        emb_id = self.db.add_embedding(employee_id, embedding, photo_hash="abc123")

        self.assertIsNotNone(emb_id)
        self.assertGreater(emb_id, 0)

    def test_get_active_employees_with_embeddings(self):
        """Test retrieving active employees with embeddings."""
        employee_id = "EMP003"
        access_start = datetime.now(timezone.utc)
        access_end = access_start + timedelta(days=30)

        self.db.upsert_employee(
            employee_id=employee_id,
            access_start=access_start,
            access_end=access_end
        )

        # Add embeddings
        emb1 = np.random.rand(512).astype(np.float32)
        emb2 = np.random.rand(512).astype(np.float32)

        self.db.add_embedding(employee_id, emb1)
        self.db.add_embedding(employee_id, emb2)

        # Retrieve
        employees = self.db.get_active_employees_with_embeddings()

        self.assertEqual(len(employees), 1)
        emp, embeddings = employees[0]
        self.assertEqual(emp['employee_id'], employee_id)
        self.assertEqual(len(embeddings), 2)

    def test_deactivate_employee(self):
        """Test employee deactivation."""
        employee_id = "EMP004"
        access_start = datetime.now(timezone.utc)
        access_end = access_start + timedelta(days=30)

        self.db.upsert_employee(
            employee_id=employee_id,
            access_start=access_start,
            access_end=access_end
        )

        # Deactivate
        result = self.db.deactivate_employee(employee_id)
        self.assertTrue(result)

        # Check status
        emp = self.db.get_employee(employee_id)
        self.assertEqual(emp['is_active'], 0)

    def test_delete_employee(self):
        """Test employee deletion."""
        employee_id = "EMP005"
        access_start = datetime.now(timezone.utc)
        access_end = access_start + timedelta(days=30)

        self.db.upsert_employee(
            employee_id=employee_id,
            access_start=access_start,
            access_end=access_end
        )

        # Delete
        result = self.db.delete_employee(employee_id)
        self.assertTrue(result)

        # Verify deletion
        emp = self.db.get_employee(employee_id)
        self.assertIsNone(emp)

    def test_log_access_attempt(self):
        """Test logging access attempts."""
        self.db.log_access_attempt(
            event_type='face_recognition',
            result='granted',
            employee_id='EMP001',
            matched_employee_id='EMP001',
            similarity_score=0.85,
            reason='Access granted',
            metadata={'test': True}
        )

        # Retrieve logs
        logs = self.db.get_audit_logs(limit=10)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['event_type'], 'face_recognition')
        self.assertEqual(logs[0]['result'], 'granted')


if __name__ == '__main__':
    unittest.main()
