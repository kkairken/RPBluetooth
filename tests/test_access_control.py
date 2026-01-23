"""
Tests for access control module.
"""
import unittest
from datetime import datetime, timezone, timedelta
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from access_control import AccessController


class TestAccessController(unittest.TestCase):
    """Test access control logic."""

    def setUp(self):
        """Set up access controller."""
        self.controller = AccessController(
            max_attempts_per_minute=5,
            cooldown_sec=1.0
        )

    def test_check_access_period_valid(self):
        """Test valid access period."""
        employee = {
            'employee_id': 'EMP001',
            'access_start': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            'access_end': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            'is_active': 1
        }

        valid, reason = self.controller.check_access_period(employee)
        self.assertTrue(valid)

    def test_check_access_period_expired(self):
        """Test expired access period."""
        employee = {
            'employee_id': 'EMP002',
            'access_start': (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            'access_end': (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            'is_active': 1
        }

        valid, reason = self.controller.check_access_period(employee)
        self.assertFalse(valid)
        self.assertIn('expired', reason.lower())

    def test_check_access_period_not_started(self):
        """Test access period not yet started."""
        employee = {
            'employee_id': 'EMP003',
            'access_start': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            'access_end': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            'is_active': 1
        }

        valid, reason = self.controller.check_access_period(employee)
        self.assertFalse(valid)
        self.assertIn('not yet valid', reason.lower())

    def test_check_employee_active(self):
        """Test employee active check."""
        active_emp = {'employee_id': 'EMP004', 'is_active': 1}
        inactive_emp = {'employee_id': 'EMP005', 'is_active': 0}

        active, _ = self.controller.check_employee_active(active_emp)
        self.assertTrue(active)

        active, _ = self.controller.check_employee_active(inactive_emp)
        self.assertFalse(active)

    def test_validate_access_complete(self):
        """Test complete access validation."""
        valid_employee = {
            'employee_id': 'EMP006',
            'access_start': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            'access_end': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            'is_active': 1
        }

        granted, reason = self.controller.validate_access(valid_employee)
        self.assertTrue(granted)

    def test_rate_limit_cooldown(self):
        """Test cooldown rate limiting."""
        # First attempt should succeed
        ok, _ = self.controller.check_rate_limit()
        self.assertTrue(ok)

        # Immediate second attempt should fail
        ok, reason = self.controller.check_rate_limit()
        self.assertFalse(ok)
        self.assertIn('cooldown', reason.lower())

        # Wait for cooldown
        time.sleep(1.1)

        # Should succeed again
        ok, _ = self.controller.check_rate_limit()
        self.assertTrue(ok)

    def test_process_access_attempt_granted(self):
        """Test successful access attempt."""
        employee = {
            'employee_id': 'EMP007',
            'access_start': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            'access_end': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            'is_active': 1,
            'display_name': 'Test User'
        }

        granted, reason, metadata = self.controller.process_access_attempt(
            employee=employee,
            similarity_score=0.85,
            similarity_threshold=0.6
        )

        self.assertTrue(granted)
        self.assertEqual(metadata['employee_id'], 'EMP007')

    def test_process_access_attempt_low_score(self):
        """Test access attempt with low similarity score."""
        employee = {
            'employee_id': 'EMP008',
            'access_start': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            'access_end': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            'is_active': 1
        }

        granted, reason, metadata = self.controller.process_access_attempt(
            employee=employee,
            similarity_score=0.4,
            similarity_threshold=0.6
        )

        self.assertFalse(granted)
        self.assertIn('low similarity', reason.lower())

    def test_process_access_attempt_no_match(self):
        """Test access attempt with no employee match."""
        granted, reason, metadata = self.controller.process_access_attempt(
            employee=None,
            similarity_score=0.5,
            similarity_threshold=0.6
        )

        self.assertFalse(granted)
        self.assertIn('not recognized', reason.lower())


if __name__ == '__main__':
    unittest.main()
