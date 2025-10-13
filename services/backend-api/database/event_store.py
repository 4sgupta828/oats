"""Async PostgreSQL Event Store for OATS Agent Event-Driven Architecture."""

import asyncio
import asyncpg
import json
import uuid
import os
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AsyncEventStore:
    """Async PostgreSQL event store with connection pooling."""
    
    def __init__(self, connection_string: str, pool_size: int = 10):
        self.connection_string = connection_string
        self.pool = None
        self.pool_size = pool_size
        self._initialized = False
    
    async def initialize(self):
        """Initialize connection pool."""
        if self._initialized:
            return
            
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=self.pool_size,
                command_timeout=30,
                server_settings={
                    'application_name': 'oats_event_store',
                }
            )
            self._initialized = True
            logger.info(f"Event store initialized with pool size {self.pool_size}")
        except Exception as e:
            logger.error(f"Failed to initialize event store: {e}")
            raise
    
    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("Event store connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get connection from pool."""
        if not self._initialized:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            yield conn
    
    # === Core Operations ===
    
    async def create_execution(self, goal: str, user_id: str = None, 
                             max_turns: int = 15, metadata: Dict = None) -> str:
        """Create new execution with enhanced metadata."""
        execution_id = str(uuid.uuid4())
        
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO agent_executions 
                (id, goal, status, max_turns, user_id, metadata)
                VALUES ($1, $2, 'running', $3, $4, $5)
                """,
                execution_id, goal, max_turns, user_id, json.dumps(metadata or {})
            )
        
        logger.info(f"Created execution {execution_id} for goal: {goal[:100]}...")
        return execution_id
    
    async def emit_event(self, execution_id: str, turn_number: int,
                        event_type: str, event_data: Dict[str, Any], 
                        success: bool = None):
        """Emit event to stream."""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO agent_events 
                (execution_id, turn_number, event_type, event_data, success)
                VALUES ($1, $2, $3, $4, $5)
                """,
                execution_id, turn_number, event_type, 
                json.dumps(event_data), success
            )
        
        logger.debug(f"Emitted event {event_type} for execution {execution_id}, turn {turn_number}")
    
    async def get_events_since(self, execution_id: str, last_event_id: int = 0) -> List[Dict]:
        """Get events for SSE streaming."""
        async with self.get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, turn_number, event_type, event_data, success, created_at
                FROM agent_events
                WHERE execution_id = $1 AND id > $2
                ORDER BY id
                """,
                execution_id, last_event_id
            )
            
            events = []
            for row in rows:
                events.append({
                    'id': row['id'],
                    'turn_number': row['turn_number'],
                    'event_type': row['event_type'],
                    'event_data': json.loads(row['event_data']) if isinstance(row['event_data'], str) else row['event_data'],
                    'success': row['success'],
                    'created_at': row['created_at']
                })
            
            return events
    
    async def update_execution_status(self, execution_id: str, status: str):
        """Update execution status."""
        async with self.get_connection() as conn:
            if status in ['completed', 'failed']:
                await conn.execute(
                    """
                    UPDATE agent_executions 
                    SET status = $1, updated_at = NOW(), completed_at = NOW() 
                    WHERE id = $2
                    """,
                    status, execution_id
                )
            else:
                await conn.execute(
                    """
                    UPDATE agent_executions 
                    SET status = $1, updated_at = NOW() 
                    WHERE id = $2
                    """,
                    status, execution_id
                )
        
        logger.info(f"Updated execution {execution_id} status to {status}")
    
    async def get_execution_status(self, execution_id: str) -> Optional[Dict]:
        """Get current execution status and metadata."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, goal, max_turns, user_id, metadata, 
                       created_at, updated_at, completed_at
                FROM agent_executions 
                WHERE id = $1
                """,
                execution_id
            )
            
            if row:
                return {
                    'id': execution_id,
                    'status': row['status'],
                    'goal': row['goal'],
                    'max_turns': row['max_turns'],
                    'user_id': row['user_id'],
                    'metadata': json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'completed_at': row['completed_at']
                }
            return None
    
    # === User Feedback ===
    
    async def submit_feedback(self, execution_id: str, turn_number: int,
                             feedback_type: str, feedback_data: Dict[str, Any]):
        """Submit user feedback."""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO user_feedback 
                (execution_id, turn_number, feedback_type, feedback_data)
                VALUES ($1, $2, $3, $4)
                """,
                execution_id, turn_number, feedback_type, 
                json.dumps(feedback_data)
            )
        
        logger.info(f"Submitted {feedback_type} feedback for execution {execution_id}, turn {turn_number}")
    
    async def check_feedback(self, execution_id: str, turn_number: int) -> Optional[Dict]:
        """Check for pending feedback at turn start."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, feedback_type, feedback_data
                FROM user_feedback
                WHERE execution_id = $1 
                  AND turn_number <= $2 
                  AND NOT processed
                ORDER BY id
                LIMIT 1
                """,
                execution_id, turn_number
            )
            
            if row:
                # Mark as processed
                await conn.execute(
                    "UPDATE user_feedback SET processed = TRUE WHERE id = $1",
                    row['id']
                )
                
                return {
                    'id': row['id'],
                    'feedback_type': row['feedback_type'],
                    'feedback_data': json.loads(row['feedback_data']) if isinstance(row['feedback_data'], str) else row['feedback_data']
                }
            
            return None
    
    # === Analytics & Debugging ===
    
    async def get_execution_summary(self, execution_id: str) -> Dict:
        """Get summary of execution for debugging/analytics."""
        async with self.get_connection() as conn:
            # Get execution info
            exec_row = await conn.fetchrow(
                "SELECT * FROM agent_executions WHERE id = $1", execution_id
            )
            
            if not exec_row:
                return None
            
            # Get event counts by type
            event_counts = await conn.fetch(
                """
                SELECT event_type, COUNT(*) as count
                FROM agent_events
                WHERE execution_id = $1
                GROUP BY event_type
                ORDER BY count DESC
                """,
                execution_id
            )
            
            # Get turn count
            turn_count = await conn.fetchval(
                """
                SELECT MAX(turn_number) FROM agent_events WHERE execution_id = $1
                """,
                execution_id
            ) or 0
            
            # Get feedback count
            feedback_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_feedback WHERE execution_id = $1
                """,
                execution_id
            ) or 0
            
            return {
                'execution': dict(exec_row),
                'turn_count': turn_count,
                'event_counts': {row['event_type']: row['count'] for row in event_counts},
                'feedback_count': feedback_count
            }
    
    async def list_executions(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """List recent executions for a user."""
        async with self.get_connection() as conn:
            if user_id:
                rows = await conn.fetch(
                    """
                    SELECT id, goal, status, created_at, updated_at, completed_at
                    FROM agent_executions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    user_id, limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, goal, status, created_at, updated_at, completed_at
                    FROM agent_executions
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit
                )
            
            return [dict(row) for row in rows]

# Global event store instance
_event_store: Optional[AsyncEventStore] = None

async def get_event_store() -> AsyncEventStore:
    """Get global event store instance."""
    global _event_store
    if _event_store is None:
        connection_string = os.getenv("DATABASE_URL", "postgresql://localhost/oats")
        _event_store = AsyncEventStore(connection_string)
        await _event_store.initialize()
    return _event_store

async def close_event_store():
    """Close global event store instance."""
    global _event_store
    if _event_store:
        await _event_store.close()
        _event_store = None
