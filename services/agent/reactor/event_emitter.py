"""Event emitter interface for agent controller."""

from typing import Dict, Any, Protocol
from abc import ABC, abstractmethod


class EventEmitter(Protocol):
    """Protocol for event emitters."""

    async def emit(
        self,
        execution_id: str,
        turn_number: int,
        event_type: str,
        event_data: Dict[str, Any],
        success: bool = None,
    ):
        """Emit an event."""
        ...


class NullEventEmitter:
    """Null object pattern - does nothing (for backward compatibility)."""

    async def emit(
        self,
        execution_id: str,
        turn_number: int,
        event_type: str,
        event_data: Dict[str, Any],
        success: bool = None,
    ):
        """No-op emit."""
        pass


class EventStoreEmitter:
    """Event emitter that writes to the event store."""

    def __init__(self, event_store):
        self.event_store = event_store

    async def emit(
        self,
        execution_id: str,
        turn_number: int,
        event_type: str,
        event_data: Dict[str, Any],
        success: bool = None,
    ):
        """Emit event to event store."""
        await self.event_store.emit_event(
            execution_id, turn_number, event_type, event_data, success
        )
