# OATS System Flow Documentation

This document describes the complete data flow and chain of calls in the OATS (Observability & Automated Troubleshooting System) architecture, from user interaction to agent execution and back.

## Architecture Overview

```
┌─────────────────┐
│   User/Client   │
│   (curl/UI)     │
└────────┬────────┘
         │ HTTP POST /investigate
         │ {"goal": "...", "target_namespace": "default"}
         ▼
┌─────────────────────────────────────────────────┐
│         Backend API (FastAPI)                   │
│         Port: 8000                              │
│         Pod: oats-backend-api-*                 │
│                                                 │
│  Endpoints:                                     │
│  - POST /investigate                            │
│                                                 │
│  Components:                                    │
│  - main.py: API endpoint handlers              │
│  - k8s_service.py: K8s job creator             │
└────────┬────────────────────────────────────────┘
         │ Create Kubernetes Job
         │ BatchV1Api().create_namespaced_job()
         ▼
┌─────────────────────────────────────────────────┐
│         Kubernetes Cluster                      │
│                                                 │
│  Job: oats-agent-run-XXXXXXXX                   │
│  Pod: oats-agent-run-XXXXXXXX-XXXXX             │
│                                                 │
│  Container Image: oats-agent:v4                 │
│  Entry Point: python agent/main.py              │
│                                                 │
│  Environment Variables:                         │
│  - OATS_GOAL (from request)                     │
│  - ANTHROPIC_API_KEY (from secret)              │
│  - OPENAI_API_KEY (from secret)                 │
│                                                 │
│  Secrets:                                       │
│  - oats-api-keys (contains API keys)            │
└────────┬────────────────────────────────────────┘
         │ Execute Agent
         ▼
┌─────────────────────────────────────────────────┐
│         Agent (Python Container)                │
│                                                 │
│  Main Components:                               │
│  1. agent/main.py - Entry point                 │
│  2. reactor/agent_controller.py - ReAct loop    │
│  3. reactor/tool_executor.py - Tool execution   │
│  4. registry/main.py - Tool registry            │
│  5. core/llm.py - LLM client                    │
│  6. tools/* - Available tools                   │
│                                                 │
│  Execution Flow:                                │
│  → Load tools from ./tools directory            │
│  → Initialize AgentController                   │
│  → Execute ReAct loop (max 15 turns)            │
│  → Generate final result                        │
│  → Exit with status code (0=success, 1=fail)    │
└────────┬────────────────────────────────────────┘
         │ API Calls
         ▼
┌─────────────────────────────────────────────────┐
│         Anthropic Claude API                    │
│         (api.anthropic.com)                     │
│                                                 │
│  Model: claude-3-5-sonnet-20241022              │
│  Context Window: 12000 tokens (managed)         │
│  Max Output: 4096 tokens                        │
└─────────────────────────────────────────────────┘
```

## Detailed Flow Steps

### 1. User Initiates Investigation

**Entry Point:** User sends HTTP POST request to backend API

```bash
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"goal": "Calculate what is 2+2", "target_namespace": "default"}'
```

**Request Structure:**
```python
class InvestigationRequest(BaseModel):
    goal: str                      # The investigation goal/query
    target_namespace: str = "default"  # K8s namespace to run job in
```

---

### 2. Backend API Receives Request

**File:** `services/backend-api/app/main.py`

```python
@app.post("/investigate")
async def start_investigation(request: InvestigationRequest):
    job_name, job_id = create_agent_job(
        goal=request.goal,
        namespace=request.target_namespace
    )
    return {
        "message": "Investigation started successfully.",
        "job_name": job_name,
        "job_id": job_id,
        "command_to_check_logs": f"kubectl logs -f job/{job_name} -n {request.target_namespace}"
    }
```

**Response Structure:**
```json
{
  "message": "Investigation started successfully.",
  "job_name": "oats-agent-run-f0f80ba6",
  "job_id": "25d4e322-a55a-40c8-85ca-273e88ccc3f5",
  "command_to_check_logs": "kubectl logs -f job/oats-agent-run-f0f80ba6 -n default"
}
```

---

### 3. Backend Creates Kubernetes Job

**File:** `services/backend-api/app/k8s_service.py`

**Function:** `create_agent_job(goal: str, namespace: str = "default")`

