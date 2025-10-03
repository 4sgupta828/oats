# reactor/models.py

from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

# New models for BasePrompt.md format

class Hypothesis(BaseModel):
    """Testable hypothesis with clear validation criteria."""
    claim: str = Field(..., description="Specific, falsifiable statement")
    test: str = Field(..., description="How the tool call will test this claim")
    signal: str = Field(..., description="What output confirms/denies the claim")

class ReflectSection(BaseModel):
    """Reflection on the outcome of the last action."""
    turn: int = Field(..., description="Current turn number")
    outcome: Literal["SUCCESS", "FAILURE", "FIRST_TURN"] = Field(..., description="Outcome of last action")
    hypothesisResult: Literal["CONFIRMED", "INVALIDATED", "INCONCLUSIVE", "IRRELEVANT", "N/A"] = Field(..., description="Result of testing the previous hypothesis")
    insight: str = Field(..., description="Key learning from this turn")

class StrategizeSection(BaseModel):
    """Strategy and hypothesis for the next action."""
    reasoning: str = Field(..., description="Why this is the most effective next step")
    hypothesis: Hypothesis = Field(..., description="Testable assumption for this turn")
    ifInvalidated: str = Field(..., description="Contingency plan if hypothesis is invalidated")

class Task(BaseModel):
    """A sub-task in the overall goal."""
    id: int = Field(..., description="Task identifier")
    desc: str = Field(..., description="Clear, verifiable sub-task description")
    status: Literal["active", "done", "blocked"] = Field(..., description="Current status of the task")

class ActiveTask(BaseModel):
    """Currently active task with its metadata."""
    id: int = Field(..., description="ID of the active task")
    archetype: Literal["INVESTIGATE", "CREATE", "MODIFY", "PROVISION", "UNORTHODOX"] = Field(..., description="Task type")
    phase: str = Field(..., description="Current phase within the archetype")
    turns: int = Field(..., description="Number of turns spent on this task")

class State(BaseModel):
    """Agent's complete state and understanding."""
    goal: str = Field(..., description="The user's high-level objective")
    tasks: List[Task] = Field(default_factory=list, description="Decomposed sub-tasks")
    active: Optional[ActiveTask] = Field(None, description="Currently active task")
    facts: List[str] = Field(default_factory=list, description="Observable, verified truths from tool outputs")
    ruled_out: List[str] = Field(default_factory=list, description="Invalidated hypotheses and ruled-out explanations")
    unknowns: List[str] = Field(default_factory=list, description="Key remaining questions or information gaps")

class ActSection(BaseModel):
    """Action to be executed."""
    tool: str = Field(..., description="Tool name to execute")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    safe: Optional[str] = Field(None, description="Safety justification (omit for read-only operations)")

class TranscriptEntry(BaseModel):
    """Single entry in the agent transcript - complete turn history."""
    turn: int = Field(..., description="Turn number")
    reflect: ReflectSection = Field(..., description="Reflection on last action")
    strategize: StrategizeSection = Field(..., description="Strategy for next action")
    state: State = Field(..., description="Agent's current state")
    act: ActSection = Field(..., description="Action to execute")
    observation: str = Field(..., description="Result of the action")
    timestamp: datetime = Field(default_factory=datetime.now)
    duration_ms: Optional[int] = None

class ReActState(BaseModel):
    """Complete state of the ReAct agent execution."""
    goal: str = Field(..., description="High-level user objective")
    state: Optional[State] = Field(None, description="Agent's evolving understanding")
    transcript: List[TranscriptEntry] = Field(default_factory=list, description="History of all turns")
    turn_count: int = Field(default=0, description="Current turn number")
    max_turns: int = Field(default=10, description="Maximum allowed turns")
    is_complete: bool = Field(default=False, description="Whether the goal has been achieved")
    completion_reason: Optional[str] = None
    total_cost: float = Field(default=0.0, description="Cumulative cost of all actions")
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @model_validator(mode='after')
    def initialize_state_with_goal(self):
        """Initialize state with goal if not provided."""
        if self.state is None:
            self.state = State(goal=self.goal)
        return self

    def reset_for_new_goal(self, new_goal: str) -> None:
        """Reset state for a completely new goal, clearing all history."""
        self.goal = new_goal
        self.state = State(goal=new_goal)
        self.transcript.clear()
        self.turn_count = 0
        self.is_complete = False
        self.completion_reason = None
        self.total_cost = 0.0
        self.start_time = datetime.now()
        self.end_time = None

    def is_same_goal(self, other_goal: str) -> bool:
        """Check if the provided goal is essentially the same as current goal."""
        return self.goal.strip().lower() == other_goal.strip().lower()

class ParsedLLMResponse(BaseModel):
    """Structured representation of LLM response in new JSON format."""
    reflect: ReflectSection = Field(..., description="Reflection section")
    strategize: StrategizeSection = Field(..., description="Strategy section")
    state: State = Field(..., description="Updated state")
    act: ActSection = Field(..., description="Action to execute")
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