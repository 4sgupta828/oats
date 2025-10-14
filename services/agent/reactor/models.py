# reactor/models.py

from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

# Models for SRE/Infrastructure Co-pilot (v3 prompt format)

class Hypothesis(BaseModel):
    """Testable hypothesis with clear validation criteria."""
    claim: str = Field(..., description="Specific, falsifiable statement")
    test: str = Field(..., description="How the tool call will test this claim")
    signal: str = Field(..., description="What output confirms/denies the claim")

class DiagnosticMetadata(BaseModel):
    """Diagnostic metadata for SRE troubleshooting."""
    investigation_phase: Literal["TRIAGE", "ORIENT", "CORRELATE", "HYPOTHESIZE", "ISOLATE", "IDENTIFY_ROOT_CAUSE", "VERIFY"] = Field(..., description="Current investigation phase")
    layer_focus: Literal["INFRASTRUCTURE", "RUNTIME", "INTEGRATION", "BUSINESS_LOGIC"] = Field(..., description="Current layer under investigation")
    signal_quality: Literal["STRONG", "MEDIUM", "WEAK", "ABSENT"] = Field(..., description="Quality of evidence from last action")
    causality_level: Literal["SYMPTOM", "PROXIMATE_CAUSE", "ROOT_CAUSE"] = Field(..., description="Level of causality identified")
    confidence: Dict[str, Literal["HIGH", "MEDIUM", "LOW"]] = Field(..., description="Confidence levels for problem_definition, root_cause_identified, fix_will_work")

class FailureMetadata(BaseModel):
    """Metadata for failure recovery."""
    type: Literal["EXECUTION_FAILURE", "STRATEGIC_FAILURE"] = Field(..., description="Type of failure")
    category: str = Field(..., description="Specific error category")
    recovery_level: str = Field(..., description="Recovery level (E1-E4 or S0-S4)")
    recovery_plan: str = Field(..., description="What to do next")

class ReflectSection(BaseModel):
    """Reflection on the outcome of the last action."""
    turn: int = Field(..., description="Current turn number")
    outcome: Literal["SUCCESS", "FAILURE", "FIRST_TURN"] = Field(..., description="Outcome of last action")
    hypothesisResult: Literal["CONFIRMED", "INVALIDATED", "INCONCLUSIVE", "IRRELEVANT", "N/A"] = Field(..., description="Result of testing the previous hypothesis")
    insight: str = Field(..., description="Key learning from this turn")
    diagnostic: Optional[DiagnosticMetadata] = Field(None, description="Diagnostic metadata for SRE work")
    failure: Optional[FailureMetadata] = Field(None, description="Failure metadata if outcome was FAILURE")

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
    archetype: Literal["DIAGNOSE", "CREATE", "MODIFY", "PROVISION"] = Field(..., description="Task type (DIAGNOSE for RCA)")
    phase: str = Field(..., description="Current phase within the archetype")
    turns: int = Field(..., description="Number of turns spent on this task")

# SRE-specific diagnostic models
class Fact(BaseModel):
    """Observable, verified truth from tool output."""
    id: int = Field(..., description="Fact identifier")
    desc: str = Field(..., description="Observable truth from tool output")
    turn: int = Field(..., description="Turn when fact was discovered")
    layer: Optional[Literal["INFRASTRUCTURE", "RUNTIME", "INTEGRATION", "BUSINESS_LOGIC"]] = Field(None, description="Which layer this fact relates to")

class Symptom(BaseModel):
    """User-facing observable failure."""
    description: str = Field(..., description="User-facing failure description")
    layer: Literal["INFRASTRUCTURE", "RUNTIME", "INTEGRATION", "BUSINESS_LOGIC"] = Field(..., description="Layer where symptom appears")
    scope: Optional[str] = Field(None, description="Scope of impact (e.g., '15% of requests')")
    started: Optional[str] = Field(None, description="When symptom started (ISO 8601)")

class TimelineEvent(BaseModel):
    """Event in the system timeline."""
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    event: str = Field(..., description="What happened")
    relevance: Literal["HIGH", "MEDIUM", "LOW"] = Field(..., description="Relevance to symptom")
    factIDs: List[int] = Field(default_factory=list, description="Related fact IDs")

