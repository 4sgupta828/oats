"""Event type constants for OATS agent system."""


class EventType:
    """Standard event types emitted by the agent."""

    # Execution lifecycle
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_RESUMED = "execution_resumed"

    # Turn lifecycle
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"

    # LLM events
    LLM_CALLED = "llm_called"
    LLM_RESPONSE_SUCCESS = "llm_response_success"
    LLM_RESPONSE_FAILED = "llm_response_failed"

    # Tool events
    TOOL_STARTED = "tool_started"
    TOOL_SUCCESS = "tool_success"
    TOOL_FAILED = "tool_failed"

    # User interaction events
    USER_INTERRUPT = "user_interrupt"
    USER_FEEDBACK_RECEIVED = "user_feedback_received"
    LLM_REQUESTS_INPUT = "llm_requests_input"
    LLM_REQUESTS_APPROVAL = "llm_requests_approval"


class ExecutionStatus:
    """Execution status constants."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
