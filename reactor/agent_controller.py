# reactor/agent_controller.py

import sys
import os
import json
import time
import re
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, ValidationError, validator
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import get_logger, UFFlowLogger
from core.config import config
from registry.main import Registry
from core.llm import OpenAIClientManager
from reactor.models import ReActState, ReActResult, ScratchpadEntry, ParsedLLMResponse
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

    @validator('tool_name')
    def validate_tool_name(cls, v):
        if not v or not v.strip():
            raise ValueError("tool_name cannot be empty")
        return v.strip()

class LLMResponseSchema(BaseModel):
    """Schema for complete LLM response."""
    thought: str = Field(..., description="The reasoning thought")
    action: ActionSchema = Field(..., description="The action to take")

    @validator('thought')
    def validate_thought(cls, v):
        if not v or not v.strip():
            raise ValueError("thought cannot be empty")
        return v.strip()

class AgentController:
    """
    The main ReAct agent controller that manages the reasoning-action-observation loop.
    """

    def __init__(self, registry: Registry):
        self.registry = registry
        self.llm_client = OpenAIClientManager()
        self.tool_executor = ReActToolExecutor(registry)
        self.prompt_builder = ReActPromptBuilder()

    def execute_goal(self, goal: str, max_turns: Optional[int] = None) -> ReActResult:
        """
        Execute a goal using the ReAct framework.

        Args:
            goal: High-level user objective
            max_turns: Maximum number of turns to prevent infinite loops

        Returns:
            ReActResult with success status and final state
        """
        start_time = time.time()

        UFFlowLogger.log_execution_start(
            "reactor",
            "execute_goal",
            goal=goal,
            max_turns=max_turns
        )

        # Initialize state
        if max_turns is None:
            max_turns = config.get_max_turns()
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

            # Main ReAct loop
            while state.turn_count < state.max_turns and not state.is_complete:
                turn_start_time = time.time()

                try:
                    logger.info(f"Starting turn {state.turn_count + 1}/{state.max_turns}")

                    # A. Reason: Build prompt and get LLM response
                    messages = self.prompt_builder.build_messages_for_openai(state, available_tools)
                    raw_response = self.llm_client.create_completion_text(messages)

                    # B. Reason: Parse the response
                    parsed_response = self._parse_llm_response(raw_response)

                    # C. Check for goal achievement
                    if parsed_response.is_finish:
                        logger.info("Agent indicated goal completion")

                        # Perform completeness verification for analysis tasks
                        completion_reason = parsed_response.action.get("reason", "Goal completed")
                        verification_result = self._verify_goal_completeness(state, completion_reason)

                        # Add the final reasoning turn to scratchpad
                        turn_duration = int((time.time() - turn_start_time) * 1000)

                        if verification_result['is_complete']:
                            # Save final results to file before finishing
                            final_results_file = self._save_final_results(state, completion_reason)

                            final_scratchpad_entry = ScratchpadEntry(
                                turn=state.turn_count + 1,
                                thought=parsed_response.thought,
                                intent=parsed_response.intent,
                                action=parsed_response.action,
                                observation=f"FINISH: {completion_reason}\nVERIFICATION: {verification_result['message']}\nFINAL RESULTS SAVED: {final_results_file}",
                                duration_ms=turn_duration
                            )
                            state.scratchpad.append(final_scratchpad_entry)
                            state.turn_count += 1

                            state.is_complete = True
                            state.completion_reason = completion_reason
                            break
                        else:
                            # Goal not actually complete - continue with verification feedback
                            incomplete_entry = ScratchpadEntry(
                                turn=state.turn_count + 1,
                                thought=parsed_response.thought,
                                intent=parsed_response.intent,
                                action=parsed_response.action,
                                observation=f"INCOMPLETE GOAL: {verification_result['message']}\nContinue working to complete all requirements.",
                                duration_ms=turn_duration
                            )
                            state.scratchpad.append(incomplete_entry)
                            state.turn_count += 1
                            logger.warning(f"Goal completion rejected: {verification_result['message']}")
                            continue

                    # D. Act: Execute the action
                    observation = self.tool_executor.execute_action(parsed_response.action)

                    # E. Observe & Update: Add to scratchpad
                    turn_duration = int((time.time() - turn_start_time) * 1000)
                    scratchpad_entry = ScratchpadEntry(
                        turn=state.turn_count + 1,
                        thought=parsed_response.thought,
                        intent=parsed_response.intent,
                        action=parsed_response.action,
                        observation=observation,
                        duration_ms=turn_duration
                    )

                    state.scratchpad.append(scratchpad_entry)
                    state.turn_count += 1

                    logger.info(f"Turn {state.turn_count} completed: {parsed_response.action.get('tool_name', 'unknown')}")

                except Exception as e:
                    logger.error(f"Error in turn {state.turn_count + 1}: {e}")

                    # Add error observation to scratchpad
                    error_entry = ScratchpadEntry(
                        turn=state.turn_count + 1,
                        thought="Error occurred during execution",
                        intent=None,
                        action={"tool_name": "error", "error": str(e)},
                        observation=f"ERROR: {str(e)}",
                        duration_ms=int((time.time() - turn_start_time) * 1000)
                    )
                    state.scratchpad.append(error_entry)
                    state.turn_count += 1

            # Finalize state
            state.end_time = datetime.now()

            # Determine success
            success = state.is_complete
            execution_summary = self._generate_execution_summary(state)

            duration = time.time() - start_time

            UFFlowLogger.log_execution_end(
                "reactor",
                "execute_goal",
                success,
                duration_ms=int(duration * 1000),
                turns_taken=state.turn_count,
                goal_achieved=state.is_complete
            )

            logger.info(f"ReAct execution completed: success={success}, turns={state.turn_count}")

            return ReActResult(
                success=success,
                state=state,
                execution_summary=execution_summary
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Unexpected error during ReAct execution: {e}"
            logger.error(error_msg)

            UFFlowLogger.log_execution_end(
                "reactor",
                "execute_goal",
                False,
                duration_ms=int(duration * 1000),
                error_type="unexpected",
                error_message=str(e)
            )

            return self._create_error_result(state, error_msg)

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
            for i, entry in enumerate(state.scratchpad):
                results_content.extend([
                    f"--- TURN {entry.turn} ---",
                    f"Thought: {entry.thought}",
                    f"Action: {entry.action}",
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
        recent_turns = state.scratchpad[-3:] if len(state.scratchpad) >= 3 else state.scratchpad

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
                            f"From Turn {entry.turn} ({entry.action.get('tool_name', 'unknown')}):",
                            stdout_content,
                            ""
                        ])

        return outputs

    def _parse_llm_response(self, raw_response: str) -> ParsedLLMResponse:
        """Parse LLM response using robust schema-based approach."""
        try:
            logger.debug(f"Parsing LLM response: {raw_response[:200]}...")

            # Extract thought, intent, and action using multiple strategies
            parsed_data = self._extract_thought_intent_and_action(raw_response)

            if not parsed_data:
                raise ValueError("Could not extract thought and action from response")

            # Use Pydantic schema for robust validation and parsing
            try:
                validated_response = LLMResponseSchema(**parsed_data)

                # Check if this is a finish action
                is_finish = validated_response.action.tool_name == "finish"

                return ParsedLLMResponse(
                    thought=validated_response.thought,
                    intent=parsed_data.get("intent"),
                    action=validated_response.action.dict(),
                    is_finish=is_finish,
                    raw_response=raw_response
                )

            except ValidationError as e:
                logger.warning(f"Schema validation failed: {e}")
                # Try fallback parsing
                return self._fallback_parse(raw_response, parsed_data)

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Full raw response: {raw_response}")

            # Return a default response that will create an error observation
            return ParsedLLMResponse(
                thought="Failed to parse response",
                intent=None,
                action={"tool_name": "error", "error": f"Parse error: {e}"},
                is_finish=False,
                raw_response=raw_response
            )

    def _generate_execution_summary(self, state: ReActState) -> str:
        """Generate human-readable execution summary."""
        if state.is_complete:
            summary = f"✅ Goal achieved in {state.turn_count} turns"
            if state.completion_reason:
                summary += f": {state.completion_reason}"
        elif state.turn_count >= state.max_turns:
            summary = f"⏰ Reached maximum turns ({state.max_turns}) without completing goal"
        else:
            summary = f"❌ Execution stopped after {state.turn_count} turns"

        # Add turn breakdown
        if state.scratchpad:
            actions_taken = [entry.action.get('tool_name', 'unknown') for entry in state.scratchpad]
            unique_actions = list(set(actions_taken))
            summary += f"\nActions used: {', '.join(unique_actions)}"

        return summary

    def _verify_goal_completeness(self, state: ReActState, completion_reason: str) -> Dict[str, Any]:
        """
        Verify if the goal is truly complete based on the execution history.
        This helps prevent premature completion of complex analysis tasks.
        """
        goal = state.goal.lower()
        completion_reason = completion_reason.lower()

        # Check if this is a search/analysis goal
        analysis_keywords = ["search", "find", "analyze", "correlate", "map", "identify", "extract", "discover"]
        is_analysis_goal = any(keyword in goal for keyword in analysis_keywords)

        if not is_analysis_goal:
            # For non-analysis goals, trust the agent's completion decision
            return {"is_complete": True, "message": "Goal completion accepted"}

        # For analysis goals, perform stricter verification
        issues = []

        # Check if comprehensive search was performed
        shell_actions = [entry for entry in state.scratchpad if entry.action.get("tool_name") == "execute_shell"]
        file_actions = [entry for entry in state.scratchpad if entry.action.get("tool_name") in ["create_file", "read_file"]]

        # Verify discovery phase
        find_commands = [entry for entry in shell_actions if "find" in str(entry.action.get("parameters", {})).lower()]
        if not find_commands and "find" in goal:
            issues.append("No discovery phase detected - missing 'find' commands to locate all relevant files")

        # Verify extraction phase for error analysis
        if "error" in goal and "log" in goal:
            grep_commands = [entry for entry in shell_actions if "grep" in str(entry.action.get("parameters", {})).lower()]
            if not grep_commands:
                issues.append("No extraction phase detected - missing 'grep' commands to extract error patterns")
            else:
                # Check if grep included line numbers and context
                has_line_numbers = any("-n" in str(entry.action.get("parameters", {})) or "-H" in str(entry.action.get("parameters", {})) for entry in grep_commands)
                if not has_line_numbers:
                    issues.append("Grep commands should include line numbers (-n or -H) for proper correlation")

        # Verify correlation phase
        if "correlate" in goal or "map" in goal or ("source" in goal and "code" in goal):
            py_searches = [entry for entry in shell_actions if "*.py" in str(entry.action.get("parameters", {})) or "python" in str(entry.action.get("parameters", {})).lower()]
            if not py_searches:
                issues.append("No correlation phase detected - missing source code searches in Python files")

        # Verify results were saved for analysis
        if len(shell_actions) > 3 and not file_actions:  # If complex analysis but no file operations
            issues.append("Complex analysis should save intermediate results to files for verification")

        # Check for shell redirection usage (proper way to handle large outputs)
        redirect_commands = [entry for entry in shell_actions if ">" in str(entry.action.get("parameters", {}))]
        large_output_commands = [entry for entry in shell_actions if "grep" in str(entry.action.get("parameters", {})).lower() or "find" in str(entry.action.get("parameters", {})).lower()]

        if len(large_output_commands) >= 2 and len(redirect_commands) == 0:
            issues.append("Large search outputs should use shell redirection (> filename.txt) to avoid truncation")

        # Check if completion reason demonstrates understanding
        superficial_reasons = ["done", "complete", "finished", "found errors", "searched files"]
        if any(reason in completion_reason for reason in superficial_reasons) and len(completion_reason) < 50:
            issues.append("Completion reason is too brief - should demonstrate comprehensive understanding of findings")

        # Determine completeness
        if issues:
            return {
                "is_complete": False,
                "message": f"Goal verification failed: {'; '.join(issues)}"
            }
        else:
            return {
                "is_complete": True,
                "message": "Goal completion verified - all analysis phases detected"
            }

    def _extract_thought_intent_and_action(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """Extract thought, intent, and action from raw response using multiple strategies."""
        # Strategy 1: Standard regex extraction with intent support
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

        return result

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

                return ParsedLLMResponse(
                    thought=parsed_data.get("thought", "Unable to extract thought"),
                    intent=parsed_data.get("intent"),
                    action=action,
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

    def _create_error_result(self, state: ReActState, error_message: str) -> ReActResult:
        """Create error result for failed executions."""
        state.end_time = datetime.now()
        return ReActResult(
            success=False,
            state=state,
            error_message=error_message,
            execution_summary=f"❌ Execution failed: {error_message}"
        )