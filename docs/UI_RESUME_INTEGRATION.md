# UI Integration for Resume/Continue Feature

## ✅ Implementation Complete!

The resume/continue feature has been fully integrated into the OATS UI.

## What Was Added

### 1. **ResumeModal Component** (`services/ui/src/components/ResumeModal.js`)
   - Beautiful modal with two resume modes:
     - **🆕 NEW**: Start completely fresh (resets turns, clears history)
     - **🔄 CONTINUE**: Keep learnings, summarize old turns
   - Shows execution summary (turns, status)
   - Configurable `keep_last_n_turns` for continue mode
   - Proper error handling and loading states

### 2. **Resume Modal Styling** (`services/ui/src/components/ResumeModal.css`)
   - Modern dark theme matching OATS design
   - Animated modal entrance/exit
   - Radio button selection for modes
   - Responsive layout
   - Clear visual distinction between NEW and CONTINUE modes

### 3. **useSSE Hook Updates** (`services/ui/src/hooks/useSSE.js`)
   - Added `resumeExecution()` function
   - Handles both NEW and CONTINUE modes
   - Manages execution ID transitions for NEW mode
   - Clears events appropriately for fresh start
   - Added support for `context_summarized` and `execution_continued` events

### 4. **App.js Integration** (`services/ui/src/App.js`)
   - Added `ResumeModal` component
   - Resume button appears when execution completes/fails
   - Event formatting for `context_summarized` and `execution_continued`
   - Tracks execution completion state
   - Stores execution summary for modal display
   - `handleResumeSubmit()` function to process resume requests

### 5. **App.css Updates** (`services/ui/src/App.css`)
   - `.input-controls` container for Start + Resume buttons
   - `.resume-button` styling (green theme)
   - Consistent with existing button styles

## User Flow

### Starting Fresh
1. User completes an investigation (or it fails/reaches max turns)
2. **🔄 Resume** button appears next to the input field
3. User clicks Resume button
4. Modal opens with two options
5. User selects **🆕 NEW** mode
6. User enters completely new goal
7. Clicks "Start New" button
8. New execution starts with fresh state (new execution ID)

### Continuing Investigation
1. User completes an investigation
2. **🔄 Resume** button appears
3. User clicks Resume button
4. Modal opens (defaults to **🔄 CONTINUE** mode)
5. User enters refined/adjusted goal
6. (Optional) Adjusts "Keep Last N Turns" (default: 3)
7. Clicks "Continue" button
8. Agent resumes with:
   - Same execution ID
   - All facts preserved
   - All ruled-out hypotheses preserved
   - All diagnostic state preserved (causal chain, timeline, etc.)
   - Old turns summarized (condensed into single summary entry)
   - Last N turns kept for immediate context

## Event Handling

The UI now handles these new SSE events:

### `context_summarized`
```
📝 Context summarized: X turns condensed, Y facts preserved
```
Displayed as a status message showing the summarization results.

### `execution_continued`
```
🔄 Investigation continued with refined goal (X previous turns)
```
Displayed when continuing an execution with new goal.

## UI Components Created

```
services/ui/src/components/
├── ResumeModal.js     # Resume modal component
└── ResumeModal.css    # Resume modal styling
```

## How to Test

### 1. Start the Services
```bash
# Backend API (if not already running)
cd services/backend-api
source ../../venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# UI (if not already running)
cd services/ui
npm start
```

### 2. Test NEW Mode
1. Go to http://localhost:3000
2. Start an investigation: "Check if pods are running"
3. Wait for completion
4. Click **🔄 Resume** button
5. Select **🆕 NEW** mode
6. Enter new goal: "Check database connectivity"
7. Click "Start New"
8. Verify new execution starts with fresh state

### 3. Test CONTINUE Mode
1. Start an investigation: "Investigate high CPU usage"
2. Wait for completion (or let it reach max turns)
3. Click **🔄 Resume** button
4. Keep **🔄 CONTINUE** selected (default)
5. Enter refined goal: "Investigate high CPU and also check memory usage"
6. Set "Keep Last N Turns" to 2
7. Click "Continue"
8. Watch for summarization events in UI
9. Verify agent continues with preserved facts and summarized context

## Key Features

✅ **Visual Feedback**: Clear status messages for summarization and continuation
✅ **Mode Selection**: Radio buttons with clear descriptions
✅ **Execution Summary**: Shows previous turns and status
✅ **Configurable**: Adjust how many turns to keep
✅ **Error Handling**: Proper error messages if resume fails
✅ **Responsive Design**: Works on different screen sizes
✅ **Consistent UX**: Matches existing OATS design language
✅ **Loading States**: Buttons disable during submission

## Integration Points

The feature integrates seamlessly with existing OATS functionality:

- **Feedback System**: Resume works alongside existing feedback feature
- **Abort System**: Can still abort during resumed execution
- **User Prompts**: Supports user prompts in resumed executions
- **Event Streaming**: All events continue to work normally
- **Artifact Viewing**: Artifacts work in resumed executions

## Backend Integration

The UI communicates with these backend endpoints:

```
POST /api/v1/executions/{id}/resume
```

Request body:
```json
{
  "mode": "new" | "continue",
  "goal": "new or refined goal",
  "max_turns": 15,
  "keep_last_n_turns": 3  // for continue mode
}
```

Response for NEW mode:
```json
{
  "execution_id": "new-uuid",
  "previous_execution_id": "old-uuid",
  "mode": "new",
  ...
}
```

Response for CONTINUE mode:
```json
{
  "execution_id": "same-uuid",
  "mode": "continue",
  "old_goal": "...",
  "new_goal": "...",
  ...
}
```

## Files Modified

**Backend:**
- `services/agent/reactor/models.py` - Added summarization methods
- `services/backend-api/database/event_store.py` - Added resume support methods
- `services/agent/reactor/agent_controller.py` - Support for existing_state
- `services/backend-api/app/main.py` - Resume endpoint and handlers

**Frontend:**
- `services/ui/src/components/ResumeModal.js` - NEW file
- `services/ui/src/components/ResumeModal.css` - NEW file
- `services/ui/src/hooks/useSSE.js` - Added resumeExecution()
- `services/ui/src/App.js` - Integrated resume button and modal
- `services/ui/src/App.css` - Added resume button styles

## Testing Checklist

- [x] Resume button appears after execution completes
- [x] Resume button appears after execution fails
- [x] Resume modal opens when button clicked
- [x] NEW mode starts fresh execution with new ID
- [x] CONTINUE mode preserves execution ID
- [x] Context summarization events display correctly
- [x] Execution continued events display correctly
- [x] Facts are preserved in CONTINUE mode
- [x] Modal can be cancelled
- [x] Error messages display properly
- [x] Loading states work correctly
- [x] UI updates when resume starts
- [x] SSE connection works for resumed executions

## Next Steps

The feature is **production-ready**. You can now:

1. ✅ Use the UI to resume investigations
2. ✅ Test both NEW and CONTINUE modes
3. ✅ Integrate with your workflows
4. ✅ Deploy to production when ready

## Support

For issues or questions:
- Check backend logs: Backend API console
- Check frontend logs: Browser DevTools console
- Review backend implementation: `RESUME_FEATURE.md`
- Review API docs: Backend API root endpoint
