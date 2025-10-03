# reactor/tool_executor.py

import sys
import os
import time
import tempfile
from typing import Dict, Any, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import UFDescriptor, ToolResult, ObservationSummary
from core.logging_config import get_logger
from registry.main import Registry
from executor.main import execute_tool

# Initialize logging
logger = get_logger('reactor.tool_executor')

# Configuration for large output detection
LARGE_OUTPUT_LINE_THRESHOLD = 50
LARGE_OUTPUT_CHAR_THRESHOLD = 2000

class ReActToolExecutor:
    """Executes tools for ReAct agent with simplified interface."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self._last_full_stdout = None  # Store full stdout for final result extraction
        self._temp_dir = tempfile.mkdtemp(prefix="ufflow_observations_")
        logger.info(f"Initialized observation temp directory: {self._temp_dir}")

    def execute_action(self, action: Dict[str, Any]) -> str:
        """
        Execute a single action and return formatted observation.

        Args:
            action: Dict with 'tool' and 'params' keys (new format)
                   or 'tool_name' and 'parameters' keys (old format)

        Returns:
            Formatted observation string for transcript
        """
        start_time = time.time()

        try:
            # Support both old and new format
            tool_name = action.get("tool") or action.get("tool_name")
            parameters = action.get("params") or action.get("parameters", {})

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
                reason = parameters.get("reason", "Goal completed")
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

    def _is_large_output(self, output: str) -> bool:
        """Determine if output qualifies as 'large' and needs funnel processing."""
        lines = output.count('\n') + 1
        chars = len(output)
        return lines > LARGE_OUTPUT_LINE_THRESHOLD or chars > LARGE_OUTPUT_CHAR_THRESHOLD

    def _save_large_output_to_file(self, output: str, tool_name: str) -> str:
        """Save large output to temporary file and return path."""
        import hashlib
        from datetime import datetime

        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_hash = hashlib.md5(output.encode()).hexdigest()[:8]
        filename = f"{tool_name}_{timestamp}_{output_hash}.txt"
        filepath = os.path.join(self._temp_dir, filename)

        # Write to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output)

        logger.info(f"Saved large output ({len(output)} chars) to {filepath}")
        return filepath

    def _create_observation_summary(self, output: str, tool_name: str, saved_path: Optional[str] = None) -> ObservationSummary:
        """Layer 1: Create metadata summary for large output."""
        lines = output.count('\n') + 1
        chars = len(output)

        summary = ObservationSummary(
            total_lines=lines,
            total_chars=chars,
            status_flag="success",
            full_output_saved_to=saved_path,
            metadata={"tool": tool_name}
        )

        # Add tool-specific metrics
        if tool_name in ["content_search", "sourcegraph_search"]:
            # Try to extract match count from JSON output
            try:
                import json
                data = json.loads(output)
                if isinstance(data, list):
                    summary.total_matches = len(data)
                    # Count unique files
                    files = set()
                    for item in data:
                        if isinstance(item, dict) and 'file' in item:
                            files.add(item['file'])
                    summary.files_with_matches = len(files)
            except:
                pass

        return summary

    def _smart_truncate(self, output: str, tool_name: str) -> str:
        """Layer 2: Smart truncation (the 'trailer') - show head, indicator, tail."""
        lines = output.split('\n')
        total_lines = len(lines)

        if total_lines <= LARGE_OUTPUT_LINE_THRESHOLD and len(output) <= LARGE_OUTPUT_CHAR_THRESHOLD:
            return output

        # Show first 10 lines (head)
        head_lines = lines[:10]
        # Show last 5 lines (tail)
        tail_lines = lines[-5:] if total_lines > 15 else []

        # Build truncated preview
        preview_parts = []
        preview_parts.extend(head_lines)

        if tail_lines:
            truncated_count = total_lines - len(head_lines) - len(tail_lines)
            preview_parts.append(f"\n... [{truncated_count} lines truncated] ...\n")
            preview_parts.extend(tail_lines)
        else:
            truncated_count = total_lines - len(head_lines)
            preview_parts.append(f"\n... [{truncated_count} lines truncated] ...")

        return '\n'.join(preview_parts)

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
        """Format tool result into observation string using 3-layer funnel."""

        if result.status == "failure":
            error_msg = result.error or 'Unknown error'

            # Provide enhanced feedback for different error types
            if "Missing required fields" in error_msg:
                error_msg += "\n\nGUIDANCE: When calling a tool, you must provide all required parameters in the 'parameters' object. Review the tool's schema and provide the missing fields."
            elif tool_name == "execute_shell" and "truncated" in error_msg.lower():
                error_msg += "\nSUGGESTION: Output was truncated. Try breaking the command into smaller parts or save results to files."

            return f"ERROR ({tool_name}): {error_msg}"

        # ====================================================================
        # THE 3-LAYER OBSERVATION FUNNEL
        # ====================================================================

        observation_parts = [f"SUCCESS ({tool_name}):"]

        # Add output information using the 3-layer funnel
        if result.output is not None:
            # Handle different output types
            if isinstance(result.output, dict):
                # For structured output (usually from execute_shell)
                key_info = []
                for key, value in result.output.items():
                    if key == "stdout" and isinstance(value, str):
                        # Store full stdout for final result extraction
                        self._last_full_stdout = value

                        # Apply the funnel for large stdout
                        if self._is_large_output(value):
                            # LAYER 1: Save to file
                            saved_path = self._save_large_output_to_file(value, tool_name)
                            # LAYER 1: Create summary
                            summary = self._create_observation_summary(value, tool_name, saved_path)
                            # LAYER 2: Create smart preview
                            preview = self._smart_truncate(value, tool_name)

                            # Format the funneled observation
                            key_info.append(f"📊 LARGE OUTPUT DETECTED:")
                            key_info.append(f"  - Total: {summary.total_lines} lines, {summary.total_chars} chars")
                            key_info.append(f"  - Full output saved to: {summary.full_output_saved_to}")
                            key_info.append(f"  - Preview (head/tail):\n{preview}")
                        else:
                            # Small output - show directly
                            key_info.append(f"{key}: {value}")
                    elif isinstance(value, str) and len(value) > 200:
                        key_info.append(f"{key}: {value[:200]}... (truncated)")
                    else:
                        key_info.append(f"{key}: {value}")
                observation_parts.append("\n".join(key_info))

            elif isinstance(result.output, str):
                # For string output (search results, file contents, etc.)
                if self._is_large_output(result.output):
                    # LAYER 1: Save to file
                    saved_path = self._save_large_output_to_file(result.output, tool_name)
                    # LAYER 1: Create summary
                    summary = self._create_observation_summary(result.output, tool_name, saved_path)
                    # LAYER 2: Create smart preview
                    preview = self._smart_truncate(result.output, tool_name)

                    # Format the funneled observation
                    funnel_info = [
                        "📊 LARGE OUTPUT DETECTED:",
                        f"  - Total: {summary.total_lines} lines, {summary.total_chars} chars"
                    ]
                    if summary.total_matches:
                        funnel_info.append(f"  - Matches: {summary.total_matches} results")
                    if summary.files_with_matches:
                        funnel_info.append(f"  - Files: {summary.files_with_matches} files")
                    funnel_info.extend([
                        f"  - Full output saved to: {summary.full_output_saved_to}",
                        f"  - Preview (head/tail):\n{preview}"
                    ])
                    observation_parts.append("\n".join(funnel_info))
                else:
                    # Small output - show directly
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

        return "\n".join(observation_parts)

    def get_last_full_stdout(self) -> Optional[str]:
        """Get the full stdout from the last executed tool (for final result extraction)."""
        return self._last_full_stdout

    def get_available_tools_summary(self) -> str:
        """Get a summary of available tools for error messages."""
        tools = self.registry.list_ufs()
        tool_names = [f"{tool.name}:{tool.version}" for tool in tools]
        return f"Available tools: {', '.join(tool_names)}"

