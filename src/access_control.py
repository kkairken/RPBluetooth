"""
Access control logic module.
Validates employee access rights based on time periods and status.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict
import time

logger = logging.getLogger(__name__)


class AccessController:
    """Manages access control rules and rate limiting."""

    def __init__(
        self,
        max_attempts_per_minute: int = 30,
        cooldown_sec: float = 0.5,
        granted_lockout_sec: float = 10.0
    ):
        """
        Initialize access controller.

        Args:
            max_attempts_per_minute: Max access attempts per minute (rate limit)
            cooldown_sec: Cooldown period between access attempts
            granted_lockout_sec: Lockout period after successful access (prevents repeated opens)
        """
        self.max_attempts_per_minute = max_attempts_per_minute
        self.cooldown_sec = cooldown_sec
        self.granted_lockout_sec = granted_lockout_sec

        # Rate limiting tracking
        self.attempt_timestamps: Dict[str, list] = defaultdict(list)
        self.last_attempt_time: float = 0.0

        # Track last successful access per employee (to prevent repeated opens)
        self.last_granted_time: Dict[str, float] = {}

    def check_access_period(
        self,
        employee: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if employee is within their access period.

        Args:
            employee: Employee record dict
            current_time: Current time (defaults to now)

        Returns:
            Tuple of (is_valid, reason)
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        try:
            # Parse access period
            access_start = datetime.fromisoformat(employee['access_start'])
            access_end = datetime.fromisoformat(employee['access_end'])

            # Make timezone-aware if needed
            if access_start.tzinfo is None:
                access_start = access_start.replace(tzinfo=timezone.utc)
            if access_end.tzinfo is None:
                access_end = access_end.replace(tzinfo=timezone.utc)

            # Check if current time is within period
            if current_time < access_start:
                return False, f"Access not yet valid (starts {access_start.isoformat()})"

            if current_time > access_end:
                return False, f"Access expired (ended {access_end.isoformat()})"

            return True, "Access period valid"

        except Exception as e:
            logger.error(f"Error checking access period: {e}")
            return False, f"Access period check error: {e}"

    def check_employee_active(self, employee: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if employee is active.

        Args:
            employee: Employee record dict

        Returns:
            Tuple of (is_active, reason)
        """
        is_active = bool(employee.get('is_active', 0))

        if not is_active:
            return False, "Employee is deactivated"

        return True, "Employee is active"

    def validate_access(
        self,
        employee: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Comprehensive access validation.

        Args:
            employee: Employee record dict
            current_time: Current time (defaults to now)

        Returns:
            Tuple of (is_granted, reason)
        """
        # Check if employee is active
        active, reason = self.check_employee_active(employee)
        if not active:
            return False, reason

        # Check access period
        period_valid, reason = self.check_access_period(employee, current_time)
        if not period_valid:
            return False, reason

        return True, "Access granted"

    def check_rate_limit(self, employee_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check rate limiting for access attempts.

        Args:
            employee_id: Employee ID (optional, for per-employee rate limiting)

        Returns:
            Tuple of (is_allowed, reason)
        """
        current_time = time.time()

        # Global cooldown check
        time_since_last = current_time - self.last_attempt_time
        if time_since_last < self.cooldown_sec:
            return False, f"Cooldown active ({self.cooldown_sec - time_since_last:.1f}s remaining)"

        # Per-employee rate limiting (optional)
        if employee_id:
            # Clean old timestamps (older than 1 minute)
            cutoff_time = current_time - 60.0
            self.attempt_timestamps[employee_id] = [
                t for t in self.attempt_timestamps[employee_id] if t > cutoff_time
            ]

            # Check attempt count
            if len(self.attempt_timestamps[employee_id]) >= self.max_attempts_per_minute:
                return False, f"Rate limit exceeded ({self.max_attempts_per_minute} attempts/min)"

            # Record this attempt
            self.attempt_timestamps[employee_id].append(current_time)

        # Update last attempt time
        self.last_attempt_time = current_time

        return True, "Rate limit OK"

    def check_granted_lockout(self, employee_id: str) -> Tuple[bool, str]:
        """
        Check if employee is in lockout period after successful access.
        Prevents door from opening repeatedly for same person.

        Args:
            employee_id: Employee ID

        Returns:
            Tuple of (is_allowed, reason)
        """
        current_time = time.time()
        last_granted = self.last_granted_time.get(employee_id, 0.0)
        time_since_granted = current_time - last_granted

        if time_since_granted < self.granted_lockout_sec:
            remaining = self.granted_lockout_sec - time_since_granted
            logger.debug(
                f"Lockout active for {employee_id}: {time_since_granted:.1f}s elapsed, "
                f"{remaining:.1f}s remaining (lockout={self.granted_lockout_sec}s)"
            )
            return False, f"Recently granted ({remaining:.0f}s remaining)"

        logger.debug(
            f"No lockout for {employee_id}: {time_since_granted:.1f}s since last grant "
            f"(lockout={self.granted_lockout_sec}s)"
        )
        return True, "No lockout"

    def record_granted_access(self, employee_id: str):
        """Record successful access for lockout tracking."""
        current_time = time.time()
        self.last_granted_time[employee_id] = current_time
        logger.info(f"Recorded granted access for {employee_id} at {current_time:.3f}")

    def process_access_attempt(
        self,
        employee: Optional[Dict[str, Any]],
        similarity_score: float,
        similarity_threshold: float
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Process complete access attempt with all checks.

        Args:
            employee: Matched employee record (or None)
            similarity_score: Face recognition similarity score
            similarity_threshold: Recognition threshold

        Returns:
            Tuple of (is_granted, reason, metadata)
        """
        metadata = {
            'similarity_score': similarity_score,
            'similarity_threshold': similarity_threshold
        }

        # Check if face was recognized
        if employee is None:
            return False, "Face not recognized", metadata

        if similarity_score < similarity_threshold:
            return False, f"Low similarity score ({similarity_score:.3f})", metadata

        employee_id = employee['employee_id']
        metadata['employee_id'] = employee_id
        metadata['display_name'] = employee.get('display_name')

        # Check if recently granted (prevent repeated opens for same person)
        lockout_ok, reason = self.check_granted_lockout(employee_id)
        if not lockout_ok:
            return False, reason, metadata

        # Check rate limit
        rate_ok, reason = self.check_rate_limit(employee_id)
        if not rate_ok:
            return False, f"Rate limit: {reason}", metadata

        # Validate access rights
        access_ok, reason = self.validate_access(employee)
        if not access_ok:
            return False, reason, metadata

        # Record successful access for lockout
        self.record_granted_access(employee_id)

        return True, "Access granted", metadata
