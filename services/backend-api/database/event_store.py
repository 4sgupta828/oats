"""Minimal PostgreSQL Event Store - Following simplified specification."""

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Optional, List, Dict, Any
import uuid
import os
import logging

logger = logging.getLogger(__name__)


class EventStore:
    """Minimal PostgreSQL event store - sync implementation."""

    def __init__(self, connection_string: str):
        self.conn_string = connection_string
        self._conn = None

    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.conn_string)
        # Check if connection is in a bad state and rollback
        try:
            if self._conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_INERROR:
                self._conn.rollback()
                logger.warning("Rolled back failed transaction")
        except Exception as e:
            logger.error(f"Failed to check transaction status: {e}")
            # Try to reconnect
            try:
                self._conn.close()
            except:
                pass
            self._conn = psycopg2.connect(self.conn_string)
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Event store connection closed")

    # === Core Operations ===

    def create_execution(self, goal: str) -> str:
        """Create new execution."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                execution_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO agent_executions (id, goal, status) VALUES (%s, %s, 'running')",
                    (execution_id, goal)
                )
                conn.commit()
                logger.info(f"Created execution {execution_id} for goal: {goal[:100]}...")
                return execution_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create execution: {e}")
            raise

    def emit_event(self, execution_id: str, turn_number: int,
                   event_type: str, event_data: Dict[str, Any], success: bool = None):
        """Emit event to stream."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_events
                    (execution_id, turn_number, event_type, event_data, success)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (execution_id, turn_number, event_type, Json(event_data), success)
                )
                conn.commit()
                logger.debug(f"Emitted event {event_type} for execution {execution_id}, turn {turn_number}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to emit event: {e}")
            raise

    def get_events_since(self, execution_id: str, last_event_id: int = 0) -> List[Dict]:
        """Get events for SSE streaming."""
        conn = self._get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, turn_number, event_type, event_data, success, created_at
                FROM agent_events
                WHERE execution_id = %s AND id > %s
                ORDER BY id
                """,
                (execution_id, last_event_id)
            )
            return [dict(row) for row in cur.fetchall()]

    def update_status(self, execution_id: str, status: str):
        """Update execution status."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_executions SET status = %s, updated_at = NOW() WHERE id = %s",
                    (status, execution_id)
                )
                if status in ['completed', 'failed', 'cancelled']:
                    cur.execute(
                        "UPDATE agent_executions SET completed_at = NOW() WHERE id = %s",
                        (execution_id,)
                    )
                conn.commit()
                logger.info(f"Updated execution {execution_id} status to {status}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update status: {e}")
            raise

    def get_execution_status(self, execution_id: str) -> Optional[Dict]:
        """Get execution status."""
        conn = self._get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, goal, status, created_at, updated_at, completed_at
                FROM agent_executions
                WHERE id = %s
                """,
                (execution_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    # === User Feedback ===

    def submit_feedback(self, execution_id: str, turn_number: int,
                       feedback_type: str, feedback_data: Dict[str, Any]):
        """Submit user feedback."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_feedback
                    (execution_id, turn_number, feedback_type, feedback_data)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (execution_id, turn_number, feedback_type, Json(feedback_data))
                )
                conn.commit()
                logger.info(f"Submitted {feedback_type} feedback for execution {execution_id}, turn {turn_number}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to submit feedback: {e}")
            raise

    def check_feedback(self, execution_id: str, turn_number: int) -> Optional[Dict]:
        """Check for pending feedback at turn start."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, feedback_type, feedback_data
                    FROM user_feedback
                    WHERE execution_id = %s
                      AND turn_number <= %s
                      AND NOT processed
                    ORDER BY id
                    LIMIT 1
                    """,
                    (execution_id, turn_number)
                )
                row = cur.fetchone()
                if row:
                    # Mark as processed
                    cur.execute(
                        "UPDATE user_feedback SET processed = TRUE WHERE id = %s",
                        (row['id'],)
                    )
                    conn.commit()
                    return dict(row)
                return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to check feedback: {e}")
            raise

    def check_abort_flag(self, execution_id: str) -> bool:
        """Check if execution should be aborted."""
        conn = self._get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status FROM agent_executions WHERE id = %s",
                (execution_id,)
            )
            row = cur.fetchone()
            return row['status'] == 'cancelled' if row else False

    # === Utility Methods ===

    def list_executions(self, limit: int = 50) -> List[Dict]:
        """List recent executions."""
        conn = self._get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, goal, status, created_at, updated_at, completed_at
                FROM agent_executions
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_execution_summary(self, execution_id: str) -> Optional[Dict]:
        """
        Get execution summary including event statistics.
        Used for resume/continue decision making.
        """
        conn = self._get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get execution info
            cur.execute(
                """
                SELECT id, goal, status, created_at, updated_at, completed_at
                FROM agent_executions
                WHERE id = %s
                """,
                (execution_id,)
            )
            execution = cur.fetchone()
            if not execution:
                return None

            # Get event statistics
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_events,
                    MAX(turn_number) as max_turn,
                    COUNT(CASE WHEN event_type = 'tool_success' THEN 1 END) as successful_tools,
                    COUNT(CASE WHEN event_type = 'tool_failed' THEN 1 END) as failed_tools,
                    COUNT(CASE WHEN event_type LIKE '%%_completed' THEN 1 END) as completion_events
                FROM agent_events
                WHERE execution_id = %s
                """,
                (execution_id,)
            )
            stats = cur.fetchone()

            return {
                **dict(execution),
                "event_stats": dict(stats) if stats else {}
            }

    def update_execution_goal(self, execution_id: str, new_goal: str):
        """Update the goal of an existing execution (for continue mode)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_executions SET goal = %s, updated_at = NOW() WHERE id = %s",
                    (new_goal, execution_id)
                )
                conn.commit()
                logger.info(f"Updated execution {execution_id} goal to: {new_goal[:100]}...")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update execution goal: {e}")
            raise


# Global event store instance
_event_store: Optional[EventStore] = None


def get_event_store() -> EventStore:
    """Get global event store instance."""
    global _event_store
    if _event_store is None:
        connection_string = os.getenv(
            "DATABASE_URL", "postgresql://localhost/oatsdb"
        )
        _event_store = EventStore(connection_string)
    return _event_store


def close_event_store():
    """Close global event store instance."""
    global _event_store
    if _event_store:
        _event_store.close()
        _event_store = None
