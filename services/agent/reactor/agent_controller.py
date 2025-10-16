# reactor/agent_controller.py

import sys
import os
import json
import time
import re
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import get_logger, UFFlowLogger
from core.config import config
from registry.main import Registry
from core.llm import OpenAIClientManager
from reactor.models import ReActState, ReActResult, ParsedLLMResponse
from reactor.prompt_builder import ReActPromptBuilder
from reactor.tool_executor import ReActToolExecutor

# Initialize logging
logger = get_logger('reactor.agent_controller')

# Pydantic schemas for robust parsing
class ActionSchema(BaseModel):
    """Schema for action part of LLM response."""
    tool_name: str = Field(..., description="Name of the tool to execute")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Parameters for the tool")
    reason: Optional[str] = Field(None, description="Reason for finish action")

    @field_validator('tool_name')
    @classmethod
    def validate_tool_name(cls, v):
        if not v or not v.strip():
            raise ValueError("tool_name cannot be empty")
        return v.strip()

class LLMResponseSchema(BaseModel):
    """Schema for complete LLM response."""
    thought: str = Field(..., description="The reasoning thought")
    action: ActionSchema = Field(..., description="The action to take")

    @field_validator('thought')
    @classmethod
    def validate_thought(cls, v):
        if not v or not v.strip():
            raise ValueError("thought cannot be empty")
        return v.strip()

