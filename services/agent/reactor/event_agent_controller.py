"""Event-emitting Agent Controller for OATS Event-Driven Architecture."""

import asyncio
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any

from .agent_controller import AgentController
from .models import ReActState, TranscriptEntry
from core.config import get_config
from core.logging_config import get_logger

logger = get_logger('event_agent_controller')

class EventAgentController(AgentController):
    """Agent Controller that emits events to the event store."""
    
    def __init__(self, registry, event_store=None):
        super().__init__(registry)
        self.event_store = event_store
        self.execution_id = None
    
    def _emit_event(self, turn_number: int, event_type: str, event_data: Dict[str, Any], success: bool = None):
        """Helper to emit events (no-op if no event store)."""
        if self.event_store and self.execution_id:
            try:
                # Run async operation in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self.event_store.emit_event(
                            self.execution_id, turn_number, event_type, event_data, success
                        )
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Failed to emit event {event_type}: {e}")
    
    def _check_for_feedback(self, turn_number: int) -> Optional[Dict]:
        """Check for pending user feedback."""
        if not self.event_store or not self.execution_id:
            return None
        
        try:
            # Run async operation in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                feedback = loop.run_until_complete(
                    self.event_store.check_feedback(self.execution_id, turn_number)
                )
                return feedback
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to check feedback: {e}")
            return None
    
    def _update_execution_status(self, status: str):
        """Update execution status."""
        if not self.event_store or not self.execution_id:
            return
        
        try:
            # Run async operation in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.event_store.update_execution_status(self.execution_id, status)
                )
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to update execution status: {e}")
    
    def execute_goal(self, goal: str, max_turns: Optional[int] = None, 
                     execution_id: str = None) -> 'ReActResult':
        """Execute goal with event emission."""
        
        # Store execution ID for event emission
        self.execution_id = execution_id
        
        # Initialize state
        state = ReActState(goal=goal, max_turns=max_turns or get_config().get_max_turns())
        
        # Emit execution started event
        self._emit_event(0, "execution_started", {
            "goal": goal,
            "max_turns": state.max_turns
        }, success=True)
        
        try:
            available_tools = self.registry.list_ufs()
            
            while state.turn_count < state.max_turns and not state.is_complete:
                turn_number = state.turn_count + 1
                turn_start_time = time.time()
                
                # ═══════════════════════════════════════════════════════
                # (a) TURN START - LLM INVOCATION
                # ═══════════════════════════════════════════════════════
                self._emit_event(turn_number, "turn_started", {
                    "turn_number": turn_number,
                    "goal": goal,
                    "max_turns": state.max_turns
                })
                
                # Check for user feedback
                feedback = self._check_for_feedback(turn_number)
                if feedback:
                    # (d) USER INTERVENTION
                    self._emit_event(turn_number, "user_feedback_received", {
                        "feedback_type": feedback['feedback_type'],
                        "feedback_data": feedback['feedback_data']
                    })
                    
                    if feedback['feedback_type'] == 'interrupt':
                        self._emit_event(turn_number, "user_interrupt", {
                            "reason": "User requested interruption",
                            "feedback_data": feedback['feedback_data']
                        })
                        self._update_execution_status('paused')
                        break
                    
                    # Handle other feedback types (input, approval)
                    self._handle_feedback(state, feedback)
                
                # Build prompt
                messages = self.prompt_builder.build_messages_for_openai(state, available_tools)
                json_schema = self._get_response_json_schema()
                
                # Call LLM
                self._emit_event(turn_number, "llm_called", {
                    "messages_count": len(messages),
                    "model": "claude-3-5-sonnet"
                })
                
                try:
                    raw_response = self.llm_client.create_completion_text(
                        messages=messages,
                        json_schema=json_schema
                    )
                    
                    # ═══════════════════════════════════════════════════════
                    # (b) LLM RESPONSE PARSING
                    # ═══════════════════════════════════════════════════════
                    parsed_response = self._parse_llm_response(raw_response)
                    state.state = parsed_response.state
                    
                    self._emit_event(turn_number, "llm_response_success", {
                        "turn_number": turn_number,
                        "raw_response_length": len(raw_response),
                        "parsed_successfully": True,
                        "reflect": parsed_response.reflect.model_dump() if parsed_response.reflect else None,
                        "strategize": parsed_response.strategize.model_dump() if parsed_response.strategize else None,
                        "action": {
                            "tool": parsed_response.act.tool,
                            "params": parsed_response.act.params
                        }
                    }, success=True)
                    
                    # ═══════════════════════════════════════════════════════
                    # (e) LLM ESCALATION - Check if LLM needs user input
                    # ═══════════════════════════════════════════════════════
                    if self._llm_requests_input(parsed_response):
                        self._emit_event(turn_number, "llm_requests_input", {
                            "request_message": self._extract_input_request(parsed_response),
                            "escalation_type": "input"
                        })
                        self._update_execution_status('paused')
                        break
                    
                    if self._llm_requests_approval(parsed_response):
                        self._emit_event(turn_number, "llm_requests_approval", {
                            "request_message": self._extract_approval_request(parsed_response),
                            "action_description": parsed_response.act.tool,
                            "escalation_type": "approval",
                            "risk_level": parsed_response.act.safe
                        })
                        self._update_execution_status('paused')
                        break
                    
                except Exception as e:
                    self._emit_event(turn_number, "llm_response_failed", {
                        "turn_number": turn_number,
                        "raw_response_length": len(raw_response) if 'raw_response' in locals() else 0,
                        "parsed_successfully": False,
                        "error_message": str(e)
                    }, success=False)
                    raise
                
                # Check for finish
                if parsed_response.is_finish:
                    completion_reason = parsed_response.act.params.get("reason", "Goal completed")
                    state.is_complete = True
                    state.completion_reason = completion_reason
                    
                    self._emit_event(turn_number, "execution_completed", {
                        "completion_reason": completion_reason,
                        "turns_completed": state.turn_count,
                        "execution_time_ms": int((time.time() - turn_start_time) * 1000)
                    }, success=True)
                    break
                
                # ═══════════════════════════════════════════════════════
                # (c) TOOL EXECUTION
                # ═══════════════════════════════════════════════════════
                tool_start_time = time.time()
                
                self._emit_event(turn_number, "tool_started", {
                    "tool_name": parsed_response.act.tool,
                    "tool_version": "1.0.0",  # Could be extracted from registry
                    "parameters": parsed_response.act.params
                })
                
                try:
                    observation = self.tool_executor.execute_action(
                        parsed_response.act.model_dump()
                    )
                    
                    tool_execution_time = int((time.time() - tool_start_time) * 1000)
                    
                    # Determine success from observation
                    tool_success = not observation.startswith("ERROR")
                    
                    self._emit_event(turn_number, "tool_success" if tool_success else "tool_failed", {
                        "tool_name": parsed_response.act.tool,
                        "tool_version": "1.0.0",
                        "parameters": parsed_response.act.params,
                        "execution_time_ms": tool_execution_time,
                        "observation_length": len(observation),
                        "error_message": observation if not tool_success else None
                    }, success=tool_success)
                    
                except Exception as e:
                    tool_execution_time = int((time.time() - tool_start_time) * 1000)
                    observation = f"ERROR: Tool execution failed - {str(e)}"
                    
                    self._emit_event(turn_number, "tool_failed", {
                        "tool_name": parsed_response.act.tool,
                        "tool_version": "1.0.0",
                        "parameters": parsed_response.act.params,
                        "execution_time_ms": tool_execution_time,
                        "error_message": str(e)
                    }, success=False)
                
                # Update transcript
                transcript_entry = TranscriptEntry(
                    turn=turn_number,
                    reflect=parsed_response.reflect,
                    strategize=parsed_response.strategize,
                    state=parsed_response.state,
                    act=parsed_response.act,
                    observation=observation
                )
                state.transcript.append(transcript_entry)
                state.turn_count += 1
            
            # Finalize
            state.end_time = datetime.now()
            success = state.is_complete
            
            if not success:
                self._emit_event(state.turn_count, "execution_failed", {
                    "reason": "Max turns reached" if state.turn_count >= state.max_turns else "Interrupted",
                    "turns_completed": state.turn_count
                }, success=False)
            
            self._update_execution_status('completed' if success else 'failed')
            
            return self._create_result(state, success)
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            
            self._emit_event(state.turn_count, "execution_failed", {
                "error": str(e),
                "traceback": traceback.format_exc()
            }, success=False)
            
            self._update_execution_status('failed')
            raise
    
    def _llm_requests_input(self, parsed_response) -> bool:
        """Check if LLM is requesting user input."""
        # Example: LLM uses special tool 'request_user_input'
        return parsed_response.act.tool == 'request_user_input'
    
    def _llm_requests_approval(self, parsed_response) -> bool:
        """Check if LLM is requesting approval for risky action."""
        # Example: Check if 'safe' field indicates approval needed
        return (parsed_response.act.safe is not None and 
                'approval' in parsed_response.act.safe.lower())
    
    def _extract_input_request(self, parsed_response) -> str:
        """Extract what input LLM is requesting."""
        return parsed_response.act.params.get('request', 'Input needed')
    
    def _extract_approval_request(self, parsed_response) -> str:
        """Extract what approval LLM is requesting."""
        return parsed_response.act.params.get('approval_request', 'Approval needed for risky action')
    
    def _handle_feedback(self, state: ReActState, feedback: Dict):
        """Incorporate user feedback into state."""
        feedback_type = feedback['feedback_type']
        feedback_data = feedback['feedback_data']
        
        if feedback_type == 'input':
            # Add user input as special observation
            user_input = feedback_data.get('input', '')
            # Will be picked up in next turn's prompt
            state.pending_user_input = user_input
        
        elif feedback_type == 'approval':
            # User approved risky action
            state.user_approved_action = feedback_data.get('action', '')
    
    def _create_result(self, state: ReActState, success: bool):
        """Create ReActResult with execution summary."""
        from .models import ReActResult
        
        execution_summary = self._generate_execution_summary(state)
        
        return ReActResult(
            success=success,
            state=state,
            execution_summary=execution_summary
        )
