# uf_flow/core/models.py

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional
from .logging_config import get_logger

logger = get_logger('models')

# --- Foundational Data Models ---

class Goal(BaseModel):
    """Represents the high-level user objective."""
    id: str = Field(..., description="Unique identifier for the goal.")
    description: str = Field(..., description="Natural language description of the goal.")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Operational constraints like budget, priority, etc.")

class Policy(BaseModel):
    """Defines a security or operational guardrail."""
    name: str
    effect: Literal["allow", "deny", "require_approval"]
    action: List[str] = Field(..., description="Actions this policy applies to, e.g., 'uf:s3-delete-bucket'.")
    resource: List[str] = Field(..., description="Resources this policy applies to, e.g., 'arn:aws:s3:::prod-data/*'.")

class ObservationSummary(BaseModel):
    """Layer 1: Tool-side summary (the 'receipt') for large outputs."""
    total_lines: Optional[int] = None
    total_chars: Optional[int] = None
    total_matches: Optional[int] = None
    files_with_matches: Optional[int] = None
    status_flag: str = Field(default="success", description="success/failure/partial")
    full_output_saved_to: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Tool-specific metrics")

class ToolResult(BaseModel):
    """Represents the outcome of a single tool execution."""
    status: Literal["success", "failure"]
    output: Any
    error: Optional[str] = None
    cost: Optional[float] = None
    duration_ms: Optional[int] = None
    # Layer 1: Receipt - metadata summary for large outputs
    summary: Optional[ObservationSummary] = None
    
# --- UF (Tool) Definition Models ---

class InputResolverMapping(BaseModel):
    """Defines where to pull a single piece of data from."""
    source: Literal["upstream", "context", "literal"]
    value_selector: str = Field(..., description="JSONPath-like selector, e.g., '{output.file_path}'.")
    node_id: Optional[str] = None # Required if source is 'upstream'

class Invocation(BaseModel):
    """Defines the type and template for the actual tool call."""
    type: Literal["shell", "python", "http-api", "llm-reasoning"]
    template: str
    params: Dict[str, str]

class InputResolver(BaseModel):
    """
    WHY: This is the key to decoupling. It makes a UF a "consumer" of data,
    allowing it to be reused in different workflows without modification.
    """
    data_mapping: Dict[str, InputResolverMapping]
    invocation: Invocation

class UFDescriptor(BaseModel):
    """The complete, static definition of a tool-calling node."""
    name: str
    version: str
    description: str = Field(..., description="Semantic description used for search.")
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    # This serves as a template; it will be instantiated and possibly modified for each PlanNode.
    resolver_template: InputResolver
    
    # Store the callable function for execution
    callable_func: Optional[Any] = Field(default=None, exclude=True) 

# --- Dynamic Execution & State Models ---

class PlanNode(BaseModel):
    """Represents a single step in a dynamic plan."""
    id: str
    uf_name: str
    status: Literal["pending", "running", "success", "failure", "skipped"] = "pending"
    # This is an INSTANCE of the resolver, which can be modified by the agent at runtime.
    input_resolver: InputResolver
    result: Optional[ToolResult] = None

class Plan(BaseModel):
    """Represents the agent's current strategy for achieving a goal. This is a living document."""
    id: str
    goal_id: str
    status: Literal["running", "succeeded", "failed", "paused"]
    # Using a simple adjacency list to represent the DAG. Key is node_id.
    graph: Dict[str, List[str]] 
    nodes: Dict[str, PlanNode]
    confidence_score: float = 1.0

class WorldState(BaseModel):
    """A snapshot of the agent's current understanding of its environment and progress."""
    goal: Goal
    plan: Plan
    execution_history: List[ToolResult] = Field(default_factory=list)
    environment_data: Dict[str, Any] = Field(default_factory=dict)
    cumulative_cost: float = 0.0