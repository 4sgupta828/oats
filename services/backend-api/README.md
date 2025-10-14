# OATS Backend API - Agent Interruption & Feedback

## Overview

This document describes the agent interruption and feedback features implemented in the OATS backend API.

## Features

### 1. Abort Execution

**Purpose**: Immediately stop a running agent execution.

**Endpoint**: `POST /api/v1/executions/{execution_id}/abort`

**Behavior**:
- Sets the execution status to `cancelled` in the database
- Agent checks for abort flag at the start of each turn
- Agent stops gracefully after completing its current turn
- Emits `execution_aborted` event to SSE stream

**Use Case**: When the user wants to completely stop the agent and cancel the goal.

**Example**:
```bash
curl -X POST http://localhost:8000/api/v1/executions/{execution_id}/abort
```

### 2. Submit Feedback

**Purpose**: Provide guidance or input to the agent during execution.

**Endpoint**: `POST /api/v1/executions/{execution_id}/feedback`

**Request Body**:
```json
{
  "turn_number": 5,
  "feedback_type": "interrupt",
  "data": {
    "guidance": "Focus on checking the database connections first"
  }
}
```

**Feedback Types**:
- `interrupt`: Pause execution and incorporate user guidance
- `input`: Provide specific input requested by the agent
- `approval`: Approve a risky action the agent requested permission for

**Behavior**:
- Feedback is stored in the `user_feedback` table
- Agent checks for pending feedback at the start of each turn
- Agent completes its current turn before processing feedback
- For `interrupt` type, execution status is set to `paused`

**Use Case**: When the user wants to guide the agent without stopping it completely.

## Architecture

### Database Tables

#### agent_executions
- `id`: Unique execution identifier
- `goal`: The user's goal/task
- `status`: Current status (running, paused, completed, failed, cancelled)
- `created_at`, `updated_at`, `completed_at`: Timestamps

#### agent_events
- Stores all events emitted during execution for SSE streaming
- Includes turn-by-turn progress, tool execution, LLM responses

#### user_feedback
- `execution_id`: Links to agent_executions
- `turn_number`: Which turn the feedback applies to
- `feedback_type`: Type of feedback (interrupt, input, approval)
- `feedback_data`: JSON data with feedback content
- `processed`: Boolean flag to track if feedback has been handled

### Event Flow

#### Abort Flow
```
User clicks "Abort"
  → UI calls /abort endpoint
  → Backend sets status to 'cancelled'
  → Agent checks abort flag at next turn start
  → Agent stops and emits 'execution_aborted' event
  → UI receives event and updates display
```

#### Feedback Flow
```
User clicks "Provide Feedback"
  → UI prompts for input
  → UI calls /feedback endpoint
  → Backend stores feedback in database
  → Agent checks for feedback at next turn start
  → Agent processes feedback and updates state
  → Agent continues with new guidance
```

## Agent Controller Changes

The `AgentController` class in `reactor/agent_controller.py` has been updated to:

1. **Check abort flag** at the start of each turn:
   ```python
   if self.event_store and self.event_store.check_abort_flag(execution_id):
       logger.info(f"Execution {execution_id} aborted by user")
       self._emit(execution_id, turn_number, 'execution_aborted', ...)
       break
   ```

2. **Check for feedback** at the start of each turn:
   ```python
   feedback = self.event_store.check_feedback(execution_id, turn_number)
   if feedback:
       if feedback['feedback_type'] == 'interrupt':
           self.event_store.update_status(execution_id, 'paused')
           break
   ```

3. **Complete current turn** before stopping - ensures agent doesn't leave work incomplete

## UI Changes

### New Buttons
- **Abort Button** (🛑 Abort): Red button that immediately stops the agent
- **Feedback Button** (💬 Provide Feedback): Purple button that allows user to provide guidance

### Button Behavior
- Only shown when execution is in progress (`isExecuting === true`)
- Abort button calls the abort endpoint and closes SSE connection
- Feedback button prompts for user input and submits via feedback endpoint

## Testing

### Test Abort Functionality
1. Start an analysis with a long-running goal
2. Click "🛑 Abort" button during execution
3. Verify agent stops after completing current turn
4. Verify execution status shows as "Aborted"

### Test Feedback Functionality
1. Start an analysis
2. Click "💬 Provide Feedback" button
3. Enter guidance in the modal (e.g., "Focus on logs first")
4. Click "Submit Guidance"
5. Verify agent pauses after completing current turn
6. Verify execution status shows as "Paused" (not "Failed")
7. Check database to see feedback was stored
8. (Future enhancement: Resume with feedback)

## Bug Fixes

### Issue: Agent marked as "failed" after receiving feedback
**Problem**: When user submitted feedback via the "Provide Feedback" button, the agent would pause correctly but then be marked as "failed" instead of "paused".

**Root Cause**: In `agent_controller.py`, the finalization logic (lines 345-361) would check if the execution was successful (`state.is_complete`). When feedback interrupted the agent, `is_complete` was False, causing the code to emit an `execution_failed` event and set status to `'failed'`, which overwrote the `'paused'` status that had been set earlier.

**Fix**: Added a check in the finalization logic to preserve `'paused'` and `'cancelled'` statuses:
```python
# Check current status to avoid overwriting 'paused' or 'cancelled'
current_status = self.event_store.get_execution_status(execution_id)
if current_status and current_status['status'] in ['paused', 'cancelled']:
    # Don't emit failed event or update status - already handled
    logger.info(f"Execution {execution_id} ended with status: {current_status['status']}")
else:
    # Normal completion/failure handling...
```

### Issue: Poor UX for feedback input
**Problem**: Using browser `prompt()` for feedback input was clunky and didn't provide good UX.

**Fix**: Created a proper `FeedbackModal` component with:
- Clean modal UI with backdrop
- Multi-line textarea for detailed feedback
- Example guidance in placeholder text
- Submit/Cancel buttons with proper states
- Keyboard accessibility (Enter doesn't submit, allows newlines)

## Future Enhancements

1. **Resume after feedback**: Allow agent to resume execution after processing user feedback
2. **Better feedback UI**: Replace prompt() with a proper modal/form
3. **Feedback history**: Show all feedback submitted during an execution
4. **Turn-specific feedback**: Allow feedback to be tied to specific agent actions
5. **Approval workflow**: Full implementation of approval requests for risky actions

## API Reference

### Abort Execution
```
POST /api/v1/executions/{execution_id}/abort

Response:
{
  "status": "aborted",
  "execution_id": "uuid"
}
```

### Submit Feedback
```
POST /api/v1/executions/{execution_id}/feedback

Request:
{
  "turn_number": int,
  "feedback_type": "interrupt" | "input" | "approval",
  "data": object
}

Response:
{
  "status": "submitted",
  "execution_id": "uuid",
  "turn_number": int,
  "feedback_type": string
}
```

### Stream Events (SSE)
```
GET /api/v1/executions/{execution_id}/events?last_event_id=0

Streams events including:
- execution_started
- turn_started
- llm_response_success
- tool_started, tool_success, tool_failed
- execution_completed, execution_failed, execution_aborted
- user_feedback_received, user_interrupt
```
