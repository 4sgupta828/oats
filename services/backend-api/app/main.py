import asyncio
import socketio
import sys
import os
import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

# Add the agent's directory to the Python path to import its modules
agent_path = Path(__file__).parent.parent / "agent"
sys.path.insert(0, str(agent_path))

# Import the agent's core components
from reactor.agent_controller import AgentController
from reactor.async_agent_controller import AsyncAgentController
from reactor.event_emitter import EventStoreEmitter
from reactor.models import ReActState, TranscriptEntry
from registry.main import global_registry

# Import event-driven components (optional - only if DATABASE_URL is set)
event_store = None
try:
    if os.getenv("DATABASE_URL"):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from database.event_store import get_event_store, close_event_store
        from database.events import EventType, ExecutionStatus
except ImportError as e:
    print(f"Note: Event store not available (database dependencies not installed): {e}")

# --- Setup ---
app = FastAPI(title="OATS SRE Co-Pilot API")

# Add CORS middleware for SSE support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    ping_interval=25,
    ping_timeout=60,
    max_http_buffer_size=10 * 1024 * 1024  # 10MB for large messages
)
# Wrap Socket.IO and FastAPI together - Socket.IO handles /socket.io/*, FastAPI handles rest
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

agent_controller = None
active_sessions = {}

# Pydantic models for SSE endpoints
class StartExecutionRequest(BaseModel):
    goal: str
    max_turns: Optional[int] = 15
    user_id: Optional[str] = "default_user"

# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Initializes the agent controller when the backend starts."""
    global agent_controller, event_store
    print("Initializing agent controller...")
    tools_path = agent_path / "tools"
    global_registry.load_ufs_from_directory(str(tools_path))
    agent_controller = AgentController(global_registry)
    print(f"Agent controller initialized with {len(global_registry.list_ufs())} tools")

    # Initialize event store if DATABASE_URL is set
    if os.getenv("DATABASE_URL"):
        try:
            event_store = await get_event_store()
            print("✅ Event store initialized - SSE endpoints enabled")
        except Exception as e:
            print(f"⚠️  Event store initialization failed: {e}")
            print("   WebSocket endpoints will still work, but SSE will be unavailable")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if event_store:
        await close_event_store()
        print("Event store closed")

# --- WebSocket Event Handlers ---
@sio.event
async def connect(sid, environ):
    """Handles new UI client connections."""
    print(f"Client connected: {sid}")
    try:
        active_sessions[sid] = {"state": None, "agent_task": None}
        await sio.emit('agent_message', {'type': 'status', 'payload': 'Agent is ready. Please provide your goal.'}, to=sid)
    except Exception as e:
        print(f"Error during connect for {sid}: {e}")
        await sio.emit('agent_message', {'type': 'error', 'payload': f"Failed to initialize session: {e}"}, to=sid)
        await sio.disconnect(sid)

@sio.on('start_investigation')
async def handle_start_investigation(sid, data):
    """Receives a goal from the UI and starts the agent investigation."""
    goal = data.get('goal')
    print(f"Received goal from {sid}: {goal}")

    if sid in active_sessions and goal:
        try:
            state = ReActState(goal=goal)
            active_sessions[sid]["state"] = state
            agent_task = asyncio.create_task(run_agent_investigation(sid, state))
            active_sessions[sid]["agent_task"] = agent_task
            await sio.emit('agent_message', {'type': 'status', 'payload': f"Investigation started for goal: {goal}"}, to=sid)
        except Exception as e:
            print(f"Error starting investigation for {sid}: {e}")
            await sio.emit('agent_message', {'type': 'error', 'payload': f"Failed to start investigation: {e}"}, to=sid)

@sio.event
async def disconnect(sid):
    """Cleans up when a UI client disconnects."""
    print(f"Client disconnected: {sid}")
    if sid in active_sessions:
        session_info = active_sessions.pop(sid)
        if session_info.get("agent_task"):
            session_info["agent_task"].cancel()
        print(f"Cleaned up session for {sid}")

