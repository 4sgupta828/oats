"""FastAPI backend with Server-Sent Events for OATS Agent."""

import asyncio
import sys
import os
import json
import threading
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

# Add the agent's directory to the Python path
agent_path = Path(__file__).parent.parent.parent / "agent"
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

class SubmitFeedbackRequest(BaseModel):
    turn_number: int
    feedback_type: str  # 'interrupt', 'input', 'approval'
    data: dict


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
            "submit_feedback": "POST /api/v1/executions/{id}/feedback"
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
def start_execution(request: StartExecutionRequest, background_tasks: BackgroundTasks):
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

                # Check if execution is complete
                status = event_store.get_execution_status(execution_id)
                if status and status['status'] in ['completed', 'failed', 'cancelled']:
                    break

                # Short delay before next poll
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            print(f"SSE stream cancelled for execution {execution_id}")
        except Exception as e:
            print(f"Error in SSE stream for execution {execution_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


@app.post("/api/v1/executions/{execution_id}/feedback")
def submit_feedback(execution_id: str, feedback: SubmitFeedbackRequest):
    """Submit user feedback for an execution."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")

    try:
        # Validate feedback type
        valid_types = ['interrupt', 'input', 'approval']
        if feedback.feedback_type not in valid_types:
            raise HTTPException(400, f"Invalid feedback_type. Must be one of: {valid_types}")

        # Submit feedback
        event_store.submit_feedback(
            execution_id,
            feedback.turn_number,
            feedback.feedback_type,
            feedback.data
        )

        print(f"📝 Submitted {feedback.feedback_type} feedback for execution {execution_id}")

        return {
            "status": "submitted",
            "execution_id": execution_id,
            "turn_number": feedback.turn_number,
            "feedback_type": feedback.feedback_type
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

        if result.success:
            event_store.update_status(execution_id, 'completed')
            print(f"✅ Agent execution {execution_id} completed successfully")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