**Job Configuration:**
```python
job_name = f"oats-agent-run-{uuid.uuid4().hex[:8]}"

env_vars = [
    # Primary goal for the agent
    client.V1EnvVar(name="OATS_GOAL", value=goal),

    # API keys from Kubernetes secrets
    client.V1EnvVar(
        name="OPENAI_API_KEY",
        value_from=client.V1EnvVarSource(
            secret_key_ref=client.V1SecretKeySelector(
                name="oats-api-keys",
                key="openai-api-key"
            )
        )
    ),
    client.V1EnvVar(
        name="ANTHROPIC_API_KEY",
        value_from=client.V1EnvVarSource(
            secret_key_ref=client.V1SecretKeySelector(
                name="oats-api-keys",
                key="anthropic-api-key"
            )
        )
    ),
]

container = client.V1Container(
    name="oats-agent",
    image="oats-agent:v4",  # From AGENT_IMAGE env var
    env=env_vars,
)

job_spec = client.V1JobSpec(
    template=pod_template,
    backoff_limit=1,  # Retry once on failure
    ttl_seconds_after_finished=300  # Auto-cleanup after 5 minutes
)
```

**Kubernetes Objects Created:**
- **Job:** `oats-agent-run-XXXXXXXX`
- **Pod:** `oats-agent-run-XXXXXXXX-XXXXX`
- **Status:** Job starts immediately

---

### 4. Agent Container Starts

**Entry Point:** `services/agent/agent/main.py`

**Main Function:** `run_agent()`

```python
def run_agent():
    # 1. Load all tools from tools directory
    global_registry.load_ufs_from_directory('./tools')

    # 2. Get goal from environment variable
    goal = os.environ.get("OATS_GOAL")
    if not goal:
        print("ERROR: OATS_GOAL environment variable not set. Aborting.")
        sys.exit(1)

    # 3. Initialize agent controller
    agent = AgentController(global_registry)

    # 4. Execute goal with ReAct loop
    result = agent.execute_goal(goal, max_turns=15)

    # 5. Print execution summary
    print("\n" + "="*30 + " EXECUTION SUMMARY " + "="*30)
    print(result.execution_summary)
    print("="*80)

    # 6. Exit with appropriate status code
    if not result.success or not result.state.is_complete:
        sys.exit(1)  # Kubernetes marks pod as Failed
    else:
        sys.exit(0)  # Kubernetes marks pod as Completed
```

**Available Tools (loaded from `./tools/`):**
- `bash_executor.py` - Execute bash commands
- `code_search.py` - Search code repositories
- `file_reader.py` - Read file contents
- `kubectl_info.py` - Query Kubernetes resources
- `log_analyzer.py` - Analyze logs
- `metrics_fetcher.py` - Fetch metrics
- `python_executor.py` - Execute Python code
- `sourcegraph_search.py` - Search via Sourcegraph
- `web_search.py` - Search the web
- `yaml_parser.py` - Parse YAML files
- `finish.py` - Mark goal as complete

---

### 5. ReAct Loop Execution

**File:** `services/agent/reactor/agent_controller.py`

**Class:** `AgentController`

**Core Loop:**
```python
def execute_goal(self, goal: str, max_turns: int = 15) -> ReActResult:
    state = ReActState(goal=goal)

    for turn in range(1, max_turns + 1):
        logger.info(f"Starting turn {turn}/{max_turns}")

        # 5.1 Build prompt with context
        prompt = self.prompt_builder.build_react_prompt(
            goal=state.goal,
            available_tools=self.registry.get_all_tools(),
            history=state.transcript
        )

        # 5.2 Call LLM (Claude API)
        llm_response = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096
        )

        # 5.3 Parse LLM response (thought + action)
        parsed = self.parse_llm_response(llm_response)

        # 5.4 Execute tool if action requested
        if parsed.action.tool_name == "finish":
            # Goal complete!
            state.is_complete = True
            state.final_result = parsed.action.parameters.get("result")
            break
        else:
            # Execute the tool
            observation = self.tool_executor.execute(
                tool_name=parsed.action.tool_name,
                parameters=parsed.action.parameters
            )

            # 5.5 Add to transcript for next turn
            state.transcript.append({
                "turn": turn,
                "thought": parsed.thought,
                "action": parsed.action,
                "observation": observation
            })

    return ReActResult(
        success=state.is_complete,
        state=state,
        turns_used=turn
    )
```

**ReAct Turn Structure:**
```
Turn N:
  1. Thought: "I need to calculate 2+2..."
  2. Action: {tool_name: "finish", parameters: {result: "4"}}
  3. Observation: (tool execution result)
  4. Add to history for context in next turn
```