# --- SSE Endpoints (Event-Driven Architecture) ---

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "websocket": "enabled",
        "sse": "enabled" if event_store else "disabled",
        "tools_loaded": len(global_registry.list_ufs()) if agent_controller else 0
    }

@app.post("/api/v1/executions")
async def start_execution(request: StartExecutionRequest, background_tasks: BackgroundTasks):
    """Start a new agent execution with SSE streaming."""
    if not event_store:
        raise HTTPException(503, "SSE endpoints require DATABASE_URL to be configured")

    if not agent_controller:
        raise HTTPException(500, "Agent controller not initialized")

    try:
        # Create execution in database
        execution_id = await event_store.create_execution(
            goal=request.goal,
            user_id=request.user_id,
            max_turns=request.max_turns,
        )

        # Start agent in background
        background_tasks.add_task(
            run_async_agent_execution, execution_id, request.goal, request.max_turns
        )

        print(f"🚀 Started execution {execution_id} for goal: {request.goal[:100]}...")

        return {
            "execution_id": execution_id,
            "status": "started",
            "goal": request.goal,
            "max_turns": request.max_turns,
        }

    except Exception as e:
        print(f"Failed to start execution: {e}")
        raise HTTPException(500, f"Failed to start execution: {str(e)}")


@app.get("/api/v1/executions/{execution_id}/events")
async def stream_events(execution_id: str, last_event_id: int = 0):
    """Stream execution events via Server-Sent Events using PostgreSQL LISTEN/NOTIFY."""
    if not event_store:
        raise HTTPException(503, "SSE endpoints require DATABASE_URL to be configured")

    async def event_generator():
        try:
            async for event in event_store.listen_for_events(execution_id, last_event_id):
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

        except asyncio.CancelledError:
            print(f"SSE stream cancelled for execution {execution_id}")
        except Exception as e:
            print(f"Error in SSE stream for execution {execution_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


@app.get("/api/v1/executions/{execution_id}/status")
async def get_execution_status(execution_id: str):
    """Get current execution status."""
    if not event_store:
        raise HTTPException(503, "SSE endpoints require DATABASE_URL to be configured")

    status = await event_store.get_execution_status(execution_id)
    if not status:
        raise HTTPException(404, "Execution not found")

    return status


@app.get("/api/v1/executions")
async def list_executions(user_id: Optional[str] = None, limit: int = 50):
    """List recent executions."""
    if not event_store:
        raise HTTPException(503, "SSE endpoints require DATABASE_URL to be configured")

    executions = await event_store.list_executions(user_id, limit)
    return {"executions": executions, "count": len(executions)}


# --- Background Agent Tasks ---

async def run_async_agent_execution(execution_id: str, goal: str, max_turns: int):
    """Run agent execution in background with event emission (for SSE)."""
    if not agent_controller or not event_store:
        print("Agent controller or event store not initialized")
        return

    print(f"🤖 Starting async agent execution {execution_id}")

    try:
        # Create async agent controller with event emitter
        emitter = EventStoreEmitter(event_store)
        async_agent = AsyncAgentController(global_registry, emitter)

        # Execute goal with event emission
        result = await async_agent.execute_goal_async(goal, max_turns, execution_id)

        if result.success:
            await event_store.update_execution_status(execution_id, "completed")
            print(f"✅ Agent execution {execution_id} completed successfully")
        else:
            await event_store.update_execution_status(execution_id, "failed")
            print(f"⚠️  Agent execution {execution_id} failed")

    except Exception as e:
        print(f"❌ Agent execution {execution_id} crashed: {e}")
        await event_store.update_execution_status(execution_id, "failed")


async def run_agent_investigation(sid, state):
    """Runs the agent's ReAct loop for a specific session (for WebSocket)."""
    global agent_controller
    print(f"Starting agent investigation for session {sid}")
    try:
        available_tools = agent_controller.registry.list_ufs()

        # Main ReAct Loop
        while not state.is_complete and state.turn_count < state.max_turns:
            # Check if session still exists (client disconnected)
            if sid not in active_sessions:
                print(f"Session {sid} no longer exists, stopping investigation")
                break

            try:
                # 1. REASON: Get the next step from the LLM
                parsed_response = agent_controller._parse_llm_response(
                    agent_controller.llm_client.create_completion_text(
                        messages=agent_controller.prompt_builder.build_messages_for_openai(state, available_tools)
                    )
                )

                # Send thought process back to the UI
                try:
                    await sio.emit('agent_message', {'type': 'thought', 'payload': parsed_response.strategize.reasoning}, to=sid)
                except Exception as emit_error:
                    print(f"Failed to send thought to {sid}: {emit_error}")

                # Check for finish action
                if parsed_response.is_finish:
                    state.is_complete = True
                    state.completion_reason = parsed_response.act.params.get("reason", "Goal completed")

                    # Save final results to file
                    final_results_file = agent_controller._save_final_results(state, state.completion_reason)

                    # Generate execution summary
                    execution_summary = agent_controller._generate_execution_summary(state)

                    # Send comprehensive completion message
                    completion_payload = {
                        'completion_reason': state.completion_reason,
                        'execution_summary': execution_summary,
                        'final_results_file': final_results_file,
                        'turns_completed': state.turn_count,
                        'goal': state.goal
                    }

                    try:
                        await sio.emit('agent_message', {'type': 'finish', 'payload': completion_payload}, to=sid)
                    except Exception as emit_error:
                        print(f"Failed to send finish message to {sid}: {emit_error}")
                    break

                # 2. ACT: Execute the tool
                action_payload = parsed_response.act.dict()
                try:
                    await sio.emit('agent_message', {'type': 'action', 'payload': action_payload}, to=sid)
                except Exception as emit_error:
                    print(f"Failed to send action to {sid}: {emit_error}")

                observation = agent_controller.tool_executor.execute_action(action_payload)

                # Send observation back to the UI
                try:
                    await sio.emit('agent_message', {'type': 'observation', 'payload': observation}, to=sid)
                except Exception as emit_error:
                    print(f"Failed to send observation to {sid}: {emit_error}")

                # 3. OBSERVE & UPDATE: Update the agent's state
                entry = TranscriptEntry(
                    turn=state.turn_count + 1,
                    reflect=parsed_response.reflect,
                    strategize=parsed_response.strategize,
                    state=parsed_response.state,
                    act=parsed_response.act,
                    observation=observation
                )
                state.transcript.append(entry)
                state.turn_count += 1

            except Exception as e:
                error_message = f"Error in ReAct loop: {str(e)}"
                print(error_message)
                await sio.emit('agent_message', {'type': 'error', 'payload': error_message}, to=sid)
                # Allow the agent to try to recover in the next loop
                state.transcript.append(TranscriptEntry(
                    turn=state.turn_count + 1,
                    observation=f"ERROR: {error_message}",
                    reflect={"turn": state.turn_count + 1, "outcome": "FAILURE", "hypothesisResult": "N/A", "insight": "Loop error"},
                    strategize={"reasoning": "Recovering from error", "hypothesis": {"claim": "", "test": "", "signal": ""}, "ifInvalidated": ""},
                    state={"goal": state.goal},
                    act={"tool": "error", "params": {}}
                ))
                state.turn_count += 1

    except asyncio.CancelledError:
        print(f"Agent investigation cancelled for session {sid}")
    except Exception as e:
        print(f"Error in agent investigation for {sid}: {e}")
        if sid in active_sessions:
            await sio.emit('agent_message', {'type': 'error', 'payload': f'Agent error: {e}'}, to=sid)
