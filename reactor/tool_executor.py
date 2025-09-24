# reactor/tool_executor.py

import sys
import os
import time
from typing import Dict, Any, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import UFDescriptor, ToolResult
from core.logging_config import get_logger
from registry.main import Registry
from executor.main import execute_tool

# Initialize logging
logger = get_logger('reactor.tool_executor')

class ReActToolExecutor:
    """Executes tools for ReAct agent with simplified interface."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self._last_full_stdout = None  # Store full stdout for final result extraction

    def execute_action(self, action: Dict[str, Any]) -> str:
        """
        Execute a single action and return formatted observation.

        Args:
            action: Dict with 'tool_name' and 'parameters' keys

        Returns:
            Formatted observation string for scratchpad
        """
        start_time = time.time()

        try:
            tool_name = action.get("tool_name")
            parameters = action.get("parameters", {})

            logger.info(f"Executing action: {tool_name} with params: {parameters}")

            # Python environment setup now handled at agent startup

            # Display command line for shell commands to provide transparency
            if tool_name in ["execute_shell"]:
                command_to_show = None
                if tool_name == "execute_shell" and "command" in parameters:
                    command_to_show = parameters["command"]

                if command_to_show:
                    print(f"💻 Command: {command_to_show}")

            # Handle finish action
            if tool_name == "finish":
                reason = action.get("reason", "Goal completed")
                return f"FINISH: {reason}"

            # Get tool from registry
            uf_descriptor = self._resolve_tool(tool_name)
            if not uf_descriptor:
                available_tools = [f"{desc.name}:{desc.version}" for desc in self.registry.list_ufs()]
                return f"ERROR: Tool '{tool_name}' not found. Available tools: {', '.join(available_tools)}"

            # Execute tool using existing infrastructure
            result = execute_tool(uf_descriptor, parameters)

            # Format observation
            observation = self._format_observation(tool_name, result)

            duration = time.time() - start_time
            logger.info(f"Tool execution completed in {duration:.2f}s with status: {result.status}")

            return observation

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Tool execution failed after {duration:.2f}s: {e}")
            return f"ERROR: Tool execution failed - {str(e)}"

    def _resolve_tool(self, tool_name: str) -> Optional[UFDescriptor]:
        """Resolve tool name to UFDescriptor."""
        try:
            # Handle versioned tool names (e.g., "read_file:1.0.0")
            if ':' in tool_name:
                name, version = tool_name.split(':', 1)
                return self.registry.get_uf(name, version)
            else:
                # Try to find any version of the tool
                available_tools = self.registry.list_ufs()
                for tool in available_tools:
                    if tool.name == tool_name:
                        return tool
                return None

        except Exception as e:
            logger.error(f"Error resolving tool '{tool_name}': {e}")
            return None

    def _format_observation(self, tool_name: str, result: ToolResult) -> str:
        """Format tool result into observation string with enhanced feedback."""

        if result.status == "failure":
            error_msg = result.error or 'Unknown error'
            
            # Provide enhanced feedback for different error types
            if "Missing required fields" in error_msg:
                # Add specific guidance for missing parameter errors
                error_msg += "\n\nGUIDANCE: When calling a tool, you must provide all required parameters in the 'parameters' object. Review the tool's schema and provide the missing fields."
            elif tool_name == "execute_shell" and "truncated" in error_msg.lower():
                error_msg += "\nSUGGESTION: Output was truncated. Try breaking the command into smaller parts or save results to files."
            
            return f"ERROR ({tool_name}): {error_msg}"

        # Format successful result
        observation_parts = [f"SUCCESS ({tool_name}):"]

        # Add output information
        if result.output is not None:
            # Handle different output types
            if isinstance(result.output, dict):
                # For structured output, format key information
                key_info = []
                for key, value in result.output.items():
                    if key == "stdout" and isinstance(value, str):
                        # Store full stdout for final result extraction
                        self._last_full_stdout = value

                        # Special handling for shell command stdout
                        # Check if this output contains React UI elements that should not be trimmed
                        react_ui_elements = ["**New Facts:**", "**Hypothesis:**", "**Progress Check:**", "**Thought:**", "**Executing Action:**", "**Observation:**"]
                        has_react_elements = any(element in value for element in react_ui_elements)

                        if has_react_elements:
                            # Don't truncate if it contains React UI elements
                            key_info.append(f"{key}: {value}")
                        else:
                            lines = value.count('\n')
                            if lines > 100:  # Very many lines - show sample
                                key_info.append(f"{key}: {lines+1} lines of output")
                                # Show first few lines as sample
                                first_lines = '\n'.join(value.split('\n')[:5])
                                key_info.append(f"Sample: {first_lines}...")
                            elif lines > 30:  # Many lines - show more but still truncate
                                key_info.append(f"{key}: {lines+1} lines of output")
                                # Show first 15 lines for meaningful results
                                first_lines = '\n'.join(value.split('\n')[:15])
                                key_info.append(f"First 15 lines: {first_lines}...")
                                if lines <= 60:  # Also show last few lines if not too many
                                    last_lines = '\n'.join(value.split('\n')[-3:])
                                    key_info.append(f"Last 3 lines: ...{last_lines}")
                            elif len(value) > 1000:  # Long output
                                key_info.append(f"{key}: {value[:500]}... (truncated - {len(value)} chars total)")
                            else:
                                key_info.append(f"{key}: {value}")
                    elif isinstance(value, str) and len(value) > 200:
                        # Check if this value contains React UI elements that should not be trimmed
                        react_ui_elements = ["**New Facts:**", "**Hypothesis:**", "**Progress Check:**", "**Thought:**", "**Executing Action:**", "**Observation:**"]
                        has_react_elements = any(element in value for element in react_ui_elements)

                        if has_react_elements:
                            key_info.append(f"{key}: {value}")
                        else:
                            key_info.append(f"{key}: {value[:200]}... (truncated)")
                    else:
                        key_info.append(f"{key}: {value}")
                observation_parts.append(" | ".join(key_info))
            elif isinstance(result.output, str):
                # Check if this output contains React UI elements that should not be trimmed
                react_ui_elements = ["**New Facts:**", "**Hypothesis:**", "**Progress Check:**", "**Thought:**", "**Executing Action:**", "**Observation:**"]
                has_react_elements = any(element in result.output for element in react_ui_elements)

                if has_react_elements:
                    # Don't truncate if it contains React UI elements
                    observation_parts.append(result.output)
                else:
                    # For string output, provide better truncation feedback
                    lines = result.output.count('\n')
                    if len(result.output) > 2000:
                        observation_parts.append(f"{result.output[:1000]}... (showing first 1000 chars of {len(result.output)} total, {lines+1} lines)")
                    elif lines > 20:
                        first_lines = '\n'.join(result.output.split('\n')[:10])
                        observation_parts.append(f"{first_lines}... (showing first 10 lines of {lines+1} total)")
                    else:
                        observation_parts.append(result.output)
            else:
                observation_parts.append(str(result.output))

        # Add execution metadata with enhanced context
        metadata_parts = []
        if result.duration_ms:
            metadata_parts.append(f"{result.duration_ms}ms")
        if result.cost:
            metadata_parts.append(f"${result.cost:.4f}")

        # Add return code for shell commands
        if tool_name == "execute_shell" and isinstance(result.output, dict):
            return_code = result.output.get("return_code")
            success = result.output.get("success")
            if return_code is not None:
                metadata_parts.append(f"return_code: {return_code}")
            if success is not None:
                metadata_parts.append(f"success: {success}")

        if metadata_parts:
            observation_parts.append(f"({', '.join(metadata_parts)})")

        # Add guidance for analysis tasks with truncation warnings
        if tool_name == "execute_shell" and result.status == "success":
            stdout = result.output.get("stdout", "") if isinstance(result.output, dict) else ""

            # Warn about truncated data being used in create_file
            if stdout and len(stdout) > 2000:
                observation_parts.append("\n⚠️  LARGE OUTPUT DETECTED: Use shell redirection (> filename.txt) instead of create_file to avoid data loss")

            if stdout and ("ERROR" in stdout or "error" in stdout):
                if len(stdout) > 1000:
                    observation_parts.append("\n📋 OUTPUT CONTAINS ERRORS: Use '> error_results.txt' to save complete findings, don't copy truncated data")
                else:
                    observation_parts.append("\n📋 OUTPUT CONTAINS ERRORS: Consider saving complete results for correlation analysis")

        return " ".join(observation_parts)

    def get_last_full_stdout(self) -> Optional[str]:
        """Get the full stdout from the last executed tool (for final result extraction)."""
        return self._last_full_stdout

    def get_available_tools_summary(self) -> str:
        """Get a summary of available tools for error messages."""
        tools = self.registry.list_ufs()
        tool_names = [f"{tool.name}:{tool.version}" for tool in tools]
        return f"Available tools: {', '.join(tool_names)}"