---

### 6. LLM API Interaction

**File:** `services/agent/core/llm.py`

**Anthropic API Call:**
```python
def chat(self, messages: List[Dict], model: str, max_tokens: int = 4096):
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages
    )

    return response.content[0].text
```

**Request to Claude:**
```
Model: claude-3-5-sonnet-20241022
Max Tokens: 4096
Temperature: 0 (deterministic)
System Prompt: ReAct agent instructions
User Prompt: [Goal + Available Tools + History]
```

**Response from Claude:**
```xml
<thought>
I need to calculate 2+2. This is a basic arithmetic operation.
The result is 4.
</thought>
<action>
{
  "tool_name": "finish",
  "parameters": {
    "result": "The calculation 2+2=4 is a fundamental arithmetic operation."
  }
}
</action>
```

---

### 7. Tool Execution

**File:** `services/agent/reactor/tool_executor.py`

**Class:** `ReActToolExecutor`

```python
def execute(self, tool_name: str, parameters: Dict[str, Any]) -> str:
    # 1. Get tool from registry
    tool = self.registry.get_tool(tool_name)

    # 2. Validate parameters
    validated_params = tool.validate_parameters(parameters)

    # 3. Execute tool function
    result = tool.execute(**validated_params)

    # 4. Format observation
    observation = {
        "tool": tool_name,
        "status": "success" if not error else "error",
        "output": result,
        "error": error_msg if error else None
    }

    return json.dumps(observation, indent=2)
```

**Example Tool - Finish:**
```python
# tools/finish.py
class FinishTool(UniversalFunction):
    name = "finish"
    description = "Mark the goal as complete with final result"

    parameters = {
        "result": {
            "type": "string",
            "description": "The final result/answer",
            "required": True
        }
    }

    def execute(self, result: str) -> str:
        # Save result to file
        output_file = f"/app/final_result_{timestamp}.txt"
        with open(output_file, 'w') as f:
            f.write(result)

        return f"Goal completed. Result: {result}"
```

---

### 8. Result Generation and Exit

**Final Steps:**
1. Agent marks goal as complete
2. Saves final result to file: `/app/final_result_*.txt`
3. Prints execution summary to stdout
4. Exits with status code:
   - `0` → Success (Kubernetes Job: Complete)
   - `1` → Failure (Kubernetes Job: Failed)

**Execution Summary (stdout):**
```
============================== EXECUTION SUMMARY ==============================
✅ Goal achieved in 1 turns: The calculation 2+2=4 is a fundamental arithmetic
operation. When we add two units to another two units, we get four units total.
Actions used: finish
================================================================================
✅ Goal execution completed successfully.
```

**Kubernetes Job Status:**
```bash
$ kubectl get job oats-agent-run-f0f80ba6
NAME                      STATUS     COMPLETIONS   DURATION   AGE
oats-agent-run-f0f80ba6   Complete   1/1           14s        27s

$ kubectl get pods -l job-name=oats-agent-run-f0f80ba6
NAME                            READY   STATUS      RESTARTS   AGE
oats-agent-run-f0f80ba6-7mrgw   0/1     Completed   0          27s
```

---

### 9. Log Retrieval (User Access)

**User can access logs via:**

```bash
# Method 1: Direct pod logs
kubectl logs oats-agent-run-f0f80ba6-7mrgw

# Method 2: Job logs (recommended)
kubectl logs job/oats-agent-run-f0f80ba6

# Method 3: Follow logs in real-time
kubectl logs -f job/oats-agent-run-f0f80ba6

# Method 4: Via backend API response
# Use the command_to_check_logs from API response
```

---

## Data Structures

### API Request/Response

```python
# Request
class InvestigationRequest(BaseModel):
    goal: str
    target_namespace: str = "default"

# Response
{
    "message": str,
    "job_name": str,
    "job_id": str,
    "command_to_check_logs": str
}
```

### Agent Internal State

```python
class ReActState:
    goal: str                          # Original goal
    transcript: List[TranscriptEntry]  # History of turns
    is_complete: bool                  # Goal completion status
    final_result: Optional[str]        # Final answer

class TranscriptEntry:
    turn: int
    thought: str
    action: ActionSchema
    observation: str

class ReActResult:
    success: bool
    state: ReActState
    turns_used: int
    execution_summary: str
```