class CausalLink(BaseModel):
    """Link in the causal chain."""
    level: Literal["symptom", "proximate_cause", "root_cause"] = Field(..., description="Causality level")
    layer: Literal["INFRASTRUCTURE", "RUNTIME", "INTEGRATION", "BUSINESS_LOGIC"] = Field(..., description="Layer this link relates to")
    description: str = Field(..., description="Clear description of this causal link")
    factIDs: List[int] = Field(default_factory=list, description="Supporting fact IDs")

class CompetingHypothesis(BaseModel):
    """Competing hypothesis for differential diagnosis."""
    claim: str = Field(..., description="Specific hypothesis about root cause")
    layer: Literal["INFRASTRUCTURE", "RUNTIME", "INTEGRATION", "BUSINESS_LOGIC"] = Field(..., description="Layer this hypothesis tests")
    likelihood: Literal["HIGH", "MEDIUM", "LOW"] = Field(..., description="Current likelihood assessment")
    evidence_for: List[str] = Field(default_factory=list, description="Supporting observations")
    evidence_against: List[str] = Field(default_factory=list, description="Contradicting observations")
    discriminator: str = Field(..., description="Test that would prove/disprove this")

class Context(BaseModel):
    """Four dimensions of system context."""
    architecture: Optional[str] = Field(None, description="What this component is and its role")
    dependencies: Optional[str] = Field(None, description="What it needs and who needs it")
    temporal: Optional[str] = Field(None, description="When it started and what changed")
    environment: Optional[str] = Field(None, description="Where it runs and resource limits")

class Diagnosis(BaseModel):
    """Complete diagnostic state for infrastructure troubleshooting."""
    symptom: Optional[Symptom] = Field(None, description="The observable failure")
    context: Optional[Context] = Field(None, description="Four dimensions of context")
    timeline: List[TimelineEvent] = Field(default_factory=list, description="Timeline of relevant changes")
    causalChain: List[CausalLink] = Field(default_factory=list, description="Chain from symptom to root cause")
    layerStatus: Optional[Dict[str, str]] = Field(None, description="Status of each layer (HEALTHY/DEGRADED/SUSPECT)")
    competingHypotheses: List[CompetingHypothesis] = Field(default_factory=list, description="Alternative theories for differential diagnosis")
    rootCause: Optional[str] = Field(None, description="Identified root cause with evidence")

