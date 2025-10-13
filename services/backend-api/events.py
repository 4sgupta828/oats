"""Event types and models for OATS Agent Event-Driven Architecture."""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel

class EventType(str, Enum):
    """Core event types for the agent execution lifecycle."""
    
    # === Turn Lifecycle ===
    TURN_STARTED = "turn_started"
    LLM_CALLED = "llm_called"
    
    # === LLM Response Handling ===
    LLM_RESPONSE_SUCCESS = "llm_response_success"
    LLM_RESPONSE_FAILED = "llm_response_failed"
    
    # === Tool Execution ===
    TOOL_STARTED = "tool_started"
    TOOL_SUCCESS = "tool_success"
    TOOL_FAILED = "tool_failed"
    
    # === User Interaction ===
    USER_FEEDBACK_RECEIVED = "user_feedback_received"
    USER_INTERRUPT = "user_interrupt"
    
    # === LLM Escalation ===
    LLM_REQUESTS_INPUT = "llm_requests_input"
    LLM_REQUESTS_APPROVAL = "llm_requests_approval"
    
    # === Execution Lifecycle ===
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_RESUMED = "execution_resumed"

class FeedbackType(str, Enum):
    """User feedback types."""
    INTERRUPT = "interrupt"
    INPUT = "input"
    APPROVAL = "approval"

class ExecutionStatus(str, Enum):
    """Execution status values."""
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

# === Event Data Models ===

class TurnStartedEvent(BaseModel):
    """Event data for turn start."""
    turn_number: int
    goal: str
    max_turns: int

class LLMCalledEvent(BaseModel):
    """Event data for LLM invocation."""
    messages_count: int
    model: Optional[str] = None
    estimated_tokens: Optional[int] = None

class LLMResponseEvent(BaseModel):
    """Event data for LLM response (success/failure)."""
    turn_number: int
    raw_response_length: int
    parsed_successfully: bool
    error_message: Optional[str] = None
    reflect: Optional[Dict[str, Any]] = None
    strategize: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None

class ToolExecutionEvent(BaseModel):
    """Event data for tool execution."""
    tool_name: str
    tool_version: str
    parameters: Dict[str, Any]
    execution_time_ms: Optional[int] = None
    observation_length: Optional[int] = None
    error_message: Optional[str] = None

class UserFeedbackEvent(BaseModel):
    """Event data for user feedback."""
    feedback_type: FeedbackType
    turn_number: int
    feedback_data: Dict[str, Any]
    processing_required: bool = True

class LLMEscalationEvent(BaseModel):
    """Event data for LLM escalation requests."""
    escalation_type: str  # 'input' or 'approval'
    request_message: str
    action_description: Optional[str] = None
    risk_level: Optional[str] = None

class ExecutionLifecycleEvent(BaseModel):
    """Event data for execution lifecycle events."""
    goal: str
    max_turns: int
    completion_reason: Optional[str] = None
    error_message: Optional[str] = None
    turns_completed: Optional[int] = None
    execution_time_ms: Optional[int] = None

# === Event Factory Functions ===

def create_turn_started_event(turn_number: int, goal: str, max_turns: int) -> Dict[str, Any]:
    """Create turn started event data."""
    return TurnStartedEvent(
        turn_number=turn_number,
        goal=goal,
        max_turns=max_turns
    ).model_dump()

def create_llm_called_event(messages_count: int, model: str = None) -> Dict[str, Any]:
    """Create LLM called event data."""
    return LLMCalledEvent(
        messages_count=messages_count,
        model=model
    ).model_dump()

def create_llm_response_event(
    turn_number: int,
    raw_response: str,
    parsed_response: Optional[Dict] = None,
    error: Optional[str] = None
) -> Dict[str, Any]:
    """Create LLM response event data."""
    return LLMResponseEvent(
        turn_number=turn_number,
        raw_response_length=len(raw_response),
        parsed_successfully=parsed_response is not None,
        error_message=error,
        reflect=parsed_response.get('reflect') if parsed_response else None,
        strategize=parsed_response.get('strategize') if parsed_response else None,
        action=parsed_response.get('act') if parsed_response else None
    ).model_dump()

def create_tool_execution_event(
    tool_name: str,
    tool_version: str,
    parameters: Dict[str, Any],
    execution_time_ms: int = None,
    observation: str = None,
    error: str = None
) -> Dict[str, Any]:
    """Create tool execution event data."""
    return ToolExecutionEvent(
        tool_name=tool_name,
        tool_version=tool_version,
        parameters=parameters,
        execution_time_ms=execution_time_ms,
        observation_length=len(observation) if observation else None,
        error_message=error
    ).model_dump()

def create_user_feedback_event(
    feedback_type: FeedbackType,
    turn_number: int,
    feedback_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Create user feedback event data."""
    return UserFeedbackEvent(
        feedback_type=feedback_type,
        turn_number=turn_number,
        feedback_data=feedback_data
    ).model_dump()

def create_llm_escalation_event(
    escalation_type: str,
    request_message: str,
    action_description: str = None,
    risk_level: str = None
) -> Dict[str, Any]:
    """Create LLM escalation event data."""
    return LLMEscalationEvent(
        escalation_type=escalation_type,
        request_message=request_message,
        action_description=action_description,
        risk_level=risk_level
    ).model_dump()

def create_execution_lifecycle_event(
    event_type: EventType,
    goal: str,
    max_turns: int,
    completion_reason: str = None,
    error_message: str = None,
    turns_completed: int = None,
    execution_time_ms: int = None
) -> Dict[str, Any]:
    """Create execution lifecycle event data."""
    return ExecutionLifecycleEvent(
        goal=goal,
        max_turns=max_turns,
        completion_reason=completion_reason,
        error_message=error_message,
        turns_completed=turns_completed,
        execution_time_ms=execution_time_ms
    ).model_dump()

# === Event Validation ===

def validate_event_data(event_type: EventType, event_data: Dict[str, Any]) -> bool:
    """Validate event data against expected schema."""
    try:
        if event_type == EventType.TURN_STARTED:
            TurnStartedEvent(**event_data)
        elif event_type == EventType.LLM_CALLED:
            LLMCalledEvent(**event_data)
        elif event_type in [EventType.LLM_RESPONSE_SUCCESS, EventType.LLM_RESPONSE_FAILED]:
            LLMResponseEvent(**event_data)
        elif event_type in [EventType.TOOL_STARTED, EventType.TOOL_SUCCESS, EventType.TOOL_FAILED]:
            ToolExecutionEvent(**event_data)
        elif event_type == EventType.USER_FEEDBACK_RECEIVED:
            UserFeedbackEvent(**event_data)
        elif event_type in [EventType.LLM_REQUESTS_INPUT, EventType.LLM_REQUESTS_APPROVAL]:
            LLMEscalationEvent(**event_data)
        elif event_type in [EventType.EXECUTION_STARTED, EventType.EXECUTION_COMPLETED, 
                           EventType.EXECUTION_FAILED, EventType.EXECUTION_PAUSED, EventType.EXECUTION_RESUMED]:
            ExecutionLifecycleEvent(**event_data)
        
        return True
    except Exception:
        return False
