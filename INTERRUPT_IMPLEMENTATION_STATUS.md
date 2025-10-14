# Interrupt Handling Implementation Status

## Overview
Implementing enhanced interrupt handling with 3 types:
1. **FEEDBACK** - Inject user guidance into transcript, agent continues
2. **PAUSE** - Save checkpoint, agent stops, can resume later
3. **STOP** - Abort execution completely (existing abort functionality)

---

## ✅ Completed

### 1. Database Schema
- Created migration: `services/backend-api/database/migrations/001_add_interrupt_types.sql`
- Added `execution_checkpoints` table for pause/resume
- Updated `user_feedback` constraint to allow new interrupt types
- Added `stopped` status to `agent_executions`
- Created migration script: `services/backend-api/database/apply_migration.py`

**To apply migration:**
```bash
cd services/backend-api
python database/apply_migration.py
```

### 2. Backend API Models
- Updated `SubmitFeedbackRequest` model in `main.py`
- Changed `feedback_type` → `interrupt_type`
- Changed `data` → `message` (simplified)
- Added `InterruptType` class with constants

### 3. Backend API Endpoints
- Updated `/api/v1/executions/{id}/feedback` endpoint
  - Now accepts `interrupt_type` instead of `feedback_type`
  - Maps legacy `'interrupt'` → `'pause'` for backward compatibility
  - Validates new interrupt types

### 4. Bug Fixes
- Fixed agent being marked as "failed" after receiving feedback
  - Agent now preserves `'paused'` and `'cancelled'` statuses
- Replaced `prompt()` with proper `FeedbackModal` component
- Added proper event handlers for user interrupts

---

## 🚧 In Progress / TODO

### 5. Event Store Methods
**File:** `services/backend-api/database/event_store.py`

Need to add:
```python
def save_checkpoint(self, execution_id: str, turn_number: int,
                   state_data: dict, resume_token: str):
    """Save execution checkpoint for pause/resume."""
    # Insert into execution_checkpoints table

def load_checkpoint(self, execution_id: str, resume_token: str) -> Optional[Dict]:
    """Load checkpoint for resume."""
    # Query execution_checkpoints by resume_token

def delete_checkpoints(self, execution_id: str):
    """Delete all checkpoints for an execution."""
    # Cleanup after completion
```

### 6. Agent Controller Updates
**File:** `services/agent/reactor/agent_controller.py`

Need to update interrupt handling (lines 138-153):
```python
# Current code breaks loop for ALL interrupt types
# New code should:
# - FEEDBACK: inject into transcript, continue (NO break)
# - PAUSE: save checkpoint, break
# - STOP: break immediately

if interrupt:
    interrupt_type = interrupt.get('feedback_type', 'feedback')

    if interrupt_type == 'feedback':
        # Inject into transcript as observation
        self._inject_user_feedback(state, interrupt, turn_number)
        # NO BREAK - continue execution

    elif interrupt_type == 'pause':
        # Save checkpoint
        resume_token = self._save_checkpoint(execution_id, state)
        self._emit(execution_id, turn_number, 'execution_paused',
                  {'resume_token': resume_token})
        self.event_store.update_status(execution_id, 'paused')
        break

    elif interrupt_type == 'stop':
        # Abort (same as current abort)
        self._emit(execution_id, turn_number, 'execution_stopped', {})
        self.event_store.update_status(execution_id, 'stopped')
        break
```

Add helper methods:
```python
def _inject_user_feedback(self, state: ReActState, interrupt: dict, turn_number: int):
    """Inject feedback as transcript entry so LLM sees it in next turn."""
    # Create TranscriptEntry with user's message
    # Append to state.transcript
    # Agent will see this in context on next turn

def _save_checkpoint(self, execution_id: str, state: ReActState) -> str:
    """Save execution checkpoint."""
    # Generate resume_token
    # Serialize state and transcript
    # Call event_store.save_checkpoint()
    # Return resume_token

def resume_from_checkpoint(self, execution_id: str, checkpoint: dict) -> ReActResult:
    """Resume execution from checkpoint."""
    # Reconstruct ReActState from checkpoint
    # Continue execution loop from saved turn
```

### 7. Resume Endpoint
**File:** `services/backend-api/app/main.py`

Need to add:
```python
class ResumeExecutionRequest(BaseModel):
    resume_token: str

@app.post("/api/v1/executions/{execution_id}/resume")
def resume_execution(execution_id: str, request: ResumeExecutionRequest):
    """Resume a paused execution from checkpoint."""
    # Load checkpoint using resume_token
    # Start agent in background with restored state
    # Return success response with execution_id
```

### 8. UI Updates
**Files:** `services/ui/src/App.js`, `services/ui/src/components/FeedbackModal.js`, `services/ui/src/hooks/useSSE.js`

Need to:
1. Update `FeedbackModal` to show interrupt type selector:
   - **💬 Provide Guidance (Continue)** → `feedback`
   - **⏸️ Pause Execution** → `pause`

2. Update `submitFeedback` call to use `interrupt_type` instead of `feedback_type`

3. Add "Resume" button when execution status is `'paused'`
   - Store `resume_token` when pause event is received
   - Call `/resume` endpoint with token

4. Update event formatting to handle new event types:
   - `execution_paused`
   - `execution_stopped`
   - `feedback_injected`

### 9. Testing
Need to test:
- **FEEDBACK flow**: Submit guidance → agent continues → LLM sees feedback in next turn
- **PAUSE flow**: Pause → checkpoint saved → status = paused → resume → agent continues
- **STOP flow**: Stop → execution ends → status = stopped → no resume possible
- **Backward compatibility**: Old `'interrupt'` type still works (maps to `'pause'`)

---

## Simplified 3-Type Design

| Type | Behavior | Status After | Can Resume? | LLM Sees It? |
|------|----------|-------------|-------------|--------------|
| **FEEDBACK** | Continue immediately | `running` | N/A | ✅ Yes (in transcript) |
| **PAUSE** | Save & stop | `paused` | ✅ Yes | ❌ No (stopped before next turn) |
| **STOP** | Abort completely | `stopped` | ❌ No | ❌ No |

## Key Differences from Current Implementation

**Current (buggy):**
- Only `'interrupt'` type
- Always pauses and breaks loop
- Marked as `'failed'` (BUG - now fixed)
- No resume capability
- Feedback not visible to LLM

**New (enhanced):**
- 3 distinct interrupt types
- **FEEDBACK** doesn't break loop - agent continues with guidance
- **PAUSE** properly saves state for resume
- **STOP** is explicit abort
- Feedback injected into transcript for LLM visibility
- Resume functionality with checkpoints

---

## Next Steps

**Option A: Complete Implementation (2-3 hours)**
1. Add event store checkpoint methods
2. Update agent controller interrupt handling
3. Add helper methods (_inject_user_feedback, _save_checkpoint, resume_from_checkpoint)
4. Add resume endpoint
5. Update UI for interrupt type selection and resume button
6. Test all flows

**Option B: Test Current State First**
1. Apply database migration
2. Test existing abort and feedback with bug fixes
3. Verify backward compatibility
4. Then continue with new features

**Recommendation:** Option B - Test what we have, then implement remaining features incrementally.
