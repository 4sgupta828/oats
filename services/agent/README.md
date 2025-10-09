# OATS Agent Service

Containerized OATS SRE Agent for Kubernetes execution.

## Structure

```
services/agent/
├── agent/
│   ├── __init__.py
│   └── main.py              # Container entrypoint
├── core/                    # Core logic (config, models, SDK)
├── reactor/                 # ReAct agent controller
├── tools/                   # SRE diagnostic tools
├── executor/                # Tool execution engine
├── orchestrator/            # Orchestration logic
├── registry/                # Tool registry
├── memory/                  # Long-term memory storage
├── docs/                    # Documentation and prompts
├── tests/                   # Test files
├── scripts/                 # Helper scripts
├── requirements.txt         # Python dependencies
└── Dockerfile              # Container image
```

## Usage

### Local Execution

```bash
cd services/agent

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OATS_GOAL="Why is the API returning 504 errors?"
export OATS_MAX_TURNS=15
export OPENAI_API_KEY="your-key"

# Run the agent
python -m agent.main
```

### Docker Build

```bash
cd services/agent
docker build -t oats-agent:latest .
```

### Docker Run

```bash
docker run \
  -e OATS_GOAL="Diagnose API 504 errors" \
  -e OATS_MAX_TURNS=15 \
  -e OPENAI_API_KEY="your-key" \
  -v $(pwd)/output:/output \
  oats-agent:latest
```

### Kubernetes Job

The agent runs as a Kubernetes Job, created by the backend API:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: oats-agent-abc123
spec:
  template:
    spec:
      containers:
      - name: oats-agent
        image: oats-agent:latest
        env:
        - name: OATS_GOAL
          value: "Why is the API returning 504 errors?"
        - name: OATS_MAX_TURNS
          value: "15"
        envFrom:
        - secretRef:
            name: oats-api-secrets
      restartPolicy: Never
```

## Environment Variables

### Required
- `OATS_GOAL` - The infrastructure problem to diagnose
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM API key

### Optional
- `OATS_MAX_TURNS` - Maximum investigation turns (default: 15)
- `UFFLOW_LLM_PROVIDER` - LLM provider: "openai" or "claude" (default: "openai")
- `UFFLOW_LLM_MODEL` - Model name (default: provider-specific)
- `UFFLOW_TEMPERATURE` - LLM temperature (default: 0.1)
- `UFFLOW_MAX_TOKENS` - Max tokens per turn (default: 4000)
- `UFFLOW_PROMPT_VERSION` - Prompt version: "v1", "v2", "v3" (default: "v3")
- `UFFLOW_LOG_LEVEL` - Log level (default: "INFO")

## Output

Results are written to `/output/result.json`:

```json
{
  "goal": "Why is the API returning 504 errors?",
  "status": "completed",
  "summary": "Root cause identified: Database connection pool exhausted...",
  "turns": 8
}
```

## Development

### Running Tests

```bash
cd services/agent
pytest tests/
```

### Adding New Tools

Create tools in `tools/` directory using the `@uf` decorator:

```python
from core.sdk import uf, UfInput
from pydantic import Field

class MyToolInput(UfInput):
    param: str = Field(..., description="Parameter description")

@uf(name="my_tool", version="1.0.0", description="Tool description")
def my_tool(inputs: MyToolInput) -> dict:
    # Implementation
    return {"result": "success"}
```

### Modifying Prompts

Prompts are in `reactor/prompts/`:
- `v3.txt` - Universal RCA Framework (default)
- `v2.txt` - Alternative SRE prompt
- `v1.txt` - General-purpose agent

Change prompt: `export UFFLOW_PROMPT_VERSION=v3`

## Architecture

The agent follows a ReAct (Reflect-Strategize-Act) pattern:

1. **Registry**: Discovers and loads all available tools
2. **Agent Controller**: Manages the investigation loop
3. **Prompt Builder**: Constructs prompts with state and tools
4. **LLM Client**: Calls OpenAI/Anthropic API
5. **Tool Executor**: Executes tools and returns results
6. **State Manager**: Tracks facts, hypotheses, and causal chains

## Troubleshooting

### Agent fails to start
```bash
# Check logs
docker logs <container-id>

# Common issues:
# - Missing OATS_GOAL environment variable
# - Invalid API key
# - Import errors (check Python path)
```

### Tool execution errors
```bash
# Check tool registry
python -c "from registry.main import Registry; r = Registry(); r.discover_and_load_ufs(); print(r.list_tools())"
```

### Import errors
```bash
# Verify structure
ls -la agent/ core/ reactor/ tools/

# Check Python path in main.py
python -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('agent').parent)); from reactor.agent_controller import AgentController"
```

## Migration Notes

This service contains the original OATS agent code moved from the repository root. The structure preserves all existing functionality while adding a containerized entrypoint for Kubernetes execution.

### Changes from Original
1. Added `agent/main.py` as container entrypoint
2. Moved all agent code to `services/agent/`
3. No changes to core agent logic
4. Added Docker support

See [README-CLOUD.md](../../README-CLOUD.md) for full migration guide.