class AgentController:
    """
    The main ReAct agent controller that manages the reasoning-action-observation loop.
    """

    _environment_setup_done = False

    def __init__(self, registry: Registry, event_store=None):
        self.registry = registry
        self.event_store = event_store
        self.llm_client = OpenAIClientManager()
        self.tool_executor = ReActToolExecutor(registry, event_store)
        self.prompt_builder = ReActPromptBuilder()

        # Setup Python environment at startup (only once)
        if not AgentController._environment_setup_done:
            self._setup_python_environment()
            AgentController._environment_setup_done = True

    def execute_goal(self, goal: str, max_turns: Optional[int] = None, execution_id: str = None,
                     existing_state: Optional[ReActState] = None) -> ReActResult:
        """
        Execute a goal using the ReAct framework.

        Args:
            goal: High-level user objective
            max_turns: Maximum number of turns to prevent infinite loops
            execution_id: Optional execution ID for event tracking
            existing_state: Optional existing ReActState to resume from (for continue mode)

        Returns:
            ReActResult with success status and final state
        """
        start_time = time.time()

        # Create execution if event store available
        if self.event_store and not execution_id:
            execution_id = self.event_store.create_execution(goal)
            self._emit(execution_id, 0, 'execution_started',
                      {'goal': goal, 'max_turns': max_turns})

        UFFlowLogger.log_execution_start(
            "reactor",
            "execute_goal",
            goal=goal,
            max_turns=max_turns
        )

        # Initialize or reuse state
        if max_turns is None:
            max_turns = config.get_max_turns()

        if existing_state:
            # Resume with existing state (continue mode)
            state = existing_state
            state.max_turns = max_turns  # Update max_turns for continuation
            logger.info(f"Resuming execution from turn {state.turn_count} with goal: '{goal}'")
        else:
            # Start fresh
            state = ReActState(goal=goal, max_turns=max_turns)

        try:
            logger.info(f"Starting ReAct execution for goal: '{goal}'")

            # Get available tools
            available_tools = self.registry.list_ufs()
            if not available_tools:
                error_msg = "No tools available in registry"
                logger.error(error_msg)
                return self._create_error_result(state, error_msg)

            logger.info(f"Found {len(available_tools)} available tools")

            # Main ReAct loop - runs until max_turns or explicit break (finish/abort/pause)
            while state.turn_count < state.max_turns:
                turn_start_time = time.time()
                turn_number = state.turn_count + 1

                try:
                    logger.info(f"Starting turn {turn_number}/{state.max_turns}")

                    # ═══════════════════════════════════════════════════════
                    # (a) TURN START - LLM INVOCATION
                    # ═══════════════════════════════════════════════════════
                    self._emit(execution_id, turn_number, 'turn_started', {})

                    # Check for abort flag (user requested to stop execution)
                    if self.event_store and self.event_store.check_abort_flag(execution_id):
                        logger.info(f"Execution {execution_id} aborted by user")
                        self._emit(execution_id, turn_number,
                                 'execution_aborted',
                                 {'reason': 'User requested abort'},
                                 success=False)
                        state.completion_reason = "Aborted by user"
                        break

                    # Check for user interrupts
                    if self.event_store:
                        interrupt = self.event_store.check_feedback(execution_id, turn_number)
                        if interrupt:
                            interrupt_type = interrupt.get('feedback_type', 'feedback')

                            self._emit(execution_id, turn_number,
                                     'interrupt_received',
                                     {'type': interrupt_type, 'data': interrupt.get('feedback_data', {})})

                            if interrupt_type == 'feedback':
                                # Inject feedback into transcript, CONTINUE execution
                                self._inject_user_feedback(state, interrupt, turn_number)
                                self._emit(execution_id, turn_number,
                                         'feedback_injected',
                                         {'message': interrupt.get('feedback_data', {}).get('message', '')})
                                # NO BREAK - agent continues with guidance in context

                            elif interrupt_type in ['stop', 'pause', 'interrupt']:
                                # STOP or legacy interrupt types - abort execution
                                reason = interrupt.get('feedback_data', {}).get('message', 'User stopped execution')
                                self._emit(execution_id, turn_number,
                                         'execution_stopped',
                                         {'reason': reason, 'type': interrupt_type})
                                self.event_store.update_status(execution_id, 'stopped')
                                state.completion_reason = f"Stopped by user: {reason}"
                                break

                            else:
                                # Other legacy feedback types (input, approval)
                                self._handle_feedback(state, interrupt)

                    # A. Reason: Build prompt and get LLM response
                    messages = self.prompt_builder.build_messages_for_openai(state, available_tools)

                    # Generate JSON schema for structured output enforcement
                    json_schema = self._get_response_json_schema()

                    # Call LLM
                    self._emit(execution_id, turn_number, 'llm_called',
                              {'messages_count': len(messages)})

                    raw_response = self.llm_client.create_completion_text(
                        messages=messages,
                        json_schema=json_schema
                    )

                    # B. Reason: Parse the response
                    parsed_response = self._parse_llm_response(raw_response)

                    # ═══════════════════════════════════════════════════════
                    # (b) LLM RESPONSE PARSING
                    # ═══════════════════════════════════════════════════════
                    # Store complete LLM response with truncation for storage
                    llm_event_data = {
                        'reflect': parsed_response.reflect.model_dump(),
                        'strategize': parsed_response.strategize.model_dump(),
                        'action': {
                            'tool': parsed_response.act.tool,
                            'params': parsed_response.act.params
                        },
                        'raw_response': raw_response[:5000] if len(raw_response) > 5000 else raw_response,
                        'raw_response_length': len(raw_response),
                        'raw_response_truncated': len(raw_response) > 5000
                    }

                    self._emit(execution_id, turn_number,
                             'llm_response_success',
                             llm_event_data,
                             success=True)

                    # B.1. Update state from response
                    state.state = parsed_response.state

                    # ═══════════════════════════════════════════════════════
                    # (c) TURN BUDGET WARNINGS (P2 Enhancement)
                    # ═══════════════════════════════════════════════════════
                    self._check_turn_budget_warnings(execution_id, turn_number, state)

                    # ═══════════════════════════════════════════════════════
                    # (e) LLM ESCALATION - Check if LLM needs user input
                    # ═══════════════════════════════════════════════════════
                    if self._llm_requests_input(parsed_response):
                        self._emit(execution_id, turn_number,
                                 'llm_requests_input',
                                 {'request': self._extract_input_request(parsed_response)})
                        if self.event_store:
                            self.event_store.update_status(execution_id, 'paused')
                        break

                    if self._llm_requests_approval(parsed_response):
                        self._emit(execution_id, turn_number,
                                 'llm_requests_approval',
                                 {
                                     'action': parsed_response.act.tool,
                                     'reason': 'Requires approval'
                                 })
                        if self.event_store:
                            self.event_store.update_status(execution_id, 'paused')
                        break

                    # C. Check if agent used finish tool (pauses, doesn't complete)
                    if parsed_response.is_finish:
                        logger.info("Agent paused - indicated current objective addressed")

                        pause_reason = parsed_response.act.params.get("reason", "Agent believes current objective is addressed")
                        turn_duration = int((time.time() - turn_start_time) * 1000)

                        # Add finish turn to transcript
                        from reactor.models import TranscriptEntry
                        final_transcript_entry = TranscriptEntry(
                            turn=state.turn_count + 1,
                            reflect=parsed_response.reflect,
                            strategize=parsed_response.strategize,
                            state=parsed_response.state,
                            act=parsed_response.act,
                            observation=f"PAUSE: {pause_reason}",
                            duration_ms=turn_duration
                        )
                        state.transcript.append(final_transcript_entry)
                        state.turn_count += 1

                        state.completion_reason = pause_reason

                        self._emit(execution_id, turn_number,
                                 'execution_paused',
                                 {'reason': pause_reason},
                                 success=True)

                        # Update status so we don't emit another pause event
                        if self.event_store:
                            self.event_store.update_status(execution_id, 'paused')
                        break

                    # ═══════════════════════════════════════════════════════
                    # (c) TOOL EXECUTION
                    # ═══════════════════════════════════════════════════════
                    self._emit(execution_id, turn_number, 'tool_started',
                              {
                                  'tool': parsed_response.act.tool,
                                  'params': parsed_response.act.params
                              })

                    # D. Act: Execute the action with execution context
                    # Set execution context for tools that need it (like user_prompt)
                    self.tool_executor.set_execution_context(execution_id, turn_number)
                    observation = self.tool_executor.execute_action(parsed_response.act.model_dump())

                    # Determine success from observation
                    tool_success = not observation.startswith("ERROR")

                    # Extract artifact paths (now supports multiple)
                    artifact_paths = self._extract_artifact_paths(observation)

                    # Store complete tool output with intelligent truncation
                    tool_event_data = {
                        'tool': parsed_response.act.tool,
                        'observation': observation[:3000] if len(observation) > 3000 else observation,
                        'observation_length': len(observation),
                        'observation_truncated': len(observation) > 3000,
                        'tool_params': parsed_response.act.params
                    }

                    # Add artifact information if available (send first one to UI for now)
                    if artifact_paths:
                        # Send first artifact to UI (for backward compatibility)
                        tool_event_data['artifact_path'] = artifact_paths[0]
                        tool_event_data['artifact_type'] = self._detect_artifact_type(artifact_paths[0])
                        # Store all artifacts for future use
                        tool_event_data['all_artifacts'] = [
                            {'path': path, 'type': self._detect_artifact_type(path)}
                            for path in artifact_paths
                        ]

                    self._emit(execution_id, turn_number,
                             'tool_success' if tool_success else 'tool_failed',
                             tool_event_data,
                             success=tool_success)

                    # E. Observe & Update: Add to transcript
                    turn_duration = int((time.time() - turn_start_time) * 1000)
                    from reactor.models import TranscriptEntry
                    transcript_entry = TranscriptEntry(
                        turn=state.turn_count + 1,
                        reflect=parsed_response.reflect,
                        strategize=parsed_response.strategize,
                        state=parsed_response.state,
                        act=parsed_response.act,
                        observation=observation,
                        duration_ms=turn_duration
                    )

                    state.transcript.append(transcript_entry)
                    state.turn_count += 1

                    logger.info(f"Turn {state.turn_count} completed: {parsed_response.act.tool}")

                    # Auto-summarization: Keep context under control
                    # Summarize after every 5 turns (keeping last 5 verbatim)
                    if state.turn_count > 0 and state.turn_count % 5 == 0:
                        self._auto_summarize_if_needed(state)

                except Exception as e:
                    logger.error(f"Error in turn {state.turn_count + 1}: {e}")

                    # Add error observation to transcript
                    from reactor.models import TranscriptEntry, ReflectSection, StrategizeSection, ActSection, Hypothesis
                    error_entry = TranscriptEntry(
                        turn=state.turn_count + 1,
                        reflect=ReflectSection(
                            turn=state.turn_count + 1,
                            outcome="FAILURE",
                            hypothesisResult="N/A",
                            insight=f"Error: {str(e)}"
                        ),
                        strategize=StrategizeSection(
                            reasoning="Error recovery needed",
                            hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                            ifInvalidated="N/A"
                        ),
                        state=state.state,
                        act=ActSection(tool="error", params={"error": str(e)}),
                        observation=f"ERROR: {str(e)}",
                        duration_ms=int((time.time() - turn_start_time) * 1000)
                    )
                    state.transcript.append(error_entry)
                    state.turn_count += 1

            # Finalize state
            state.end_time = datetime.now()

            # Generate execution summary
            execution_summary = self._generate_execution_summary(state)

            duration = time.time() - start_time

            UFFlowLogger.log_execution_end(
                "reactor",
                "execute_goal",
                True,  # Always "successful" - just paused
                duration_ms=int(duration * 1000),
                turns_taken=state.turn_count
            )

            logger.info(f"ReAct execution paused: turns={state.turn_count}")

            # Update final status in event store
            if self.event_store:
                # Check current status to avoid overwriting 'paused' or 'cancelled'
                current_status = self.event_store.get_execution_status(execution_id)
                if current_status and current_status['status'] in ['paused', 'cancelled']:
                    # Already handled (agent used finish or user cancelled)
                    logger.info(f"Execution {execution_id} ended with status: {current_status['status']}")
                else:
                    # Max turns reached - pause for user input
                    pause_reason = 'Max turns reached - awaiting user input'
                    self._emit(execution_id, state.turn_count,
                             'execution_paused',
                             {'reason': pause_reason, 'is_max_turns': True, 'current_turns': state.turn_count, 'max_turns': state.max_turns},
                             success=True)

                    self.event_store.update_status(execution_id, 'paused')

            return ReActResult(
                success=True,  # Always successful - just paused
                state=state,
                execution_summary=execution_summary
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Unexpected error during ReAct execution: {e}"
            logger.error(error_msg)

            if self.event_store and execution_id:
                import traceback
                self._emit(execution_id, state.turn_count,
                         'execution_failed',
                         {'error': str(e), 'traceback': traceback.format_exc()},
                         success=False)
                self.event_store.update_status(execution_id, 'failed')

            UFFlowLogger.log_execution_end(
                "reactor",
                "execute_goal",
                False,
                duration_ms=int(duration * 1000),
                error_type="unexpected",
                error_message=str(e)
            )

            return self._create_error_result(state, error_msg)

    def _emit(self, execution_id: str, turn_number: int,
              event_type: str, event_data: dict, success: bool = None):
        """Helper to emit events (no-op if no event store)."""
        if self.event_store and execution_id:
            self.event_store.emit_event(
                execution_id, turn_number, event_type, event_data, success
            )

    def _llm_requests_input(self, parsed_response) -> bool:
        """Check if LLM is requesting user input."""
        # Example: LLM uses special tool 'request_user_input'
        return parsed_response.act.tool == 'request_user_input'

    def _llm_requests_approval(self, parsed_response) -> bool:
        """Check if LLM is requesting approval for risky action."""
        # Example: Check if action has 'safe' field indicating approval needed
        return (hasattr(parsed_response.act, 'safe') and
                parsed_response.act.safe is not None and
                'approval' in str(parsed_response.act.safe).lower())

    def _extract_input_request(self, parsed_response) -> str:
        """Extract what input LLM is requesting."""
        return parsed_response.act.params.get('request', 'Input needed')

    def _inject_user_feedback(self, state: ReActState, interrupt: dict, turn_number: int):
        """Inject user feedback as a transcript entry so LLM sees it in next turn."""
        from reactor.models import TranscriptEntry, ReflectSection, StrategizeSection, ActSection, Hypothesis

        feedback_msg = interrupt.get('feedback_data', {}).get('message', 'User provided feedback')

        feedback_entry = TranscriptEntry(
            turn=turn_number,
            reflect=ReflectSection(
                turn=turn_number,
                outcome="SUCCESS",
                hypothesisResult="N/A",
                insight="Received user guidance"
            ),
            strategize=StrategizeSection(
                reasoning="Incorporating user guidance into investigation",
                hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                ifInvalidated="N/A"
            ),
            state=state.state,
            act=ActSection(tool="user_feedback", params={"message": feedback_msg}),
            observation=f"👤 USER GUIDANCE: {feedback_msg}",
            duration_ms=0
        )

        state.transcript.append(feedback_entry)
        state.turn_count += 1

        logger.info(f"Injected user feedback into transcript at turn {turn_number}: {feedback_msg[:100]}")

    def _handle_feedback(self, state, feedback: dict):
        """Incorporate user feedback into state (legacy method for other feedback types)."""
        feedback_type = feedback['feedback_type']
        feedback_data = feedback['feedback_data']

        if feedback_type == 'input':
            # Add user input as special observation
            user_input = feedback_data.get('input', '')
            # Will be picked up in next turn's prompt
            if not hasattr(state, 'pending_user_input'):
                state.pending_user_input = user_input

        elif feedback_type == 'approval':
            # User approved risky action
            if not hasattr(state, 'user_approved_action'):
                state.user_approved_action = feedback_data.get('action', '')

    def _save_final_results(self, state: ReActState, completion_reason: str) -> str:
        """Save final results to a file for complete output preservation."""
        try:
            # Create goal hash for unique filename
            goal_hash = hashlib.md5(state.goal.encode()).hexdigest()[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"final_result_{goal_hash}_{timestamp}.txt"

            # Collect comprehensive results
            results_content = [
                "=" * 80,
                "UFFLOW REACTOR - FINAL RESULTS",
                "=" * 80,
                f"Goal: {state.goal}",
                f"Completion Reason: {completion_reason}",
                f"Turns Completed: {state.turn_count}",
                f"Execution Time: {state.start_time.strftime('%Y-%m-%d %H:%M:%S')} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "=" * 40 + " EXECUTION TRACE " + "=" * 40,
                ""
            ]

            # Add all turns with FULL observations (no truncation)
            import json
            for entry in state.transcript:
                results_content.extend([
                    f"--- TURN {entry.turn} ---",
                    f"Reflect: {json.dumps(entry.reflect.model_dump(), indent=2)}",
                    f"Strategize: {json.dumps(entry.strategize.model_dump(), indent=2)}",
                    f"Act: {json.dumps(entry.act.model_dump(), indent=2)}",
                    f"Observation: {entry.observation}",  # Full observation, not truncated
                    ""
                ])

            # Extract and highlight final outputs from last few turns
            final_outputs = self._extract_final_outputs(state)
            if final_outputs:
                results_content.extend([
                    "=" * 40 + " FINAL OUTPUTS " + "=" * 40,
                    ""
                ])
                results_content.extend(final_outputs)

            # Also capture the very last full stdout if available
            last_full_stdout = self.tool_executor.get_last_full_stdout()
            if last_full_stdout and len(last_full_stdout) > 100:
                results_content.extend([
                    "",
                    "=" * 40 + " COMPLETE FINAL OUTPUT " + "=" * 40,
                    "# This is the complete, untruncated output from the final command:",
                    "",
                    last_full_stdout,
                    ""
                ])

            # Write to file securely
            from core.workspace_security import secure_write_text, validate_workspace_path
            content = '\n'.join(results_content)
            secure_write_text(filename, content)
            full_path = validate_workspace_path(filename, "file creation")

            logger.info(f"Final results saved to: {full_path}")
            return full_path

        except Exception as e:
            logger.error(f"Failed to save final results: {e}")
            return f"ERROR: Could not save final results - {e}"

    def _extract_final_outputs(self, state: ReActState) -> List[str]:
        """Extract meaningful final outputs from recent turns."""
        outputs = []

        # Look at last 3 turns for significant results
        recent_turns = state.transcript[-3:] if len(state.transcript) >= 3 else state.transcript

        for entry in recent_turns:
            observation = entry.observation

            # Extract stdout from SUCCESS observations
            if "SUCCESS" in observation and "stdout:" in observation:
                # Try to extract the actual stdout content
                import re
                stdout_match = re.search(r'stdout:\s*([^|]+)', observation)
                if stdout_match:
                    stdout_content = stdout_match.group(1).strip()
                    if len(stdout_content) > 50:  # Significant output
                        outputs.extend([
                            f"From Turn {entry.turn} ({entry.act.tool}):",
                            stdout_content,
                            ""
                        ])

        return outputs

    def _get_response_json_schema(self) -> Dict[str, Any]:
        """Generate JSON schema for structured output enforcement."""
        from reactor.models import ParsedLLMResponse

        # Get the JSON schema from the Pydantic model
        schema = ParsedLLMResponse.model_json_schema()

        return {
            "name": "react_response",
            "schema": schema
        }

    def _parse_llm_response(self, raw_response: str) -> ParsedLLMResponse:
        """Parse LLM response in new JSON format."""
        import json
        import re
        try:
            logger.debug(f"Parsing LLM response: {raw_response[:200]}...")

            # Try to parse as direct JSON first (from structured output)
            try:
                response_data = json.loads(raw_response)
            except json.JSONDecodeError:
                # Fall back to extracting JSON from markdown or text
                # Extract JSON from response (handle markdown code blocks)
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # Try to find raw JSON
                    json_match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        raise ValueError("No JSON found in response")

                # Parse JSON
                response_data = json.loads(json_str)

            # Validate and create ParsedLLMResponse
            from reactor.models import ReflectSection, StrategizeSection, State, ActSection, Hypothesis

            # Handle wrapped response format (if LLM returns {"response": {...}})
            if "response" in response_data and isinstance(response_data["response"], dict):
                response_data = response_data["response"]

            reflect = ReflectSection(**response_data.get("reflect", {}))

            strategize_data = response_data.get("strategize", {})
            hypothesis_data = strategize_data.get("hypothesis", {})
            hypothesis = Hypothesis(**hypothesis_data)
            strategize = StrategizeSection(
                reasoning=strategize_data.get("reasoning", ""),
                hypothesis=hypothesis,
                ifInvalidated=strategize_data.get("ifInvalidated", "")
            )

            state = State(**response_data.get("state", {}))

            # Handle case where act might be None (when task is complete)
            act_data = response_data.get("act")
            if act_data is None:
                # Create a finish action when act is null
                act = ActSection(tool="finish", params={})
            else:
                act = ActSection(**act_data)

            # Check if this is a finish action
            is_finish = act.tool == "finish"

            return ParsedLLMResponse(
                reflect=reflect,
                strategize=strategize,
                state=state,
                act=act,
                is_finish=is_finish,
                raw_response=raw_response
            )

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Full raw response: {raw_response}")

            # Return a default error response
            from reactor.models import ReflectSection, StrategizeSection, State, ActSection, Hypothesis

            return ParsedLLMResponse(
                reflect=ReflectSection(
                    turn=1,
                    outcome="FAILURE",
                    hypothesisResult="N/A",
                    insight=f"Failed to parse response: {str(e)}"
                ),
                strategize=StrategizeSection(
                    reasoning="Error in parsing",
                    hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                    ifInvalidated="Retry"
                ),
                state=State(goal="unknown"),
                act=ActSection(tool="error", params={"error": f"Parse error: {e}"}),
                is_finish=False,
                raw_response=raw_response
            )

    def _generate_execution_summary(self, state: ReActState) -> str:
        """Generate human-readable execution summary."""
        summary = f"⏸️  Execution paused after {state.turn_count} turns"
        if state.completion_reason:
            summary += f": {state.completion_reason}"

        # Add turn breakdown
        if state.transcript:
            actions_taken = [entry.act.tool for entry in state.transcript]
            unique_actions = list(set(actions_taken))
            summary += f"\nActions used: {', '.join(unique_actions)}"

        return summary

    def _extract_thought_intent_and_action(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract thought, intent, and action from raw response using multiple strategies."""

        # Extract WORKING MEMORY UPDATE (new structured format)
        working_memory_update = None
        memory_match = re.search(r'WORKING MEMORY UPDATE:\s*(.*?)(?=PROGRESS CHECK:|Thought:|Intent:|Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)
        if memory_match:
            memory_content = memory_match.group(1).strip()
            working_memory_update = self._parse_working_memory_update(memory_content)
            if working_memory_update:
                logger.debug(f"Extracted working memory update with {len(working_memory_update.get('new_facts', []))} new facts")

        # Extract PROGRESS CHECK (new field)
        progress_check = None
        progress_match = re.search(r'PROGRESS CHECK:\s*(.*?)(?=Thought:|Intent:|Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)
        if progress_match:
            progress_check = progress_match.group(1).strip()
            logger.debug(f"Extracted progress check: {progress_check[:100]}...")

        # Strategy 1: Enhanced regex extraction with new format
        thought_match = re.search(r'Thought:\s*(.*?)(?=Intent:|Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)

        if not thought_match:
            # Strategy 2: Try alternative formats
            thought_match = re.search(r'💭\s*Thought:\s*(.*?)(?=Intent:|🛠️\s*Action:|Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)

        if not thought_match:
            # Fallback: Look for old format without Intent
            thought_match = re.search(r'Thought:\s*(.*?)(?=Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)

        if not thought_match:
            logger.error("Could not extract thought from response")
            return None

        thought = thought_match.group(1).strip()

        # Extract intent (optional for backwards compatibility)
        intent = None
        intent_match = re.search(r'Intent:\s*(.*?)(?=Action:|$)', raw_response, re.DOTALL | re.IGNORECASE)
        if intent_match:
            intent = intent_match.group(1).strip()
            logger.debug(f"Extracted intent: {intent}")

        # Extract action JSON with multiple strategies
        action_json = self._extract_action_json(raw_response)

        if not action_json:
            logger.error("Could not extract action JSON from response")
            return None

        result = {
            "thought": thought,
            "action": action_json
        }

        if intent:
            result["intent"] = intent
        if working_memory_update:
            result["working_memory_update"] = working_memory_update
        if progress_check:
            result["progress_check"] = progress_check

        return result

    def _parse_working_memory_update(self, memory_content: str) -> Optional[Dict[str, Any]]:
        """Parse structured working memory update from agent response."""
        try:
            update = {}

            # Extract NEW_FACTS
            facts_match = re.search(r'NEW_FACTS:\s*\[(.*?)\]', memory_content, re.DOTALL | re.IGNORECASE)
            if facts_match:
                facts_str = facts_match.group(1)
                # Parse list of quoted strings
                facts = re.findall(r'"([^"]*)"', facts_str)
                update['new_facts'] = facts

            # Extract HYPOTHESIS
            hypothesis_match = re.search(r'HYPOTHESIS:\s*"([^"]*)"', memory_content, re.IGNORECASE)
            if hypothesis_match:
                update['updated_hypothesis'] = hypothesis_match.group(1)

            # Extract EVIDENCE_GAPS
            gaps_match = re.search(r'EVIDENCE_GAPS:\s*\[(.*?)\]', memory_content, re.DOTALL | re.IGNORECASE)
            if gaps_match:
                gaps_str = gaps_match.group(1)
                gaps = re.findall(r'"([^"]*)"', gaps_str)
                update['new_gaps'] = gaps

            # Extract FAILED_APPROACHES
            failed_match = re.search(r'FAILED_APPROACHES:\s*\[(.*?)\]', memory_content, re.DOTALL | re.IGNORECASE)
            if failed_match:
                failed_str = failed_match.group(1)
                if failed_str.strip():  # Only if not empty
                    failed = re.findall(r'"([^"]*)"', failed_str)
                    if failed:
                        update['failed_approach'] = failed[0]  # Take first one

            # Extract NEXT_PRIORITIES
            priorities_match = re.search(r'NEXT_PRIORITIES:\s*\[(.*?)\]', memory_content, re.DOTALL | re.IGNORECASE)
            if priorities_match:
                priorities_str = priorities_match.group(1)
                priorities = re.findall(r'"([^"]*)"', priorities_str)
                update['next_actions'] = priorities

            # Extract SYNTHESIS
            synthesis_match = re.search(r'SYNTHESIS:\s*"([^"]*)"', memory_content, re.IGNORECASE)
            if synthesis_match:
                update['synthesis_update'] = synthesis_match.group(1)

            return update if update else None

        except Exception as e:
            logger.warning(f"Failed to parse working memory update: {e}")
            return None

    def _update_working_memory(self, state: ReActState, memory_update: Dict[str, Any]) -> None:
        """Update the state's working memory based on parsed update."""
        try:
            # Add new facts
            if 'new_facts' in memory_update:
                for fact in memory_update['new_facts']:
                    if fact and fact not in state.working_memory.known_facts:
                        state.working_memory.known_facts.append(fact)

            # Update hypothesis
            if 'updated_hypothesis' in memory_update:
                state.working_memory.current_hypothesis = memory_update['updated_hypothesis']

            # Add new evidence gaps
            if 'new_gaps' in memory_update:
                for gap in memory_update['new_gaps']:
                    if gap and gap not in state.working_memory.evidence_gaps:
                        state.working_memory.evidence_gaps.append(gap)

            # Add failed approach
            if 'failed_approach' in memory_update:
                approach = memory_update['failed_approach']
                if approach and approach not in state.working_memory.failed_approaches:
                    state.working_memory.failed_approaches.append(approach)

            # Update next priorities (replace, don't append)
            if 'next_actions' in memory_update:
                state.working_memory.next_priorities = memory_update['next_actions']

            # Update synthesis notes
            if 'synthesis_update' in memory_update:
                state.working_memory.synthesis_notes = memory_update['synthesis_update']

            logger.debug(f"Updated working memory: {len(state.working_memory.known_facts)} facts, {len(state.working_memory.evidence_gaps)} gaps")

        except Exception as e:
            logger.error(f"Failed to update working memory: {e}")

    def _extract_action_json(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract action JSON using multiple robust strategies."""
        strategies = [
            self._extract_json_with_balanced_braces,
            self._extract_json_with_regex,
            self._extract_json_with_heuristics
        ]

        for strategy in strategies:
            try:
                result = strategy(raw_response)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                continue

        return None

    def _extract_json_with_balanced_braces(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON using balanced brace matching."""
        action_start = raw_response.find('Action:')
        if action_start == -1:
            action_start = raw_response.find('🛠️  Action:')

        if action_start != -1:
            brace_start = raw_response.find('{', action_start)
            if brace_start != -1:
                brace_count = 0
                brace_end = -1
                for i in range(brace_start, len(raw_response)):
                    if raw_response[i] == '{':
                        brace_count += 1
                    elif raw_response[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            brace_end = i
                            break

                if brace_end != -1:
                    json_str = raw_response[brace_start:brace_end + 1]
                    # Fix Python dict format to JSON format
                    json_str = self._normalize_dict_to_json(json_str)
                    return json.loads(json_str)
        return None

    def _normalize_dict_to_json(self, dict_str: str) -> str:
        """Convert Python dict format to JSON format."""
        try:
            # Use ast.literal_eval to safely parse Python dict format
            import ast
            python_dict = ast.literal_eval(dict_str)
            # Convert to proper JSON
            return json.dumps(python_dict)
        except:
            # If ast fails, try simple replacements
            # Replace single quotes with double quotes for keys and string values
            normalized = re.sub(r"'([^']*)':", r'"\1":', dict_str)  # Keys
            normalized = re.sub(r":\s*'([^']*)'", r': "\1"', normalized)  # String values
            normalized = re.sub(r":\s*None", r': null', normalized)  # None values
            normalized = re.sub(r":\s*True", r': true', normalized)  # True values
            normalized = re.sub(r":\s*False", r': false', normalized)  # False values
            return normalized

    def _extract_json_with_regex(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON using regex patterns."""
        patterns = [
            r'Action:\s*({.*?})',
            r'🛠️\s*Action:\s*({.*?})',
            r'"tool_name":\s*"([^"]+)".*?"parameters":\s*({.*?})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, raw_response, re.DOTALL)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        # Handle complex patterns
                        if len(match) == 2:
                            return {
                                "tool_name": match[0],
                                "parameters": json.loads(match[1])
                            }
                    else:
                        return json.loads(match)
                except (json.JSONDecodeError, IndexError):
                    continue
        return None

    def _extract_json_with_heuristics(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON using heuristic parsing for malformed JSON."""
        # Look for tool_name patterns
        tool_match = re.search(r'"tool_name":\s*"([^"]+)"', raw_response)
        if not tool_match:
            return None

        tool_name = tool_match.group(1)
        result = {"tool_name": tool_name}

        # Look for parameters
        params_match = re.search(r'"parameters":\s*({.*?})', raw_response, re.DOTALL)
        if params_match:
            try:
                result["parameters"] = json.loads(params_match.group(1))
            except json.JSONDecodeError:
                # Try to fix common issues in parameters
                params_str = params_match.group(1)
                # Fix unescaped newlines and quotes in script content
                if "script_content" in params_str:
                    result["parameters"] = self._extract_script_parameters(params_str)
                else:
                    result["parameters"] = {}

        # Look for reason (finish actions)
        reason_match = re.search(r'"reason":\s*"([^"]*)"', raw_response)
        if reason_match:
            result["reason"] = reason_match.group(1)

        return result

    def _extract_script_parameters(self, params_str: str) -> Dict[str, Any]:
        """Extract script parameters with special handling for multiline content."""
        result = {}

        # Extract script_content with special handling
        script_match = re.search(r'"script_content":\s*"(.*?)"(?=,\s*"|\s*})', params_str, re.DOTALL)
        if script_match:
            script_content = script_match.group(1)
            # Basic cleanup - this is a simplified approach
            script_content = script_content.replace('\\n', '\n').replace('\\"', '"')
            result["script_content"] = script_content

        # Extract script_type
        type_match = re.search(r'"script_type":\s*"([^"]*)"', params_str)
        if type_match:
            result["script_type"] = type_match.group(1)

        return result

    def _fallback_parse(self, raw_response: str, parsed_data: Dict[str, Any]) -> ParsedLLMResponse:
        """Fallback parsing when schema validation fails."""
        try:
            # Try to construct a basic valid action
            action_data = parsed_data.get("action", {})

            if isinstance(action_data, dict) and "tool_name" in action_data:
                action = {
                    "tool_name": action_data["tool_name"],
                    "parameters": action_data.get("parameters", {}),
                }

                if "reason" in action_data:
                    action["reason"] = action_data["reason"]

                is_finish = action["tool_name"] == "finish"

                # Handle working memory update in fallback
                wm_update = None
                if parsed_data.get("working_memory_update"):
                    try:
                        from reactor.models import WorkingMemoryUpdate
                        wm_update = WorkingMemoryUpdate(**parsed_data["working_memory_update"])
                    except Exception:
                        pass

                return ParsedLLMResponse(
                    thought=parsed_data.get("thought", "Unable to extract thought"),
                    intent=parsed_data.get("intent"),
                    action=action,
                    working_memory_update=wm_update,
                    progress_check=parsed_data.get("progress_check"),
                    is_finish=is_finish,
                    raw_response=raw_response
                )
            else:
                raise ValueError("Could not construct valid action from parsed data")

        except Exception as e:
            logger.error(f"Fallback parsing also failed: {e}")
            return ParsedLLMResponse(
                thought="Failed to parse response",
                intent=None,
                action={"tool_name": "error", "error": f"Fallback parse error: {e}"},
                is_finish=False,
                raw_response=raw_response
            )

    def _setup_python_environment(self):
        """Setup Python virtual environment at agent startup if needed."""
        try:
            # Check if this is a Python project
            if not self._is_python_project():
                return

            # Check if venv is already active
            if self._has_active_venv():
                logger.info("Python virtual environment already active")
                return

            # Check if venv exists but isn't active
            venv_path = self._find_venv_path()
            if venv_path:
                # Only show venv messages if logging level allows INFO messages
                root_logger = logging.getLogger()
                if root_logger.level <= logging.INFO:
                    print(f"🐍 Python virtual environment found at {venv_path} but not active")
                    print(f"💡 To activate: source {venv_path}/bin/activate (or Scripts\\activate.bat on Windows)")
                return

            # No venv found - create one automatically
            print(f"🐍 Python project detected but no virtual environment found")
            print(f"🔧 Creating virtual environment...")

            success = self._create_and_activate_venv()
            if success:
                print(f"✅ Virtual environment created and activated at .venv")
            else:
                print(f"⚠️  Could not create venv automatically. Please run:")
                print(f"   python -m venv .venv && source .venv/bin/activate")

        except Exception as e:
            logger.warning(f"Error checking Python environment at startup: {e}")

    def _is_python_project(self) -> bool:
        """Check if current directory is a Python project."""
        python_files = [
            "requirements.txt", "pyproject.toml", "setup.py",
            "setup.cfg", "Pipfile", "poetry.lock"
        ]

        # Check for Python config files
        for file in python_files:
            if os.path.exists(file):
                return True

        # Check for .py files in current directory
        try:
            for item in os.listdir("."):
                if item.endswith(".py"):
                    return True
        except OSError:
            pass

        return False

    def _has_active_venv(self) -> bool:
        """Check if a virtual environment is currently active."""
        return (os.environ.get("VIRTUAL_ENV") is not None or
                os.environ.get("CONDA_DEFAULT_ENV") is not None)

    def _find_venv_path(self) -> str:
        """Find existing virtual environment in common locations."""
        venv_dirs = [
            ".venv", "venv", "env", ".env",  # Common generic names
            "virtualenv", ".virtualenv",      # virtualenv tool
            "venv-dev", "venv-prod",         # Environment-specific
            ".pyenv", "pyenv-versions",      # pyenv
            "conda-env", ".conda"            # conda environments (local)
        ]

        # Add version-specific patterns (e.g., venv38, venv312, py39, python311)
        current_version = f"{sys.version_info.major}{sys.version_info.minor}"
        version_patterns = [
            f"venv{current_version}", f".venv{current_version}",
            f"py{current_version}", f".py{current_version}",
            f"python{current_version}", f".python{current_version}"
        ]

        # Also check common versions even if not current (people switch versions)
        for version in ["38", "39", "310", "311", "312", "313"]:
            version_patterns.extend([
                f"venv{version}", f".venv{version}",
                f"py{version}", f".py{version}",
                f"python{version}", f".python{version}"
            ])

        venv_dirs.extend(version_patterns)

        for venv_dir in venv_dirs:
            if os.path.isdir(venv_dir):
                # Check if it's a valid venv (has bin/activate or Scripts/activate.bat)
                activate_script = os.path.join(venv_dir, "bin", "activate")
                activate_bat = os.path.join(venv_dir, "Scripts", "activate.bat")

                if os.path.exists(activate_script) or os.path.exists(activate_bat):
                    return venv_dir

        return ""

    def _create_and_activate_venv(self) -> bool:
        """Create and activate a virtual environment."""
        try:
            import subprocess

            # Create venv using direct subprocess call
            logger.info("Creating virtual environment at .venv")
            result = subprocess.run(
                [sys.executable, "-m", "venv", ".venv"],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                # Activate the venv by setting environment variables
                venv_path = ".venv"
                venv_bin = os.path.join(venv_path, "bin" if os.name != "nt" else "Scripts")

                if os.path.exists(venv_bin):
                    # Set environment variables to activate the venv
                    os.environ["VIRTUAL_ENV"] = os.path.abspath(venv_path)
                    os.environ["PATH"] = f"{os.path.abspath(venv_bin)}{os.pathsep}{os.environ.get('PATH', '')}"

                    # Remove PYTHONHOME if it exists (can interfere with venv)
                    if "PYTHONHOME" in os.environ:
                        del os.environ["PYTHONHOME"]

                    logger.info(f"Virtual environment created and activated: {os.environ['VIRTUAL_ENV']}")
                    return True
            else:
                logger.error(f"Failed to create venv: {result.stderr}")

        except Exception as e:
            logger.error(f"Failed to create virtual environment: {e}")

        return False

    def _extract_artifact_paths(self, observation: str) -> list:
        """Extract all artifact file paths from observation."""
        import re
        artifacts = []

        # Pattern 1: Large output saved to temp file
        match = re.search(r'Full output saved to:\s*([^\s\n]+)', observation)
        if match:
            full_path = match.group(1)
            # Extract relative path from temp directory
            if '.ufflow_temp' in full_path:
                parts = full_path.split('.ufflow_temp/')
                if len(parts) > 1:
                    artifacts.append(parts[1])  # Add relative path

        # Pattern 2: All "Artifact available:" markers (supports multiple)
        matches = re.findall(r'Artifact available:\s*([^\s\n]+)', observation)
        for match in matches:
            artifact_path = match.strip()
            if artifact_path not in artifacts:
                artifacts.append(artifact_path)

        return artifacts

    def _extract_artifact_path(self, observation: str) -> Optional[str]:
        """Extract first artifact file path from observation (backward compatibility)."""
        artifacts = self._extract_artifact_paths(observation)
        return artifacts[0] if artifacts else None

    def _detect_artifact_type(self, artifact_path: str) -> str:
        """Detect artifact type from file path/extension."""
        if not artifact_path:
            return 'text'

        # Extract extension
        _, ext = os.path.splitext(artifact_path.lower())

        # Map extensions to types
        type_map = {
            '.json': 'json',
            '.log': 'logs',
            '.txt': 'text',
            '.md': 'markdown',
            '.csv': 'table',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.xml': 'xml',
            '.html': 'html'
        }

        # Check for code file extensions
        code_exts = {'.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c', '.rb', '.php'}
        if ext in code_exts:
            return 'code'

        # Check for trace/metric patterns in filename
        filename_lower = artifact_path.lower()
        if 'trace' in filename_lower or 'span' in filename_lower:
            return 'traces'
        if 'metric' in filename_lower or 'stats' in filename_lower:
            return 'metrics'

        return type_map.get(ext, 'text')

    def _auto_summarize_if_needed(self, state: ReActState) -> None:
        """
        Auto-summarize transcript to prevent context bloat.
        Keeps last 5 turns verbatim, summarizes older turns.
        """
        KEEP_LAST_N = 5

        if len(state.transcript) <= KEEP_LAST_N:
            return  # Not enough turns to summarize

        logger.info(f"Auto-summarizing: {len(state.transcript)} turns -> keeping last {KEEP_LAST_N}")

        # Split transcript
        older_turns = state.transcript[:-KEEP_LAST_N]
        recent_turns = state.transcript[-KEEP_LAST_N:]

        # Create summary entry
        from reactor.models import TranscriptEntry, ReflectSection, StrategizeSection, ActSection, Hypothesis

        turn_range = f"{older_turns[0].turn}-{older_turns[-1].turn}"
        tools_used = list(set(turn.act.tool for turn in older_turns))
        successes = sum(1 for t in older_turns if t.reflect.outcome == "SUCCESS")
        failures = sum(1 for t in older_turns if t.reflect.outcome == "FAILURE")

        summary_observation = (
            f"📋 AUTO-SUMMARIZED CONTEXT (Turns {turn_range})\n\n"
            f"Turns: {len(older_turns)} | Success/Failure: {successes}/{failures}\n"
            f"Tools: {', '.join(tools_used[:5])}\n\n"
            f"💡 All facts, ruled-out hypotheses, and diagnostic state preserved in agent state."
        )

        summary_entry = TranscriptEntry(
            turn=0,
            reflect=ReflectSection(
                turn=0,
                outcome="SUCCESS",
                hypothesisResult="N/A",
                insight=f"Summarized {len(older_turns)} older turns"
            ),
            strategize=StrategizeSection(
                reasoning="Auto-condensed older context to prevent bloat",
                hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                ifInvalidated="N/A"
            ),
            state=state.state,
            act=ActSection(tool="auto_summary", params={"turns_summarized": len(older_turns)}),
            observation=summary_observation,
            duration_ms=0
        )

        # Update transcript: [summary] + recent turns
        state.transcript = [summary_entry] + recent_turns
        logger.info(f"Auto-summarization complete: {len(state.transcript)} entries remain")

    def _check_turn_budget_warnings(self, execution_id: str, turn_number: int, state: ReActState):
        """
        P2 Enhancement: Check turn budget and emit warnings at key thresholds.
        Helps agent be more efficient and consider finishing when approaching limits.
        """
        max_turns = state.max_turns
        percent_used = (turn_number / max_turns) * 100

        # Warning thresholds
        WARNING_AT_50_PERCENT = max_turns // 2  # 50% of budget
        WARNING_AT_75_PERCENT = int(max_turns * 0.75)  # 75% of budget
        CRITICAL_AT_90_PERCENT = int(max_turns * 0.9)  # 90% of budget

        warning_message = None
        warning_level = None

        if turn_number == WARNING_AT_50_PERCENT:
            warning_message = f"⚠️  Turn budget: {turn_number}/{max_turns} ({percent_used:.0f}%) - Consider focusing on highest-priority findings"
            warning_level = "info"

        elif turn_number == WARNING_AT_75_PERCENT:
            warning_message = f"⚠️  Turn budget: {turn_number}/{max_turns} ({percent_used:.0f}%) - Start consolidating findings, prepare for finish"
            warning_level = "warning"

        elif turn_number == CRITICAL_AT_90_PERCENT:
            warning_message = f"🚨 Turn budget CRITICAL: {turn_number}/{max_turns} ({percent_used:.0f}%) - MUST finish soon with comprehensive summary"
            warning_level = "critical"

        if warning_message:
            logger.warning(warning_message)
            self._emit(execution_id, turn_number,
                      'turn_budget_warning',
                      {
                          'turn': turn_number,
                          'max_turns': max_turns,
                          'percent_used': percent_used,
                          'message': warning_message,
                          'level': warning_level,
                          'recommendation': self._get_budget_recommendation(percent_used)
                      })

    def _get_budget_recommendation(self, percent_used: float) -> str:
        """Get recommendation based on turn budget usage."""
        if percent_used >= 90:
            return "Use 'finish' tool immediately with comprehensive summary of all findings across turns"
        elif percent_used >= 75:
            return "Begin synthesizing findings from all turns into a coherent report. Plan to use 'finish' tool within next 2-3 turns"
        elif percent_used >= 50:
            return "Focus on completing high-priority investigations. Avoid exploring new tangents unless critical"
        else:
            return "Continue investigation as planned"

    def _create_error_result(self, state: ReActState, error_message: str) -> ReActResult:
        """Create error result for failed executions."""
        state.end_time = datetime.now()
        return ReActResult(
            success=False,
            state=state,
            error_message=error_message,
            execution_summary=f"❌ Execution failed: {error_message}"
        )