class State(BaseModel):
    """Agent's complete state and understanding."""
    goal: str = Field(..., description="The user's high-level objective")
    tasks: List[Task] = Field(default_factory=list, description="Decomposed sub-tasks")
    active: Optional[ActiveTask] = Field(None, description="Currently active task")
    facts: List[Fact] = Field(default_factory=list, description="Observable, verified truths from tool outputs")
    ruled_out: List[str] = Field(default_factory=list, description="Invalidated hypotheses and ruled-out explanations")
    unknowns: List[str] = Field(default_factory=list, description="Key remaining questions or information gaps")
    diagnosis: Optional[Diagnosis] = Field(None, description="Diagnostic state for infrastructure troubleshooting")

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

    def continue_with_summarized_context(self, new_goal: str, keep_last_n_turns: int = 3) -> Dict[str, Any]:
        """
        Continue investigation with refined goal, keeping learnings but summarizing old context.

        This method:
        - Updates the goal to the refined version
        - Keeps all strategic state (facts, ruled_out, unknowns, diagnosis)
        - Condenses older transcript entries into a summary
        - Keeps last N turns for immediate context
        - Does NOT reset turn count (maintains historical context)

        Returns summary statistics for user confirmation.
        """
        # Capture stats before summarization
        stats = {
            "old_goal": self.goal,
            "new_goal": new_goal,
            "total_turns_before": self.turn_count,
            "transcript_entries_before": len(self.transcript),
            "facts_count": len(self.state.facts) if self.state else 0,
            "ruled_out_count": len(self.state.ruled_out) if self.state else 0,
            "unknowns_count": len(self.state.unknowns) if self.state else 0,
            "has_diagnosis": self.state.diagnosis is not None if self.state else False,
        }

        # Update goal
        self.goal = new_goal
        if self.state:
            self.state.goal = new_goal

        # Summarize transcript if needed
        if len(self.transcript) > keep_last_n_turns:
            self._summarize_transcript(keep_last_n_turns)
            stats["transcript_entries_after"] = len(self.transcript)
            stats["turns_summarized"] = stats["transcript_entries_before"] - keep_last_n_turns
        else:
            stats["transcript_entries_after"] = len(self.transcript)
            stats["turns_summarized"] = 0

        return stats

    def _summarize_transcript(self, keep_last_n_turns: int) -> None:
        """
        Condense older transcript entries into a single summary entry.
        Keeps last N turns for immediate context.
        """
        if len(self.transcript) <= keep_last_n_turns:
            return  # Nothing to summarize

        # Split transcript
        older_turns = self.transcript[:-keep_last_n_turns]
        recent_turns = self.transcript[-keep_last_n_turns:]

        # Create summary entry from older turns
        summary_entry = self._create_summary_entry(older_turns)

        # Update transcript: [summary] + recent turns
        self.transcript = [summary_entry] + recent_turns

    def _create_summary_entry(self, turns: List[TranscriptEntry]) -> TranscriptEntry:
        """
        Create a summary transcript entry from multiple older turns.
        Captures key outcomes, learnings, and failed approaches.
        """
        if not turns:
            # Return empty summary if no turns
            return TranscriptEntry(
                turn=0,
                reflect=ReflectSection(
                    turn=0,
                    outcome="FIRST_TURN",
                    hypothesisResult="N/A",
                    insight="Context summary placeholder"
                ),
                strategize=StrategizeSection(
                    reasoning="Summarized context from previous investigation",
                    hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                    ifInvalidated="N/A"
                ),
                state=self.state if self.state else State(goal=self.goal),
                act=ActSection(tool="context_summary", params={}),
                observation="No previous context to summarize",
                duration_ms=0
            )

        # Extract key information from turns
        turn_range = f"{turns[0].turn}-{turns[-1].turn}"
        tools_used = list(set(turn.act.tool for turn in turns))

        # Count outcomes
        successes = sum(1 for t in turns if t.reflect.outcome == "SUCCESS")
        failures = sum(1 for t in turns if t.reflect.outcome == "FAILURE")

        # Extract key insights (from successful turns and failures)
        insights = []
        failed_approaches = []

        for turn in turns:
            if turn.reflect.outcome == "SUCCESS" and turn.reflect.insight:
                # Capture successful insights
                if turn.reflect.insight not in ["N/A", ""]:
                    insights.append(f"Turn {turn.turn}: {turn.reflect.insight[:150]}")
            elif turn.reflect.outcome == "FAILURE":
                # Capture failed approaches
                approach = f"{turn.act.tool}: {turn.strategize.hypothesis.claim[:100]}"
                failed_approaches.append(approach)

        # Build summary observation
        summary_lines = [
            f"📋 CONTEXT SUMMARY (Turns {turn_range})",
            f"",
            f"Turns executed: {len(turns)}",
            f"Success/Failure: {successes}/{failures}",
            f"Tools used: {', '.join(tools_used[:5])}{'...' if len(tools_used) > 5 else ''}",
            f"",
        ]

        if insights:
            summary_lines.append("Key learnings:")
            for insight in insights[:5]:  # Top 5 insights
                summary_lines.append(f"  • {insight}")
            summary_lines.append("")

        if failed_approaches:
            summary_lines.append("Failed approaches (ruled out):")
            for approach in failed_approaches[:5]:  # Top 5 failed approaches
                summary_lines.append(f"  • {approach}")
            summary_lines.append("")

        summary_lines.append("💡 All verified facts, ruled-out hypotheses, and diagnostic state preserved in agent state.")

        observation = "\n".join(summary_lines)

        # Create summary transcript entry
        return TranscriptEntry(
            turn=0,  # Special turn number for summary
            reflect=ReflectSection(
                turn=0,
                outcome="SUCCESS",
                hypothesisResult="N/A",
                insight=f"Summarized {len(turns)} turns of prior investigation"
            ),
            strategize=StrategizeSection(
                reasoning="Context from previous investigation phase, condensed to prevent context bloat",
                hypothesis=Hypothesis(
                    claim="Prior context summarized for continuation",
                    test="N/A",
                    signal="N/A"
                ),
                ifInvalidated="N/A"
            ),
            state=self.state if self.state else State(goal=self.goal),
            act=ActSection(
                tool="context_summary",
                params={
                    "turn_range": turn_range,
                    "turns_summarized": len(turns),
                    "tools_used": tools_used
                }
            ),
            observation=observation,
            duration_ms=0
        )

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