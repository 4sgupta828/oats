"""FastAPI backend with Server-Sent Events for OATS Agent Event-Driven Architecture."""

import asyncio
import json
import os
import sys
import traceback
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

# Add the agent's directory to the Python path
agent_path = Path(__file__).parent.parent / "agent"
sys.path.insert(0, str(agent_path))

# Import agent components
from reactor.agent_controller import AgentController
from reactor.models import ReActState
from registry.main import global_registry

# Import event-driven architecture components
from database.event_store import AsyncEventStore, get_event_store, close_event_store
from events import EventType, ExecutionStatus

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === FastAPI App Setup ===
app = FastAPI(
    title="OATS Agent API - Event-Driven",
    description="OATS SRE Co-Pilot API with event-driven architecture",
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

# === Global State ===
agent_controller: Optional[AgentController] = None
event_store: Optional[AsyncEventStore] = None

# === Pydantic Models ===
class StartExecutionRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = 15
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class SubmitFeedbackRequest(BaseModel):
    turn_number: int
    feedback_type: str  # 'interrupt', 'input', 'approval'
    data: Dict[str, Any]

# === Startup/Shutdown Events ===
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global agent_controller, event_store
    
    logger.info("🚀 Starting OATS Agent API - Event-Driven")
    
    try:
        # Initialize event store
        event_store = await get_event_store()
        logger.info("✅ Event store initialized")
        
        # Initialize agent controller
        tools_path = agent_path / "tools"
        global_registry.load_ufs_from_directory(str(tools_path))
        
        # Create agent controller without event store for now (will be passed per execution)
        agent_controller = AgentController(global_registry)
        
        logger.info(f"✅ Agent controller initialized with {len(global_registry.list_ufs())} tools")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down OATS Agent API")
    await close_event_store()
    logger.info("✅ Shutdown complete")

# === API Endpoints ===

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "OATS Agent API - Event-Driven",
        "version": "2.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Detailed health check."""
    try:
        # Test event store connection
        if event_store:
            await event_store.get_execution_status("test")  # This will fail but test connection
    except Exception:
        pass  # Expected to fail with test ID
    
    return {
        "status": "healthy",
        "services": {
            "event_store": event_store is not None,
            "agent_controller": agent_controller is not None,
            "tools_loaded": len(global_registry.list_ufs()) if agent_controller else 0
        },
        "timestamp": datetime.now().isoformat()
    }

@app.post("/executions")
async def start_execution(request: StartExecutionRequest, background_tasks: BackgroundTasks):
    """Start a new agent execution."""
    if not agent_controller or not event_store:
        raise HTTPException(500, "Services not initialized")
    
    try:
        # Create execution in database
        execution_id = await event_store.create_execution(
            goal=request.goal,
            user_id=request.user_id,
            max_turns=request.max_turns,
            metadata=request.metadata
        )
        
        # Emit execution started event
        await event_store.emit_event(
            execution_id, 0, EventType.EXECUTION_STARTED,
            {
                "goal": request.goal,
                "max_turns": request.max_turns,
                "user_id": request.user_id,
                "metadata": request.metadata
            },
            success=True
        )
        
        # Start agent in background
        background_tasks.add_task(
            run_agent_execution, 
            execution_id, 
            request.goal, 
            request.max_turns
        )
        
        logger.info(f"🚀 Started execution {execution_id} for goal: {request.goal[:100]}...")
        
        return {
            "execution_id": execution_id,
            "status": "started",
            "goal": request.goal,
            "max_turns": request.max_turns,
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start execution: {e}")
        raise HTTPException(500, f"Failed to start execution: {str(e)}")

@app.get("/executions/{execution_id}/events")
async def stream_events(execution_id: str, last_event_id: int = 0):
    """Stream execution events via Server-Sent Events."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")
    
    async def event_generator():
        last_id = last_event_id
        consecutive_empty_polls = 0
        max_empty_polls = 100  # 30 seconds of empty polls (100 * 300ms)
        
        try:
            while consecutive_empty_polls < max_empty_polls:
                # Get new events
                events = await event_store.get_events_since(execution_id, last_id)
                
                if events:
                    consecutive_empty_polls = 0
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
                        last_id = event['id']
                else:
                    consecutive_empty_polls += 1
                
                # Check if execution is complete
                if events and any(e['event_type'] in [
                    EventType.EXECUTION_COMPLETED, 
                    EventType.EXECUTION_FAILED
                ] for e in events):
                    logger.info(f"Execution {execution_id} completed, closing SSE stream")
                    break
                
                await asyncio.sleep(0.3)  # Poll every 300ms
                
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error in SSE stream for execution {execution_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
    
    return EventSourceResponse(event_generator())

@app.post("/executions/{execution_id}/feedback")
async def submit_feedback(execution_id: str, feedback: SubmitFeedbackRequest):
    """Submit user feedback for an execution."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")
    
    try:
        # Validate feedback type
        valid_types = ['interrupt', 'input', 'approval']
        if feedback.feedback_type not in valid_types:
            raise HTTPException(400, f"Invalid feedback_type. Must be one of: {valid_types}")
        
        # Submit feedback
        await event_store.submit_feedback(
            execution_id,
            feedback.turn_number,
            feedback.feedback_type,
            feedback.data
        )
        
        logger.info(f"📝 Submitted {feedback.feedback_type} feedback for execution {execution_id}")
        
        return {
            "status": "submitted",
            "execution_id": execution_id,
            "turn_number": feedback.turn_number,
            "feedback_type": feedback.feedback_type
        }
        
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(500, f"Failed to submit feedback: {str(e)}")

@app.get("/executions/{execution_id}/status")
async def get_execution_status(execution_id: str):
    """Get current execution status and metadata."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")
    
    try:
        status = await event_store.get_execution_status(execution_id)
        if not status:
            raise HTTPException(404, "Execution not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution status: {e}")
        raise HTTPException(500, f"Failed to get execution status: {str(e)}")

@app.get("/executions")
async def list_executions(user_id: Optional[str] = None, limit: int = 50):
    """List recent executions."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")
    
    try:
        executions = await event_store.list_executions(user_id, limit)
        return {
            "executions": executions,
            "count": len(executions),
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Failed to list executions: {e}")
        raise HTTPException(500, f"Failed to list executions: {str(e)}")

@app.get("/executions/{execution_id}/summary")
async def get_execution_summary(execution_id: str):
    """Get detailed execution summary for debugging/analytics."""
    if not event_store:
        raise HTTPException(500, "Event store not initialized")
    
    try:
        summary = await event_store.get_execution_summary(execution_id)
        if not summary:
            raise HTTPException(404, "Execution not found")
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution summary: {e}")
        raise HTTPException(500, f"Failed to get execution summary: {str(e)}")

# === Background Agent Execution ===

async def run_agent_execution(execution_id: str, goal: str, max_turns: int):
    """Run agent execution in background with event emission."""
    if not agent_controller or not event_store:
        logger.error("Agent controller or event store not initialized")
        return
    
    logger.info(f"🤖 Starting agent execution {execution_id}")
    start_time = datetime.now()
    
    try:
        # Create agent controller with event store
        from reactor.event_agent_controller import EventAgentController
        event_agent = EventAgentController(global_registry, event_store)
        
        # Execute goal with event emission
        result = await asyncio.to_thread(
            event_agent.execute_goal, goal, max_turns, execution_id
        )
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if result.success:
            logger.info(f"✅ Agent execution {execution_id} completed successfully in {execution_time:.0f}ms")
        else:
            logger.warning(f"⚠️ Agent execution {execution_id} failed after {execution_time:.0f}ms")
        
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(f"❌ Agent execution {execution_id} crashed after {execution_time:.0f}ms: {e}")
        
        # Emit failure event
        await event_store.emit_event(
            execution_id, 0, EventType.EXECUTION_FAILED,
            {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "execution_time_ms": execution_time
            },
            success=False
        )
        await event_store.update_execution_status(execution_id, ExecutionStatus.FAILED)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