### Tool Schema

```python
class UniversalFunction:
    name: str              # Tool identifier
    description: str       # What the tool does
    parameters: Dict       # Parameter schema (JSON Schema)
    category: str          # Tool category

    def execute(**kwargs) -> str:
        """Execute tool and return observation"""
        pass
```

---

## Environment Variables

### Backend API
```bash
AGENT_IMAGE=oats-agent:v4           # Agent container image
API_KEY_SECRET_NAME=oats-api-keys   # K8s secret name for API keys
```

### Agent Container
```bash
OATS_GOAL="<goal from request>"     # Investigation goal
ANTHROPIC_API_KEY="sk-ant-..."      # Claude API key (from K8s secret)
OPENAI_API_KEY="sk-proj-..."        # OpenAI API key (from K8s secret)
```

---

## Kubernetes Resources

### Secrets
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: oats-api-keys
type: Opaque
data:
  anthropic-api-key: <base64-encoded-key>
  openai-api-key: <base64-encoded-key>
```

### Service Account (for backend API)
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: oats-job-creator

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: job-creator-role
rules:
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["create", "get", "list", "delete"]
- apiGroups: [""]
  resources: ["pods", "pods/log"]
  verbs: ["get", "list"]
```

### Deployment (Backend API)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oats-backend-api
spec:
  replicas: 1
  template:
    spec:
      serviceAccountName: oats-job-creator
      containers:
      - name: backend-api
        image: oats-backend-api:v3
        env:
        - name: AGENT_IMAGE
          value: "oats-agent:v4"
```

---

## Error Handling

### Agent Failures
1. **Missing API Key:** Agent exits with error, Job marked as Failed
2. **Tool Execution Error:** Logged to transcript, agent continues to next turn
3. **Max Turns Reached:** Agent exits incomplete, Job marked as Failed
4. **LLM API Error:** Logged, agent retries next turn

### Kubernetes Retry
- `backoffLimit: 1` → Job will retry once if pod fails
- `ttl_seconds_after_finished: 300` → Auto-cleanup after 5 minutes

---

## Monitoring and Observability

### Log Levels
```python
INFO  - Normal operation (turn starts, API calls, completions)
WARNING - Context limits, retries
ERROR - Failures, exceptions
DEBUG - Detailed tool execution, parsing
```

### Key Metrics to Monitor
- Job completion rate (success vs. failed)
- Average turns per goal
- Tool usage distribution
- LLM API latency
- Token usage per request
- Pod resource usage (CPU, memory)

---

## Future Enhancements (Phase 3 - UI)

### Planned UI Flow
```
User → Web UI → Backend API → K8s Job → Agent → Results
                    ↓                        ↓
                WebSocket ←─────────────────┘
                    ↓
                Real-time
                Log Stream
```

**UI Features:**
- Dashboard showing active/completed jobs
- Real-time log streaming via WebSocket
- Investigation history browser
- Job status visualization
- Result display with syntax highlighting

---

## Complete Example Flow

```bash
# 1. User sends request
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"goal": "What is 2+2?"}'

# Response:
# {
#   "job_name": "oats-agent-run-abc123",
#   ...
# }

# 2. Backend creates K8s Job → Pod starts → Agent runs

# 3. Agent executes ReAct loop:
#    Turn 1:
#      Thought: "Need to calculate 2+2"
#      Action: finish with result "4"
#      Observation: "Goal completed"
#    → Exit success (code 0)

# 4. K8s marks Job as Complete

# 5. User checks logs
kubectl logs job/oats-agent-run-abc123

# Output:
# 🚀 Starting OATS Agent for goal: 'What is 2+2?'
# ...
# ✅ Goal achieved in 1 turns: The answer is 4
# ✅ Goal execution completed successfully.
```

---

## Summary

The OATS system follows this flow:

1. **User** → HTTP request to Backend API
2. **Backend API** → Creates Kubernetes Job with agent image
3. **K8s Job** → Starts pod with agent container
4. **Agent** → Loads tools, executes ReAct loop with LLM
5. **LLM (Claude)** → Generates thoughts and actions
6. **Tools** → Execute actions, return observations
7. **Agent** → Completes goal, saves result, exits
8. **K8s** → Marks job complete/failed based on exit code
9. **User** → Retrieves logs via kubectl or (future) UI

All communication is asynchronous - the backend API returns immediately with job details, and the user monitors the job status and logs independently.
