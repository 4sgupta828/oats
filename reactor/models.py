# reactor/models.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ScratchpadEntry(BaseModel):
    """Single entry in the ReAct scratchpad history."""
    turn: int = Field(..., description="Turn number in the conversation")
    thought: str = Field(..., description="Agent's reasoning for this turn")
    intent: Optional[str] = Field(None, description="Agent's classified intent for this turn")
    action: Dict[str, Any] = Field(..., description="Tool action taken")
    observation: str = Field(..., description="Result of the action")
    timestamp: datetime = Field(default_factory=datetime.now)
    duration_ms: Optional[int] = None

class ReActState(BaseModel):
    """Complete state of the ReAct agent execution."""
    goal: str = Field(..., description="High-level user objective")
    scratchpad: List[ScratchpadEntry] = Field(default_factory=list, description="History of all turns")
    turn_count: int = Field(default=0, description="Current turn number")
    max_turns: int = Field(default=10, description="Maximum allowed turns")
    is_complete: bool = Field(default=False, description="Whether the goal has been achieved")
    completion_reason: Optional[str] = None
    total_cost: float = Field(default=0.0, description="Cumulative cost of all actions")
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def reset_for_new_goal(self, new_goal: str) -> None:
        """Reset state for a completely new goal, clearing all history."""
        self.goal = new_goal
        self.scratchpad.clear()
        self.turn_count = 0
        self.is_complete = False
        self.completion_reason = None
        self.total_cost = 0.0
        self.start_time = datetime.now()
        self.end_time = None

    def is_same_goal(self, other_goal: str) -> bool:
        """Check if the provided goal is essentially the same as current goal."""
        # Simple string comparison - could be enhanced with semantic similarity
        return self.goal.strip().lower() == other_goal.strip().lower()

class ParsedLLMResponse(BaseModel):
    """Structured representation of LLM response."""
    thought: str = Field(..., description="Agent's reasoning")
    intent: Optional[str] = Field(None, description="Agent's classified intent")
    action: Dict[str, Any] = Field(..., description="Tool action to execute")
    is_finish: bool = Field(default=False, description="Whether this is a finish action")
    raw_response: str = Field(..., description="Original LLM response")

class ReActResult(BaseModel):
    """Final result of ReAct execution."""
    success: bool = Field(..., description="Whether the goal was achieved")
    state: ReActState = Field(..., description="Final agent state")
    error_message: Optional[str] = None
    execution_summary: str = Field(..., description="Human-readable summary")

    def get_total_duration_ms(self) -> int:
        """Calculate total execution duration."""
        if self.state.end_time and self.state.start_time:
            delta = self.state.end_time - self.state.start_time
            return int(delta.total_seconds() * 1000)
        return 0