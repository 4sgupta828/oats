# reactor/prompt_builder.py

import sys
import os
import platform
import subprocess
import logging
# Use tiktoken for accurate token counting with OpenAI models (optional)
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken not available. Token counting will use approximation.")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Tuple
from core.models import UFDescriptor
from reactor.models import ReActState, ScratchpadEntry
from core.workspace_security import get_workspace_security

logger = logging.getLogger(__name__)

class ReActPromptBuilder:
    """Builds prompts for the ReAct agent using scratchpad history."""

    def __init__(self):
        self.system_context = self._get_system_context()
        self.system_prompt = self._build_system_prompt()
        # Initialize tokenizer for accurate context management
        if TIKTOKEN_AVAILABLE:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        else:
            self.tokenizer = None
        self.max_tokens_per_turn = 4000  # Hard limit
        self.warning_threshold = 3000    # Warning threshold

    def _count_tokens(self, text: str) -> int:
        """Count tokens accurately using the tiktoken library."""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Approximate token count: ~4 characters per token
            return len(text) // 4

    def _enforce_context_limits(self, scratchpad: List[ScratchpadEntry], prompt_base: str) -> Tuple[List[ScratchpadEntry], bool]:
        """Enforce token limits using progressive thinning strategy.

        Strategy:
        1. First try: Make observations more aggressive (remove middle/end samples)
        2. Second try: Make observations minimal (start/end only)
        3. Last resort: Remove oldest turns entirely

        Returns:
            Tuple of (filtered_scratchpad, warning_triggered)
        """
        base_tokens = self._count_tokens(prompt_base)
        warning_triggered = False

        # Try progressive thinning levels
        for aggression_level in range(3):  # 0=normal, 1=aggressive, 2=minimal
            current_scratchpad = scratchpad.copy()

            # Test this aggression level
            history_text = self._format_scratchpad_history_with_aggression(current_scratchpad, aggression_level)
            total_tokens = base_tokens + self._count_tokens(history_text)

            if total_tokens <= self.max_tokens_per_turn:
                if total_tokens > self.warning_threshold and not warning_triggered:
                    logger.warning(f"Context approaching limit: {total_tokens}/{self.max_tokens_per_turn} tokens")
                    warning_triggered = True
                if aggression_level > 0:
                    logger.info(f"Applied aggression level {aggression_level} to fit context")
                    warning_triggered = True
                # Store the aggression level for the final formatting
                return self._apply_aggression_to_scratchpad(current_scratchpad, aggression_level), warning_triggered

            if aggression_level == 2:  # If even minimal didn't work, remove old turns
                logger.warning(f"Even minimal truncation exceeded limit ({total_tokens} tokens), removing old turns")

        # Last resort: Remove oldest entries with minimal truncation
        current_scratchpad = scratchpad.copy()
        aggression_level = 2  # Use minimal truncation while removing turns

        while current_scratchpad:
            history_text = self._format_scratchpad_history_with_aggression(current_scratchpad, aggression_level)
            total_tokens = base_tokens + self._count_tokens(history_text)

            if total_tokens <= self.max_tokens_per_turn:
                logger.warning(f"Context management: using {len(current_scratchpad)}/{len(scratchpad)} turns with minimal truncation")
                break

            current_scratchpad.pop(0)  # Remove oldest turn
            warning_triggered = True

        return self._apply_aggression_to_scratchpad(current_scratchpad, aggression_level), warning_triggered

    def _format_scratchpad_history_with_aggression(self, scratchpad: List[ScratchpadEntry], aggression_level: int) -> str:
        """Format scratchpad with specific aggression level for testing."""
        history_parts = []

        for entry in scratchpad:
            history_parts.append(f"Turn {entry.turn}:")
            history_parts.append(f"Thought: {entry.thought}")
            if entry.intent:
                history_parts.append(f"Intent: {entry.intent}")
            history_parts.append(f"Action: {entry.action}")
            truncated_obs = self._truncate_observation(entry.observation, aggression_level)
            history_parts.append(f"Observation: {truncated_obs}")
            history_parts.append("")  # Empty line between turns

        return "\n".join(history_parts)

    def _apply_aggression_to_scratchpad(self, scratchpad: List[ScratchpadEntry], aggression_level: int) -> List[ScratchpadEntry]:
        """Apply truncation aggression level to scratchpad entries."""
        if aggression_level == 0:
            return scratchpad  # No change needed for normal level

        # Create new entries with truncated observations
        thinned_scratchpad = []
        for entry in scratchpad:
            new_entry = entry.model_copy()
            new_entry.observation = self._truncate_observation(entry.observation, aggression_level)
            thinned_scratchpad.append(new_entry)

        return thinned_scratchpad

    def _truncate_observation(self, observation: str, aggression_level: int = 0) -> str:
        """Truncate large observations with progressive aggression levels.

        Args:
            observation: The original observation text
            aggression_level: 0=normal, 1=aggressive, 2=minimal

        Returns:
            Truncated observation with sampling based on aggression level
        """
        if not observation or not observation.strip():
            return observation

        lines = observation.split('\n')

        # Progressive settings based on aggression level
        if aggression_level == 0:  # Normal truncation
            max_lines, sample_lines, max_line_length = 20, 3, 100
        elif aggression_level == 1:  # Aggressive truncation
            max_lines, sample_lines, max_line_length = 10, 2, 80
        else:  # Minimal truncation (level 2+)
            max_lines, sample_lines, max_line_length = 6, 1, 60

        # Truncate individual lines first
        lines = [line[:max_line_length] + ('...' if len(line) > max_line_length else '') for line in lines]

        # If short enough, return as-is
        if len(lines) <= max_lines:
            return '\n'.join(lines)

        # For aggressive levels, only show start/end (no middle)
        if aggression_level >= 2:
            truncated = []
            truncated.extend(lines[:sample_lines])
            truncated.append(f'... [{len(lines) - 2*sample_lines} lines omitted] ...')
            truncated.extend(lines[-sample_lines:])
            return '\n'.join(truncated)

        # Normal/aggressive: Sample from start, middle, end
        start_lines = lines[:sample_lines]
        middle_idx = len(lines) // 2
        middle_lines = lines[middle_idx-sample_lines//2:middle_idx+sample_lines//2+1]
        end_lines = lines[-sample_lines:]

        # Build truncated version
        truncated = []
        truncated.extend(start_lines)
        if aggression_level == 0:  # Only include middle for normal level
            truncated.append(f'... [{len(lines) - 2*sample_lines - len(middle_lines)} lines omitted] ...')
            truncated.extend(middle_lines)
        if middle_lines != end_lines or aggression_level >= 1:
            truncated.append(f'... [showing last {sample_lines} lines] ...')
            truncated.extend(end_lines)

        return '\n'.join(truncated)

    def _get_system_context(self) -> Dict[str, str]:
        """Get system context information for better command generation."""
        context = {
            'os': platform.system(),
            'os_version': platform.version(),
            'python_version': platform.python_version(),
        }

        # Detect shell capabilities
        if context['os'] == 'Darwin':  # macOS
            context['shell_notes'] = 'macOS grep does not support -P (Perl regex). Use basic regex or sed/awk instead.'
            context['grep_features'] = 'Supports: -E (extended regex), -n (line numbers), -H (filenames). No -P support.'
        elif context['os'] == 'Linux':
            context['shell_notes'] = 'GNU tools available with full feature sets.'
            context['grep_features'] = 'Supports: -P (Perl regex), -E (extended regex), -n, -H and all GNU features.'
        else:
            context['shell_notes'] = 'Windows environment - use PowerShell compatible commands.'
            context['grep_features'] = 'Limited grep. Consider using select-string in PowerShell.'

        return context

    def _get_system_specific_commands(self) -> str:
        """Get system-specific command examples."""
        if self.system_context['os'] == 'Darwin':  # macOS
            return """macOS Command Examples:
• Regex search: grep -E "pattern1|pattern2" file.txt
• Exception search: grep -Hn "raise " *.py
• Case-insensitive: grep -i "error" *.log
• Multi-file with filenames: find . -name "*.py" -exec grep -Hn "raise " {} \\;
• Count matches: grep -c "pattern" file.txt
• Context lines: grep -A3 -B3 "pattern" file.txt
• AVOID: grep -P (not supported on macOS)"""
        elif self.system_context['os'] == 'Linux':
            return """Linux Command Examples:
• Perl regex: grep -P "(?<=raise )\\w+" file.txt
• Extended regex: grep -E "pattern1|pattern2" file.txt
• All GNU features available
• Use -P for advanced regex patterns"""
        else:
            return """Windows Command Examples:
• Use PowerShell select-string instead of grep
• Example: select-string "pattern" -path "*.txt"
• For complex tasks, prefer Python scripts"""

    def _build_system_prompt(self) -> str:
        """Build the core system prompt with ReAct instructions."""
        canonical_intents = [
            "lint_code", "format_code", "run_tests", "install_dependencies",
            "parse_structured_data", "check_for_secrets", "search_codebase",
            "read_file", "write_file", "list_files", "provision_tool", "check_tool_availability",
            "ask_user", "confirm_with_user"
        ]

        return f"""You are an autonomous AI agent that accomplishes complex goals by reasoning step-by-step and using available tools.

SYSTEM CONTEXT:
• Operating System: {self.system_context['os']}
• Shell Limitations: {self.system_context['shell_notes']}
• Grep Capabilities: {self.system_context['grep_features']}
• Python Version: {self.system_context['python_version']}

## INTENT-DRIVEN WORKFLOW

Your response MUST follow this three-part format exactly:

Thought: [Reason about your goal and formulate a plan for the immediate next action.]
Intent: [Classify your plan into a single intent from the CANONICAL INTENTS LIST below.]
Action: {{"tool_name": "tool_name", "parameters": {{"param": "value"}}}}

### EXAMPLE:
Thought: The goal is to check Python files for style errors. I'll first check if a linter like 'ruff' is already on the system before attempting to use it.
Intent: check_tool_availability
Action: {{"tool_name": "check_command_exists", "parameters": {{"command_name": "ruff"}}}}

### CANONICAL INTENTS LIST:
You MUST choose one of the following: {', '.join(canonical_intents)}

RULES FOR SYSTEMATIC EXECUTION:
1. TOOL SELECTION AND USAGE WORKFLOW:
   a) First, identify if a dedicated tool exists for your task
   b) Use `check_command_exists` to verify tool availability
   c) If tool is missing: Use `provision_tool_agent` with format "I need [tool_name] to do [specific_task]" or "I need any tool to do [specific_task]"
   d) If tool exists but you need usage help: Use `execute_shell` with "--help" or "man [tool]"
   e) Apply your built-in knowledge of common tools and their syntax
   f) Only fall back to custom shell scripts when no suitable tool exists or can be installed

   CRITICAL: provision_tool_agent is ONLY for installation, never for learning syntax or usage.

2. FILE DISAMBIGUATION STRATEGY:
   When multiple files with the same name exist (e.g., multiple app.py files), YOU must choose the correct one using context:

   a) FIRST: Use `execute_shell` with `find . -name "filename" -type f` to discover ALL matching files
   b) ANALYZE context clues:
      • Recently created/modified files (check timestamps with `ls -la`)
      • Current working directory proximity
      • Project structure (root vs nested directories)
      • File size (newly created files are often smaller)
   c) CHOOSE intelligently and specify the FULL RELATIVE PATH in your tool parameters
   d) NEVER rely on the system to prompt the user - YOU decide based on context

   EXAMPLES:
   - If goal mentions "just created app.py", choose the most recently modified one
   - If working on a main project, prefer ./app.py over ./tests/app.py
   - Use explicit paths like "./src/app.py" instead of just "app.py"

3. USER INTERACTION STRATEGY - Use These Tools When Needed:
   a) BEFORE RISKY ACTIONS: Use `user_confirm` before destructive operations
      • Deleting files (especially large ones or multiple files)
      • Overwriting important files (configs, .env, package.json)
      • Making significant code changes (>100 lines)
      • Installing packages or dependencies
      • Running commands that modify system state

   b) WHEN STUCK OR FAILED: Use `user_prompt` after exhausting alternatives
      • Tried 3+ different approaches and all failed
      • Error messages are unclear and you need guidance
      • Multiple tools exist but unsure which to use

   c) FOR CRITICAL DECISIONS: Use `user_prompt` when choices have major impact
      • Multiple implementation approaches with different trade-offs
      • Ambiguous requirements needing clarification
      • Missing essential information (API keys, database URLs, etc.)

   d) DECISION PRESENTATION: When asking for choices, always provide:
      • Clear options with pros/cons
      • Your recommended option with reasoning
      • Specific technical implications of each choice

   EXAMPLES:
   - RISKY: user_confirm("Delete 50 log files (2GB total)?", default_yes=False)
   - STUCK: user_prompt("Tried pip, conda, and manual install for package X. All failed with permission errors. Any suggestions?")
   - CHOICE: user_prompt("Choose authentication: A) JWT (fast, complex setup) B) Sessions (simple, requires state) C) OAuth (secure, adds dependency). I recommend B for this project size. Which do you prefer?")

6. When goal is complete, use: Action: {{"tool_name": "finish", "reason": "explanation"}}
7. Be systematic and verify your work before finishing.
8. NEVER include any text outside the three-part format - no analysis, explanations, or commentary.
9. If errors occur, structure your Thought as: Error Analysis (what happened), Root Cause (why), Correction Plan (next action).

EXHAUSTIVE SEARCH STRATEGY:
For complex search/analysis tasks, use this systematic approach:

PHASE 1 - DISCOVERY: First discover all relevant files/data sources
• Use 'find' commands to locate all relevant files (e.g., find . -name "*.log" -type f)
• Get accurate counts and scope before proceeding
• Save intermediate results to files for reference

PHASE 2 - COMPREHENSIVE EXTRACTION: Extract ALL matching patterns
• Use specific, targeted commands with line numbers: grep -Hn "PATTERN" file1 file2
• Use context flags for better understanding: grep -A3 -B3 "PATTERN" files
• Handle large outputs by processing files individually if needed
• Save all findings to analysis files

PHASE 3 - CORRELATION: Map findings across different sources
• Search source code systematically: find . -name "*.py" -exec grep -Hn "error|ERROR" {{}} \\;
• Cross-reference log entries with source code locations
• Create correlation mappings

PHASE 4 - VERIFICATION: Ensure completeness before finishing
• Verify all relevant file types were searched
• Confirm pattern matches are comprehensive
• Double-check correlations are accurate
• Only finish when ALL requirements are demonstrably met

SHELL COMMAND BEST PRACTICES:
• Use file type filters: find . -name "*.log" instead of broad searches
• Add line numbers: grep -n or grep -Hn for file references
• Use context: grep -A2 -B2 for surrounding lines
• Process systematically: handle large outputs by breaking into phases
• Save intermediate results: create files with findings for later use

TASK INTERPRETATION EXAMPLES:
When asked to "search all exceptions in py files":
• CORRECT: Search for "raise " patterns (covers all exception types)
• INCORRECT: Search only for "Exception" (misses ValueError, TypeError, etc.)
• EXAMPLE: find . -name "*.py" -exec grep -Hn "raise " {{}} \\; > exceptions.txt

When asked to "find errors in log files":
• CORRECT: Search for error patterns: grep -i "error|fail|exception" *.log
• INCORRECT: Search only for "ERROR" (misses case variations)

When asked to "analyze code patterns":
• CORRECT: Use comprehensive searches covering all relevant patterns
• INCORRECT: Use narrow searches that miss edge cases

HANDLING LARGE OUTPUTS - CRITICAL:
When output will be large (>1000 lines), ALWAYS redirect to files directly in shell commands:
• GOOD: find . -name "*.log" -exec grep -Hn "ERROR" {{}} \\; > error_findings.txt
• BAD: Using create_file with truncated observation data.
• Then use read_file to analyze the complete saved results.

SYSTEM-SPECIFIC COMMANDS:
{self._get_system_specific_commands()}

EXAMPLE WORKFLOW:
1. find . -name "*.log" -type f > log_files.txt
2. grep -Hn "ERROR" $(cat log_files.txt) > error_entries.txt
3. find . -name "*.py" -exec grep -Hn "raise " {{}} \\; > source_errors.txt
4. Use read_file to analyze the complete results from files"""

    def build_react_prompt(self, state: ReActState, available_tools: List[UFDescriptor]) -> str:
        """Build complete prompt for the current ReAct turn."""

        # Get workspace information
        workspace_security = get_workspace_security()

        # Build base prompt without history
        base_prompt_parts = [
            self.system_prompt,
            "",
            f"GOAL: {state.goal}",
            "",
            "HARD SECURITY BOUNDARIES:",
            f"• You are working within: {workspace_security.workspace_root}",
            f"• All file operations must stay within this directory.",
            f"• Use relative paths when possible (e.g., './logs/error.log').",
            f"• CRITICAL: Any attempt to access, modify, or list files outside of this workspace will result in immediate termination of the task.",
            "",
            "AVAILABLE TOOLS:",
            self._format_tool_descriptions(available_tools),
            "",
        ]

        base_prompt = "\n".join(base_prompt_parts)

        # Apply context limits to scratchpad
        filtered_scratchpad = state.scratchpad
        if state.scratchpad:
            filtered_scratchpad, warning_triggered = self._enforce_context_limits(state.scratchpad, base_prompt)
            if warning_triggered:
                logger.info(f"Context management applied: using {len(filtered_scratchpad)}/{len(state.scratchpad)} history entries")

        # Build final prompt
        prompt_parts = base_prompt_parts.copy()

        # Add filtered scratchpad history
        if filtered_scratchpad:
            prompt_parts.extend([
                "PREVIOUS STEPS:",
                self._format_scratchpad_history(filtered_scratchpad),
                "",
            ])

        # Add current turn prompt
        prompt_parts.extend([
            f"TURN {state.turn_count + 1}:",
            "What should you do next to accomplish the goal?",
            "",
            "Your response:"
        ])

        final_prompt = "\n".join(prompt_parts)

        # Final size check and warning
        total_tokens = self._count_tokens(final_prompt)
        if total_tokens > self.warning_threshold:
            logger.warning(f"Final prompt size: {total_tokens} tokens")

        return final_prompt

    def _format_tool_descriptions(self, tools: List[UFDescriptor]) -> str:
        """Format available tools for the prompt."""
        tool_descriptions = []

        for tool in tools:
            # Extract required parameters from input schema
            schema = tool.input_schema
            properties = schema.get('properties', {})
            required = schema.get('required', [])

            params = []
            for param_name, param_def in properties.items():
                param_type = param_def.get('type', 'string')
                param_desc = param_def.get('description', 'No description')
                required_marker = " (required)" if param_name in required else " (optional)"
                params.append(f"  - {param_name} ({param_type}){required_marker}: {param_desc}")

            tool_desc = f"""- {tool.name}:{tool.version}
  Description: {tool.description}
  Parameters:
{chr(10).join(params) if params else "  None"}"""

            tool_descriptions.append(tool_desc)

        return "\n".join(tool_descriptions)

    def _format_scratchpad_history(self, scratchpad: List[ScratchpadEntry]) -> str:
        """Format scratchpad history for the prompt with normal truncation."""
        return self._format_scratchpad_history_with_aggression(scratchpad, aggression_level=0)

    def build_messages_for_openai(self, state: ReActState, available_tools: List[UFDescriptor]) -> List[Dict[str, str]]:
        """Build messages array for OpenAI chat completion."""
        prompt = self.build_react_prompt(state, available_tools)

        return [
            {
                "role": "system",
                "content": prompt
            }
        ]