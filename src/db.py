"""
Database module for offline face access control system.
Manages SQLite database for employees, embeddings, and audit logs.
"""
import sqlite3
import logging
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for access control system."""

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()

        # Employees table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                employee_id TEXT PRIMARY KEY,
                display_name TEXT,
                access_start TEXT NOT NULL,
                access_end TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Embeddings table (one employee can have multiple embeddings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                photo_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_employee ON embeddings(employee_id)")

        # Audit log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                employee_id TEXT,
                matched_employee_id TEXT,
                similarity_score REAL,
                result TEXT NOT NULL,
                reason TEXT,
                metadata TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_employee ON audit_log(employee_id)")

        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def upsert_employee(
        self,
        employee_id: str,
        access_start: datetime,
        access_end: datetime,
        display_name: Optional[str] = None,
        is_active: bool = True
    ) -> None:
        """
        Insert or update employee record.

        Args:
            employee_id: Unique employee identifier
            access_start: Access period start datetime
            access_end: Access period end datetime
            display_name: Optional display name
            is_active: Whether employee is active
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO employees (employee_id, display_name, access_start, access_end, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                display_name = excluded.display_name,
                access_start = excluded.access_start,
                access_end = excluded.access_end,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
        """, (employee_id, display_name, access_start.isoformat(), access_end.isoformat(),
              int(is_active), now, now))

        self.conn.commit()
        logger.info(f"Upserted employee {employee_id}")

    def add_embedding(
        self,
        employee_id: str,
        embedding: np.ndarray,
        photo_hash: Optional[str] = None
    ) -> int:
        """
        Add face embedding for an employee.

        Args:
            employee_id: Employee identifier
            embedding: Face embedding vector
            photo_hash: Optional SHA256 hash of source photo

        Returns:
            Embedding record ID
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        # Convert numpy array to bytes
        embedding_bytes = embedding.tobytes()

        cursor.execute("""
            INSERT INTO embeddings (employee_id, embedding, photo_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (employee_id, embedding_bytes, photo_hash, now))

        self.conn.commit()
        embedding_id = cursor.lastrowid
        logger.info(f"Added embedding {embedding_id} for employee {employee_id}")
        return embedding_id

    def delete_embeddings(self, employee_id: str) -> None:
        """
        Delete all embeddings for an employee.

        Args:
            employee_id: Employee identifier
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM embeddings WHERE employee_id = ?", (employee_id,))
        self.conn.commit()
        logger.info(f"Deleted embeddings for employee {employee_id}")

    def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """
        Get employee record by ID.

        Args:
            employee_id: Employee identifier

        Returns:
            Employee dict or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def get_active_employees_with_embeddings(self) -> List[Tuple[Dict[str, Any], List[np.ndarray]]]:
        """
        Get all active employees with their embeddings.

        Returns:
            List of (employee_dict, embeddings_list) tuples
        """
        cursor = self.conn.cursor()

        # Get active employees
        cursor.execute("""
            SELECT * FROM employees
            WHERE is_active = 1
        """)
        employees = [dict(row) for row in cursor.fetchall()]

        result = []
        for emp in employees:
            # Get embeddings for this employee
            cursor.execute("""
                SELECT embedding FROM embeddings
                WHERE employee_id = ?
            """, (emp['employee_id'],))

            embeddings = []
            for row in cursor.fetchall():
                # Convert bytes back to numpy array
                embedding_bytes = row[0]
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                embeddings.append(embedding)

            if embeddings:  # Only include employees with at least one embedding
                result.append((emp, embeddings))

        return result

    def update_employee_period(
        self,
        employee_id: str,
        access_start: datetime,
        access_end: datetime
    ) -> bool:
        """
        Update employee access period.

        Args:
            employee_id: Employee identifier
            access_start: New access start datetime
            access_end: New access end datetime

        Returns:
            True if updated, False if employee not found
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            UPDATE employees
            SET access_start = ?, access_end = ?, updated_at = ?
            WHERE employee_id = ?
        """, (access_start.isoformat(), access_end.isoformat(), now, employee_id))

        self.conn.commit()
        updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated period for employee {employee_id}")
        else:
            logger.warning(f"Employee {employee_id} not found for period update")

        return updated

    def deactivate_employee(self, employee_id: str) -> bool:
        """
        Deactivate an employee.

        Args:
            employee_id: Employee identifier

        Returns:
            True if deactivated, False if employee not found
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            UPDATE employees
            SET is_active = 0, updated_at = ?
            WHERE employee_id = ?
        """, (now, employee_id))

        self.conn.commit()
        updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Deactivated employee {employee_id}")
        else:
            logger.warning(f"Employee {employee_id} not found for deactivation")

        return updated

    def delete_employee(self, employee_id: str) -> bool:
        """
        Permanently delete an employee and their embeddings.

        Args:
            employee_id: Employee identifier

        Returns:
            True if deleted, False if employee not found
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))
        self.conn.commit()

        deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted employee {employee_id}")
        else:
            logger.warning(f"Employee {employee_id} not found for deletion")

        return deleted

    def log_access_attempt(
        self,
        event_type: str,
        result: str,
        employee_id: Optional[str] = None,
        matched_employee_id: Optional[str] = None,
        similarity_score: Optional[float] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an access attempt to audit log.

        Args:
            event_type: Type of event (e.g., 'face_recognition', 'admin_command')
            result: Result status (e.g., 'granted', 'denied')
            employee_id: Employee ID if known
            matched_employee_id: Matched employee ID from recognition
            similarity_score: Recognition similarity score
            reason: Reason for the result
            metadata: Additional metadata as dict
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        metadata_json = json.dumps(metadata) if metadata else None

        cursor.execute("""
            INSERT INTO audit_log (timestamp, event_type, employee_id, matched_employee_id,
                                   similarity_score, result, reason, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, event_type, employee_id, matched_employee_id, similarity_score,
              result, reason, metadata_json))

        self.conn.commit()

    def get_audit_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs with optional filters.

        Args:
            start_time: Filter logs after this time
            end_time: Filter logs before this time
            employee_id: Filter by employee ID
            limit: Maximum number of records

        Returns:
            List of audit log records
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        if employee_id:
            query += " AND (employee_id = ? OR matched_employee_id = ?)"
            params.extend([employee_id, employee_id])

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_system_status(self) -> Dict[str, Any]:
        """
        Get system status summary.

        Returns:
            Dict with system statistics
        """
        cursor = self.conn.cursor()

        # Count employees
        cursor.execute("SELECT COUNT(*) FROM employees WHERE is_active = 1")
        active_employees = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM employees")
        total_employees = cursor.fetchone()[0]

        # Count embeddings
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        total_embeddings = cursor.fetchone()[0]

        # Recent access attempts
        cursor.execute("""
            SELECT COUNT(*) FROM audit_log
            WHERE timestamp >= datetime('now', '-1 hour')
        """)
        recent_attempts = cursor.fetchone()[0]

        return {
            'active_employees': active_employees,
            'total_employees': total_employees,
            'total_embeddings': total_embeddings,
            'recent_attempts_1h': recent_attempts
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
