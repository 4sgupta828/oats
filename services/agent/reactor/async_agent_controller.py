"""Async Agent Controller with event emission support."""

import asyncio
import time
import traceback
from datetime import datetime
from typing import Optional

from .agent_controller import AgentController
from .event_emitter import NullEventEmitter
from .models import ReActState, ReActResult, TranscriptEntry
from core.logging_config import get_logger

logger = get_logger('reactor.async_agent_controller')


class AsyncAgentController(AgentController):
    """
    Fully async agent controller that emits events during execution.
    Compatible with both WebSocket and SSE transports.
    """

    def __init__(self, registry, event_emitter=None):
        super().__init__(registry)
        self.event_emitter = event_emitter or NullEventEmitter()
        self.execution_id = None

    async def execute_goal_async(
        self, goal: str, max_turns: Optional[int] = None, execution_id: str = None
    ) -> ReActResult:
        """
        Fully async execution with event emission.

        Args:
            goal: The goal to achieve
            max_turns: Maximum number of turns
            execution_id: Unique execution identifier for event tracking

        Returns:
            ReActResult with execution outcome
        """
        self.execution_id = execution_id
        start_time = time.time()

        # Initialize state
        from core.config import config
        if max_turns is None:
            max_turns = config.get_max_turns()
        state = ReActState(goal=goal, max_turns=max_turns)

        try:
            # Emit execution started event
            await self.event_emitter.emit(
                execution_id,
                0,
                "execution_started",
                {"goal": goal, "max_turns": max_turns},
                success=True,
            )

            logger.info(f"Starting async ReAct execution for goal: '{goal}'")

            # Get available tools
            available_tools = self.registry.list_ufs()
            if not available_tools:
                error_msg = "No tools available in registry"
                logger.error(error_msg)
                await self._emit_error(execution_id, 0, error_msg)
                return self._create_error_result(state, error_msg)

            logger.info(f"Found {len(available_tools)} available tools")

            # Main ReAct loop
            while state.turn_count < state.max_turns and not state.is_complete:
                turn_number = state.turn_count + 1
                turn_start_time = time.time()

                try:
                    logger.info(f"Starting turn {turn_number}/{state.max_turns}")

                    # Emit turn started
                    await self.event_emitter.emit(
                        execution_id,
                        turn_number,
                        "turn_started",
                        {"turn_number": turn_number, "goal": goal, "max_turns": max_turns},
                    )

                    # Check for user feedback (for pause/resume functionality)
                    feedback = await self._check_for_feedback(execution_id, turn_number)
                    if feedback:
                        await self._handle_feedback(state, feedback)
                        if feedback['feedback_type'] == 'interrupt':
                            logger.info("Execution interrupted by user")
                            break

                    # A. Reason: Build prompt and get LLM response
                    messages = self.prompt_builder.build_messages_for_openai(
                        state, available_tools
                    )
                    json_schema = self._get_response_json_schema()

                    # Emit LLM called event
                    await self.event_emitter.emit(
                        execution_id,
                        turn_number,
                        "llm_called",
                        {"messages_count": len(messages), "model": "claude-3-5-sonnet"},
                    )

                    # Call LLM (run in thread pool to not block event loop)
                    raw_response = await asyncio.to_thread(
                        self.llm_client.create_completion_text,
                        messages=messages,
                        json_schema=json_schema,
                    )

                    # B. Parse the response
                    parsed_response = self._parse_llm_response(raw_response)

                    # Emit LLM response success
                    await self.event_emitter.emit(
                        execution_id,
                        turn_number,
                        "llm_response_success",
                        {
                            "turn_number": turn_number,
                            "raw_response_length": len(raw_response),
                            "parsed_successfully": True,
                            "reflect": (
                                parsed_response.reflect.model_dump()
                                if parsed_response.reflect
                                else None
                            ),
                            "strategize": (
                                parsed_response.strategize.model_dump()
                                if parsed_response.strategize
                                else None
                            ),
                            "action": {
                                "tool": parsed_response.act.tool,
                                "params": parsed_response.act.params,
                            },
                        },
                        success=True,
                    )

                    # Update state from response
                    state.state = parsed_response.state

                    # C. Check for goal achievement
                    if parsed_response.is_finish:
                        completion_reason = parsed_response.act.params.get(
                            "reason", "Goal completed"
                        )
                        turn_duration = int((time.time() - turn_start_time) * 1000)

                        # Save final results
                        final_results_file = self._save_final_results(
                            state, completion_reason
                        )

                        # Create final transcript entry
                        final_transcript_entry = TranscriptEntry(
                            turn=turn_number,
                            reflect=parsed_response.reflect,
                            strategize=parsed_response.strategize,
                            state=parsed_response.state,
                            act=parsed_response.act,
                            observation=f"FINISH: {completion_reason}\nFINAL RESULTS SAVED: {final_results_file}",
                            duration_ms=turn_duration,
                        )
                        state.transcript.append(final_transcript_entry)
                        state.turn_count += 1

                        state.is_complete = True
                        state.completion_reason = completion_reason

                        # Emit completion event
                        await self.event_emitter.emit(
                            execution_id,
                            turn_number,
                            "execution_completed",
                            {
                                "completion_reason": completion_reason,
                                "turns_completed": state.turn_count,
                                "execution_time_ms": int(
                                    (time.time() - start_time) * 1000
                                ),
                            },
                            success=True,
                        )
                        break

                    # D. Act: Execute the action
                    tool_start_time = time.time()

                    # Emit tool started
                    await self.event_emitter.emit(
                        execution_id,
                        turn_number,
                        "tool_started",
                        {
                            "tool_name": parsed_response.act.tool,
                            "tool_version": "1.0.0",
                            "parameters": parsed_response.act.params,
                        },
                    )

                    # Execute tool (run in thread pool)
                    observation = await asyncio.to_thread(
                        self.tool_executor.execute_action,
                        parsed_response.act.model_dump(),
                    )

                    tool_execution_time = int((time.time() - tool_start_time) * 1000)
                    tool_success = not observation.startswith("ERROR")

                    # Emit tool result
                    await self.event_emitter.emit(
                        execution_id,
                        turn_number,
                        "tool_success" if tool_success else "tool_failed",
                        {
                            "tool_name": parsed_response.act.tool,
                            "tool_version": "1.0.0",
                            "parameters": parsed_response.act.params,
                            "execution_time_ms": tool_execution_time,
                            "observation": observation[:500],  # Truncate for event
                            "observation_length": len(observation),
                            "error_message": observation if not tool_success else None,
                        },
                        success=tool_success,
                    )

                    # E. Observe & Update: Add to transcript
                    turn_duration = int((time.time() - turn_start_time) * 1000)
                    transcript_entry = TranscriptEntry(
                        turn=turn_number,
                        reflect=parsed_response.reflect,
                        strategize=parsed_response.strategize,
                        state=parsed_response.state,
                        act=parsed_response.act,
                        observation=observation,
                        duration_ms=turn_duration,
                    )

                    state.transcript.append(transcript_entry)
                    state.turn_count += 1

                    logger.info(f"Turn {state.turn_count} completed: {parsed_response.act.tool}")

                except Exception as e:
                    logger.error(f"Error in turn {turn_number}: {e}")

                    # Emit error
                    await self._emit_error(execution_id, turn_number, str(e))

                    # Add error observation to transcript
                    from reactor.models import (
                        ReflectSection,
                        StrategizeSection,
                        ActSection,
                        Hypothesis,
                    )

                    error_entry = TranscriptEntry(
                        turn=turn_number,
                        reflect=ReflectSection(
                            turn=turn_number,
                            outcome="FAILURE",
                            hypothesisResult="N/A",
                            insight=f"Error: {str(e)}",
                        ),
                        strategize=StrategizeSection(
                            reasoning="Error recovery needed",
                            hypothesis=Hypothesis(claim="N/A", test="N/A", signal="N/A"),
                            ifInvalidated="N/A",
                        ),
                        state=state.state,
                        act=ActSection(tool="error", params={"error": str(e)}),
                        observation=f"ERROR: {str(e)}",
                        duration_ms=int((time.time() - turn_start_time) * 1000),
                    )
                    state.transcript.append(error_entry)
                    state.turn_count += 1

            # Finalize state
            state.end_time = datetime.now()
            success = state.is_complete

            if not success and state.turn_count >= state.max_turns:
                # Emit failure event for max turns reached
                await self.event_emitter.emit(
                    execution_id,
                    state.turn_count,
                    "execution_failed",
                    {
                        "reason": "Max turns reached",
                        "turns_completed": state.turn_count,
                    },
                    success=False,
                )

            execution_summary = self._generate_execution_summary(state)

            logger.info(
                f"Async ReAct execution completed: success={success}, turns={state.turn_count}"
            )

            return ReActResult(
                success=success, state=state, execution_summary=execution_summary
            )

        except Exception as e:
            logger.error(f"Unexpected error during async ReAct execution: {e}")
            await self._emit_error(execution_id, state.turn_count, str(e), traceback.format_exc())
            return self._create_error_result(state, str(e))

    async def _check_for_feedback(self, execution_id: str, turn_number: int):
        """Check for user feedback from event store."""
        if not hasattr(self.event_emitter, 'event_store'):
            return None

        try:
            return await self.event_emitter.event_store.check_feedback(
                execution_id, turn_number
            )
        except Exception as e:
            logger.error(f"Failed to check feedback: {e}")
            return None

    async def _handle_feedback(self, state: ReActState, feedback: dict):
        """Handle user feedback."""
        feedback_type = feedback['feedback_type']
        feedback_data = feedback['feedback_data']

        if feedback_type == 'input':
            # Add user input to state for next turn
            user_input = feedback_data.get('input', '')
            # This would be incorporated into the prompt in the next turn
            if not hasattr(state, 'user_inputs'):
                state.user_inputs = []
            state.user_inputs.append(user_input)

        elif feedback_type == 'approval':
            # Mark action as approved
            if not hasattr(state, 'approved_actions'):
                state.approved_actions = []
            state.approved_actions.append(feedback_data.get('action', ''))

    async def _emit_error(self, execution_id: str, turn_number: int, error_msg: str, traceback_str: str = None):
        """Helper to emit error events."""
        await self.event_emitter.emit(
            execution_id,
            turn_number,
            "execution_failed",
            {
                "error": error_msg,
                "traceback": traceback_str or traceback.format_exc(),
            },
            success=False,
        )
