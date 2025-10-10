import asyncio
import socketio
import sys
import os
from pathlib import Path
from fastapi import FastAPI

# Add agent directory to Python path
agent_path = Path(__file__).parent.parent.parent / "agent"
sys.path.insert(0, str(agent_path))

from reactor.agent_controller import AgentController
from reactor.models import ReActState, TranscriptEntry
from registry.main import global_registry

# --- Setup ---
app = FastAPI(title="OATS SRE Co-Pilot API")
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio)
app.mount("/", socket_app)

# Global agent controller instance (shared across sessions)
agent_controller = None

# In-memory storage for active sessions
active_sessions = {}

# --- Startup Event ---

@app.on_event("startup")
async def startup_event():
    """
    Initialize the agent controller when the backend starts.
    """
    global agent_controller
    print("Initializing agent controller...")

    # Load all available tools from the 'tools' directory
    tools_path = Path(__file__).parent.parent.parent / "agent" / "tools"
    global_registry.load_ufs_from_directory(str(tools_path))

    # Create the agent controller
    agent_controller = AgentController(global_registry)
    print(f"Agent controller initialized with {len(global_registry.list_ufs())} tools")

# --- WebSocket Event Handlers ---

@sio.event
async def connect(sid, environ):
    """
    Triggered when a new UI client connects.
    Creates a new session with the embedded agent.
    """
    print(f"Client connected: {sid}")

    try:
        # Initialize a new session with a fresh state
        active_sessions[sid] = {
            "state": None,  # Will be initialized when investigation starts
            "agent_task": None
        }

        await sio.emit('agent_message', {'type': 'status', 'payload': 'Agent is ready. Please provide your goal.'}, to=sid)

    except Exception as e:
        print(f"Error during connect for {sid}: {e}")
        await sio.emit('agent_message', {'type': 'error', 'payload': f"Failed to initialize session: {e}"}, to=sid)
        await sio.disconnect(sid)


@sio.on('start_investigation')
async def handle_start_investigation(sid, data):
    """
    Receives a goal from the UI and starts the agent investigation.
    """
    goal = data.get('goal')
    print(f"Received goal from {sid}: {goal}")

    if sid in active_sessions and goal:
        try:
            # Initialize agent state for this session
            state = ReActState(goal=goal)
            active_sessions[sid]["state"] = state

            # Start the agent investigation in the background
            agent_task = asyncio.create_task(run_agent_investigation(sid, state))
            active_sessions[sid]["agent_task"] = agent_task

            await sio.emit('agent_message', {'type': 'status', 'payload': f"Investigation started for goal: {goal}"}, to=sid)
        except Exception as e:
            print(f"Error starting investigation for {sid}: {e}")
            await sio.emit('agent_message', {'type': 'error', 'payload': f"Failed to start investigation: {e}"}, to=sid)

@sio.event
async def disconnect(sid):
    """
    Triggered when a UI client disconnects.
    Cleans up session resources.
    """
    print(f"Client disconnected: {sid}")
    if sid in active_sessions:
        session_info = active_sessions.pop(sid)
        # Cancel any running agent task
        if session_info.get("agent_task"):
            session_info["agent_task"].cancel()
        print(f"Cleaned up session for {sid}")

# --- Background Task ---

async def run_agent_investigation(sid, state):
    """
    Runs the agent investigation loop for a specific session.
    """
    global agent_controller
    print(f"Starting agent investigation for session {sid}")

    try:
        available_tools = agent_controller.registry.list_ufs()

        # Main ReAct Loop
        while not state.is_complete and state.turn_count < state.max_turns:
            try:
                # 1. REASON: Get the next step from the LLM
                parsed_response = agent_controller._parse_llm_response(
                    agent_controller.llm_client.create_completion_text(
                        messages=agent_controller.prompt_builder.build_messages_for_openai(state, available_tools)
                    )
                )

                # Send thought process back to the UI
                await sio.emit('agent_message', {'type': 'thought', 'payload': parsed_response.strategize.reasoning}, to=sid)

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

                    await sio.emit('agent_message', {'type': 'finish', 'payload': completion_payload}, to=sid)
                    break

                # 2. ACT: Execute the tool
                action_payload = parsed_response.act.dict()
                await sio.emit('agent_message', {'type': 'action', 'payload': action_payload}, to=sid)
                observation = agent_controller.tool_executor.execute_action(action_payload)

                # Send observation back to the UI
                await sio.emit('agent_message', {'type': 'observation', 'payload': observation}, to=sid)

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