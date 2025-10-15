# Resume/Continue Feature for OATS Agent

## Overview

The OATS agent now supports resuming executions with two modes:

1. **NEW MODE**: Start completely fresh with a new goal (resets turns, clears all history)
2. **CONTINUE MODE**: Refine/change goal while keeping learnings (preserves facts, ruled-out hypotheses, diagnostic state, but summarizes old turns)

## Use Cases

### When to use NEW mode:
- Starting a completely different investigation
- Want to forget all previous context
- Need fresh turn counter

### When to use CONTINUE mode:
- Refining or adjusting the current investigation goal
- Want to keep learnings but prevent context bloat
- Continue with accumulated knowledge (facts, ruled-out approaches, diagnostic state)

## API Usage

### Endpoint
```
POST /api/v1/executions/{execution_id}/resume
```

### Request Body

#### NEW Mode
```json
{
  "mode": "new",
  "goal": "Your completely new goal",
  "max_turns": 15
}
```

**Response:**
```json
{
  "execution_id": "new-execution-id",
  "previous_execution_id": "old-execution-id",
  "mode": "new",
  "status": "started",
  "goal": "Your completely new goal",
  "max_turns": 15,
  "message": "Started fresh execution with new goal"
}
```

#### CONTINUE Mode
```json
{
  "mode": "continue",
  "goal": "Your refined/adjusted goal",
  "max_turns": 15,
  "keep_last_n_turns": 3
}
```

**Response:**
```json
{
  "execution_id": "same-execution-id",
  "mode": "continue",
  "status": "resumed",
  "old_goal": "Previous goal...",
  "new_goal": "Your refined goal...",
  "max_turns": 15,
  "keep_last_n_turns": 3,
  "previous_turns": 12,
  "message": "Resumed execution with summarized context"
}
```

## How CONTINUE Mode Works

When you resume in CONTINUE mode, the system:

1. **Reconstructs state** from database events
2. **Preserves strategic information**:
   - All verified facts (state.facts)
   - Ruled-out hypotheses (state.ruled_out)
   - Outstanding unknowns (state.unknowns)
   - Complete diagnostic state (causal chain, timeline, competing hypotheses)
3. **Summarizes transcript**:
   - Keeps last N turns (default: 3) for immediate context
   - Condenses older turns into a single summary entry
   - Summary captures:
     - Key learnings/insights
     - Failed approaches
     - Tools used
     - Success/failure counts
4. **Continues execution** with refined goal and preserved learnings

## Strategic Summarization

The summarization is intelligent:

- **Preserves** all structured state (facts, ruled-out, unknowns, diagnosis)
- **Condenses** verbose observations from older turns
- **Highlights** key learnings and failed approaches
- **Maintains** turn count (doesn't reset counter)
- **Keeps** recent context for continuity

## Example Curl Commands

### Start an execution
```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Investigate why the API service is experiencing high latency",
    "max_turns": 15
  }'
```

### Resume with NEW mode (fresh start)
```bash
curl -X POST http://localhost:8000/api/v1/executions/{execution_id}/resume \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "new",
    "goal": "Check database connection pool exhaustion",
    "max_turns": 15
  }'
```

### Resume with CONTINUE mode (keep learnings)
```bash
curl -X POST http://localhost:8000/api/v1/executions/{execution_id}/resume \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "continue",
    "goal": "Investigate high latency and also check for memory leaks in the API service",
    "max_turns": 15,
    "keep_last_n_turns": 3
  }'
```

## Testing

Run the test script:
```bash
python test_resume_feature.py
```

Or manually test each mode using the curl commands above.

## Implementation Details

### Files Modified

1. **services/agent/reactor/models.py**:
   - Added `continue_with_summarized_context()` method
   - Added `_summarize_transcript()` helper
   - Added `_create_summary_entry()` helper

2. **services/backend-api/database/event_store.py**:
   - Added `get_execution_summary()` method
   - Added `update_execution_goal()` method

3. **services/agent/reactor/agent_controller.py**:
   - Updated `execute_goal()` to accept `existing_state` parameter

4. **services/backend-api/app/main.py**:
   - Added `ResumeExecutionRequest` model
   - Added `/api/v1/executions/{id}/resume` endpoint
   - Added `run_agent_resume()` handler
   - Added `reconstruct_state_from_events()` helper

### State Preservation

The `State` object in CONTINUE mode preserves:
- **facts**: List of verified observations from tool outputs
- **ruled_out**: List of invalidated hypotheses
- **unknowns**: List of outstanding questions
- **diagnosis**: Complete diagnostic state including:
  - Symptom description
  - Context (architecture, dependencies, temporal, environment)
  - Timeline of events
  - Causal chain (symptom → proximate cause → root cause)
  - Layer status (INFRASTRUCTURE, RUNTIME, INTEGRATION, BUSINESS_LOGIC)
  - Competing hypotheses with evidence

### Context Summarization

The transcript summarization creates a special entry that captures:
- Turn range summarized (e.g., "Turns 1-12")
- Success/failure counts
- Tools used during that period
- Top 5 key insights
- Top 5 failed approaches
- Note that all structured state is preserved

This prevents context bloat while maintaining investigative continuity.

## Benefits

1. **Flexibility**: Choose between fresh start and continuation
2. **Context Management**: Prevents token bloat in long investigations
3. **Learnings Preserved**: Don't lose valuable facts and insights
4. **Failure Prevention**: Ruled-out approaches prevent repeated failures
5. **Diagnostic Continuity**: Full causal chain and timeline maintained
6. **User Control**: Explicit mode selection with clear semantics
