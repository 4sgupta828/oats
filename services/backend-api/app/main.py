"""FastAPI backend with Server-Sent Events for OATS Agent."""

import asyncio
import sys
import os
import json
import threading
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

# Add the agent's directory to the Python path (image layout: /app/agent)
agent_path = Path(__file__).parent.parent / "agent"
sys.path.insert(0, str(agent_path))

# Import agent components
from reactor.agent_controller import AgentController
from registry.main import global_registry

# Import event-driven components
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.event_store import get_event_store, close_event_store

# --- Setup ---
app = FastAPI(
    title="OATS SRE Co-Pilot API",
    description="Event-driven agent execution with Server-Sent Events",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
event_store = None

# Pydantic models
class StartExecutionRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = 15
    user_id: Optional[str] = "default_user"

class InterruptType(str):
    FEEDBACK = "feedback"  # Inject guidance into transcript, continue
    PAUSE = "pause"        # Save checkpoint, stop execution
    STOP = "stop"          # Abort execution completely

class SubmitFeedbackRequest(BaseModel):
    turn_number: int
    interrupt_type: str  # 'feedback', 'pause', 'stop' (or legacy: 'interrupt', 'input', 'approval')
    message: Optional[str] = None  # User's guidance/feedback message

class ContinueExecutionRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = 15

class ResetExecutionRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = 15


# --- Startup/Shutdown Events ---
@app.on_event("startup")
def startup_event():
    """Initialize services on startup."""
    global event_store

    print("=" * 60)
    print("🚀 Starting OATS Agent API - Event-Driven Architecture")
    print("=" * 60)

    # Check for DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("\n❌ ERROR: DATABASE_URL environment variable not set")
        print("\nPlease set DATABASE_URL:")
        print("  export DATABASE_URL='postgresql://user:password@host:port/database'")
        print("\nOr initialize the database:")
        print("  python database/init_db.py")
        print()
        raise RuntimeError("DATABASE_URL not configured")

    try:
        # Initialize event store
        event_store = get_event_store()
        print("✅ Event store initialized")

        # Initialize agent registry
        tools_path = agent_path / "tools"
        global_registry.load_ufs_from_directory(str(tools_path))
        print(f"✅ Agent registry initialized with {len(global_registry.list_ufs())} tools")

        print("\n" + "=" * 60)
        print("✅ OATS Agent API ready")
        print("   SSE streaming: http://localhost:8000/api/v1/executions")
        print("   Health check: http://localhost:8000/health")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Failed to initialize services: {e}")
        raise


@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on shutdown."""
    print("\n🛑 Shutting down OATS Agent API...")
    if event_store:
        close_event_store()
        print("✅ Event store closed")
    print("✅ Shutdown complete\n")


# --- API Endpoints ---

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "OATS Agent API",
        "version": "2.0.0",
        "architecture": "Event-Driven (SSE + PostgreSQL)",
        "status": "healthy",
        "endpoints": {
            "health": "/health",
            "start_execution": "POST /api/v1/executions",
            "stream_events": "GET /api/v1/executions/{id}/events",
            "execution_status": "GET /api/v1/executions/{id}/status",
            "list_executions": "GET /api/v1/executions",
            "submit_feedback": "POST /api/v1/executions/{id}/feedback",
            "abort_execution": "POST /api/v1/executions/{id}/abort",
            "continue_execution": "POST /api/v1/executions/{id}/continue",
            "reset_execution": "POST /api/v1/executions/{id}/reset",
            "get_artifact": "GET /api/v1/artifacts/{file_path}"
        }
    }


@app.get("/health")
def health_check():
    """Detailed health check."""
    try:
        # Test event store connection
        if event_store:
            event_store.get_execution_status("test")  # Will fail but tests connection
    except Exception:
        pass  # Expected to fail with test ID

    return {
        "status": "healthy",
        "services": {
            "event_store": event_store is not None,
            "agent_registry": len(global_registry.list_ufs()) > 0,
            "tools_loaded": len(global_registry.list_ufs())
        },
        "architecture": "Event-Driven (SSE + PostgreSQL polling)"
    }


@app.post("/api/v1/executions")
def start_execution(request: StartExecutionRequest):
    """Start a new agent execution."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Validate goal
        if not request.goal or not request.goal.strip():
            raise HTTPException(400, "Goal cannot be empty")

        if len(request.goal) > 10000:
            raise HTTPException(400, "Goal too long (max 10000 characters)")

        # Create execution in database
        execution_id = event_store.create_execution(request.goal.strip())

        # Start agent in background thread
        thread = threading.Thread(
            target=run_agent_execution,
            args=(execution_id, request.goal.strip(), request.max_turns),
            daemon=True
        )
        thread.start()

        print(f"🚀 Started execution {execution_id} for goal: {request.goal[:100]}...")

        return {
            "execution_id": execution_id,
            "status": "started",
            "goal": request.goal.strip(),
            "max_turns": request.max_turns,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to start execution: {e}")
        raise HTTPException(500, f"Failed to start execution: {str(e)}")


@app.get("/api/v1/executions/{execution_id}/events")
async def stream_events(execution_id: str, last_event_id: int = 0):
    """
    Stream execution events via Server-Sent Events.
    Uses polling for real-time updates (simple sync implementation).
    """
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    async def event_generator():
        try:
            current_last_id = last_event_id

            while True:
                # Poll for new events
                events = event_store.get_events_since(execution_id, current_last_id)

                for event in events:
                    yield {
                        "id": str(event['id']),
                        "event": event['event_type'],
                        "data": json.dumps({
                            'turn': event['turn_number'],
                            'success': event['success'],
                            'data': event['event_data'],
                            'timestamp': event['created_at'].isoformat()
                        })
                    }
                    current_last_id = event['id']

                # Keep streaming - never auto-close
                # User must explicitly continue or reset
                status = event_store.get_execution_status(execution_id)
                if status and status['status'] == 'cancelled':
                    break  # Only break on cancellation

                # Short delay before next poll
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            print(f"SSE stream cancelled for execution {execution_id}")
        except Exception as e:
            print(f"Error in SSE stream for execution {execution_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


@app.post("/api/v1/executions/{execution_id}/abort")
def abort_execution(execution_id: str):
    """Abort a running execution."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Check if execution exists
        status = event_store.get_execution_status(execution_id)
        if not status:
            raise HTTPException(404, "Execution not found")

        # Only allow aborting running or paused executions
        if status['status'] not in ['running', 'paused']:
            raise HTTPException(400, f"Cannot abort execution with status: {status['status']}")

        # Set status to cancelled
        event_store.update_status(execution_id, 'cancelled')

        # Emit abort event
        event_store.emit_event(
            execution_id, 0, 'execution_aborted',
            {"reason": "User requested abort"},
            success=False
        )

        print(f"🛑 Aborted execution {execution_id}")

        return {
            "status": "aborted",
            "execution_id": execution_id
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to abort execution: {e}")
        raise HTTPException(500, f"Failed to abort execution: {str(e)}")


@app.post("/api/v1/executions/{execution_id}/continue")
def continue_execution(execution_id: str, request: ContinueExecutionRequest):
    """
    Continue execution with refined/additional goal.
    Keeps all state (facts, ruled_out, diagnosis) and transcript (with auto-summarization).
    """
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Validate goal
        if not request.goal or not request.goal.strip():
            raise HTTPException(400, "Goal cannot be empty")

        # Check if execution exists and is paused
        status = event_store.get_execution_status(execution_id)
        if not status:
            raise HTTPException(404, "Execution not found")

        if status['status'] not in ['paused', 'cancelled']:
            raise HTTPException(400, f"Can only continue paused executions. Current status: {status['status']}")

        print(f"▶️  Continuing execution {execution_id}")

        # Update execution goal in database
        event_store.update_execution_goal(execution_id, request.goal.strip())

        # Update status to running
        event_store.update_status(execution_id, 'running')

        # Emit continuation event
        event_store.emit_event(
            execution_id, 0, 'execution_continued',
            {'goal': request.goal.strip()},
            success=True
        )

        # Start agent in background (reconstructs state from DB)
        thread = threading.Thread(
            target=run_agent_continue,
            args=(execution_id, request.goal.strip(), request.max_turns),
            daemon=True
        )
        thread.start()

        print(f"🚀 Continued execution {execution_id}")

        return {
            "execution_id": execution_id,
            "status": "continued",
            "goal": request.goal.strip(),
            "max_turns": request.max_turns
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to continue execution: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to continue execution: {str(e)}")


@app.post("/api/v1/executions/{execution_id}/reset")
def reset_execution(execution_id: str, request: ResetExecutionRequest):
    """
    Reset: Force complete current goal and start fresh with new goal.
    Clears all state and transcript.
    """
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Validate goal
        if not request.goal or not request.goal.strip():
            raise HTTPException(400, "Goal cannot be empty")

        # Check if execution exists
        status = event_store.get_execution_status(execution_id)
        if not status:
            raise HTTPException(404, "Execution not found")

        print(f"🔄 Resetting execution {execution_id} (force complete)")

        # Force complete the current goal
        event_store.update_status(execution_id, 'completed')
        event_store.emit_event(
            execution_id, 0, 'execution_reset',
            {'reason': 'User reset - force completed current goal'},
            success=True
        )

        # Create new execution with new goal
        new_execution_id = event_store.create_execution(request.goal.strip())

        # Emit event linking to previous execution
        event_store.emit_event(
            new_execution_id, 0, 'execution_started',
            {
                'goal': request.goal.strip(),
                'previous_execution_id': execution_id,
                'reset': True
            },
            success=True
        )

        # Start agent in background thread (fresh state)
        thread = threading.Thread(
            target=run_agent_execution,
            args=(new_execution_id, request.goal.strip(), request.max_turns),
            daemon=True
        )
        thread.start()

        print(f"🚀 Started fresh execution {new_execution_id} (reset from {execution_id})")

        return {
            "execution_id": new_execution_id,
            "previous_execution_id": execution_id,
            "status": "started",
            "goal": request.goal.strip(),
            "max_turns": request.max_turns,
            "message": "Reset complete - started fresh execution"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to reset execution: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to reset execution: {str(e)}")


@app.post("/api/v1/executions/{execution_id}/feedback")
def submit_feedback(execution_id: str, feedback: SubmitFeedbackRequest):
    """Submit user interrupt/feedback for an execution."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Validate interrupt type
        valid_types = ['feedback', 'pause', 'stop', 'interrupt', 'input', 'approval', 'user_prompt_response']  # Include user_prompt_response
        if feedback.interrupt_type not in valid_types:
            raise HTTPException(400, f"Invalid interrupt_type. Must be one of: {valid_types}")

        # Map legacy 'interrupt' to 'pause' for backward compatibility
        interrupt_type = feedback.interrupt_type
        if interrupt_type == 'interrupt':
            interrupt_type = 'pause'

        # Prepare feedback data
        feedback_data = {}
        if feedback.message:
            # For user_prompt_response, store the message as 'response'
            if interrupt_type == 'user_prompt_response':
                feedback_data = {"response": feedback.message}
            else:
                feedback_data = {"message": feedback.message}

        # Submit feedback
        event_store.submit_feedback(
            execution_id,
            feedback.turn_number,
            interrupt_type,
            feedback_data
        )

        print(f"📝 Submitted {interrupt_type} interrupt for execution {execution_id}")

        return {
            "status": "submitted",
            "execution_id": execution_id,
            "turn_number": feedback.turn_number,
            "interrupt_type": interrupt_type
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to submit feedback: {e}")
        raise HTTPException(500, f"Failed to submit feedback: {str(e)}")


@app.get("/api/v1/executions/{execution_id}/status")
def get_execution_status(execution_id: str):
    """Get current execution status and metadata."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        status = event_store.get_execution_status(execution_id)
        if not status:
            raise HTTPException(404, "Execution not found")

        return status

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to get execution status: {e}")
        raise HTTPException(500, f"Failed to get execution status: {str(e)}")


@app.get("/api/v1/executions")
def list_executions(limit: int = 50):
    """List recent executions."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        if limit > 100:
            limit = 100  # Cap at 100

        executions = event_store.list_executions(limit)
        return {
            "executions": executions,
            "count": len(executions)
        }

    except Exception as e:
        print(f"Failed to list executions: {e}")
        raise HTTPException(500, f"Failed to list executions: {str(e)}")


@app.get("/api/v1/artifacts/{file_path:path}")
def get_artifact(file_path: str):
    """
    Serve artifact files generated by agent tools.
    Supports various file types with appropriate content types.
    """
    import mimetypes
    from fastapi.responses import FileResponse

    try:
        resolved_path = None

        # Check if this is a temp file (observations_xxx/) or a regular workspace file
        if file_path.startswith('observations_'):
            # This is a temp file from large output
            agent_temp_base = agent_path / ".ufflow_temp"
            requested_file = agent_temp_base / file_path
            resolved_path = requested_file.resolve()

            # Security check: Ensure resolved path is within temp directory
            if not str(resolved_path).startswith(str(agent_temp_base.resolve())):
                raise HTTPException(403, "Access denied: File path outside artifact directory")
        else:
            # This is a regular workspace file (from create_file, write_file, etc.)
            # Resolve relative to agent's parent directory (repo root)
            workspace_root = agent_path.parent.parent
            requested_file = workspace_root / file_path
            resolved_path = requested_file.resolve()

            # Security check: Ensure resolved path is within workspace
            if not str(resolved_path).startswith(str(workspace_root.resolve())):
                raise HTTPException(403, "Access denied: File path outside workspace")

        # Check if file exists
        if not resolved_path.exists():
            raise HTTPException(404, f"Artifact not found: {file_path}")

        if not resolved_path.is_file():
            raise HTTPException(400, "Path is not a file")

        # Detect file type and determine content type
        mime_type, _ = mimetypes.guess_type(str(resolved_path))

        # Default to text/plain if unknown
        if not mime_type:
            mime_type = "text/plain"

        # Return file with appropriate content type
        return FileResponse(
            path=str(resolved_path),
            media_type=mime_type,
            filename=resolved_path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to serve artifact '{file_path}': {e}")
        raise HTTPException(500, f"Failed to serve artifact: {str(e)}")


# --- Background Agent Execution ---

def run_agent_execution(execution_id: str, goal: str, max_turns: int):
    """Run agent execution in background thread with event emission."""
    if not event_store:
        print("Event store not initialized")
        return

    print(f"🤖 Starting agent execution {execution_id}")

    try:
        # Create sync agent controller with event store
        agent = AgentController(global_registry, event_store)

        # Execute goal with event emission
        result = agent.execute_goal(goal, max_turns, execution_id)

        # Agent controller already set status to 'paused' or 'cancelled'
        # Don't override it - agent never truly "completes"
        if result.success:
            print(f"⏸️  Agent execution {execution_id} paused")
        else:
            event_store.update_status(execution_id, 'failed')
            print(f"⚠️  Agent execution {execution_id} failed")

    except Exception as e:
        print(f"❌ Agent execution {execution_id} crashed: {e}")
        import traceback
        event_store.emit_event(
            execution_id, 0, 'execution_failed',
            {"error": str(e), "traceback": traceback.format_exc()},
            success=False
        )
        event_store.update_status(execution_id, 'failed')


def run_agent_continue(execution_id: str, goal: str, max_turns: int):
    """
    Continue agent execution - reconstruct state from DB and keep going.
    Auto-summarization happens transparently during execution.
    """
    if not event_store:
        print("Event store not initialized")
        return

    print(f"▶️  Continuing agent execution {execution_id}")

    try:
        # Reconstruct state from events
        print(f"📥 Reconstructing state from execution {execution_id}")
        state = reconstruct_state_from_events(execution_id)

        if not state:
            raise ValueError(f"Could not reconstruct state from execution {execution_id}")

        print(f"✅ State reconstructed: {state.turn_count} turns, {len(state.transcript)} entries, "
              f"{len(state.state.facts) if state.state else 0} facts")

        # Update goal (refined/additional context)
        state.goal = goal
        if state.state:
            state.state.goal = goal

        # Continue execution with existing state
        agent = AgentController(global_registry, event_store)
        agent.execute_goal(goal, max_turns, execution_id, existing_state=state)

        # Always pauses - never truly "completes"
        print(f"⏸️  Agent execution {execution_id} paused")

    except Exception as e:
        print(f"❌ Agent execution {execution_id} crashed during continue: {e}")
        import traceback
        traceback.print_exc()
        event_store.emit_event(
            execution_id, 0, 'execution_failed',
            {"error": str(e), "traceback": traceback.format_exc()},
            success=False
        )
        event_store.update_status(execution_id, 'failed')


def reconstruct_state_from_events(execution_id: str):
    """
    Reconstruct ReActState from stored events.
    This is a simplified reconstruction that extracts key state from the last LLM response.
    """
    try:
        from reactor.models import ReActState, State, TranscriptEntry
        from reactor.models import ReflectSection, StrategizeSection, ActSection, Hypothesis

        # Get execution info
        summary = event_store.get_execution_summary(execution_id)
        if not summary:
            return None

        goal = summary['goal']
        max_turn = summary['event_stats'].get('max_turn', 0)

        # Get all events for this execution
        events = event_store.get_events_since(execution_id, 0)

        # Create initial state
        state = ReActState(goal=goal, max_turns=15)
        state.turn_count = max_turn

        # Reconstruct transcript from events
        turn_data = {}  # turn_number -> {llm_response, tool_result}

        for event in events:
            turn = event['turn_number']
            event_type = event['event_type']
            data = event['event_data']

            if turn not in turn_data:
                turn_data[turn] = {}

            if event_type == 'llm_response_success':
                turn_data[turn]['llm_response'] = data
            elif event_type in ['tool_success', 'tool_failed']:
                turn_data[turn]['tool_result'] = data

        # Build transcript entries from turn data
        for turn_num in sorted(turn_data.keys()):
            if turn_num == 0:
                continue  # Skip turn 0 (metadata events)

            turn = turn_data[turn_num]
            llm_resp = turn.get('llm_response', {})
            tool_result = turn.get('tool_result', {})

            # Reconstruct transcript entry from event data
            if llm_resp and 'reflect' in llm_resp:
                try:
                    # Safely get strategize data
                    strategize_data = llm_resp.get('strategize', {})
                    hypothesis_data = strategize_data.get('hypothesis', {})

                    # Safely get action data
                    action_data = llm_resp.get('action', {})

                    # Create entry only if we have minimal required data
                    if not strategize_data or not action_data:
                        print(f"⚠️  Incomplete data for turn {turn_num}, skipping")
                        continue

                    entry = TranscriptEntry(
                        turn=turn_num,
                        reflect=ReflectSection(**llm_resp['reflect']),
                        strategize=StrategizeSection(
                            reasoning=strategize_data.get('reasoning', ''),
                            hypothesis=Hypothesis(**hypothesis_data) if hypothesis_data else Hypothesis(claim='N/A', test='N/A', signal='N/A'),
                            ifInvalidated=strategize_data.get('ifInvalidated', 'N/A')
                        ),
                        state=State(**llm_resp.get('state', {'goal': goal})) if 'state' in llm_resp else State(goal=goal),
                        act=ActSection(**action_data) if action_data else ActSection(tool='unknown', params={}),
                        observation=tool_result.get('observation', 'N/A'),
                        duration_ms=0
                    )
                    state.transcript.append(entry)

                    # Update state from the entry (preserve latest state)
                    if entry.state:
                        state.state = entry.state

                except Exception as e:
                    print(f"⚠️  Could not reconstruct turn {turn_num}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

        print(f"📊 Reconstructed state: {len(state.transcript)} transcript entries, "
              f"{len(state.state.facts) if state.state else 0} facts")

        return state

    except Exception as e:
        print(f"❌ Failed to reconstruct state: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
