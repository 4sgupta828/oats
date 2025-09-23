# reactor/prompt_builder.py

import sys
import os
import platform
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
        self.max_tokens_per_turn = 8000  # Hard limit (increased for ReAct workflow)
        self.warning_threshold = 6000    # Warning threshold

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

    def _format_working_memory(self, working_memory) -> str:
        """Format current working memory state for prompt."""
        if not working_memory:
            return "• No working memory established yet"

        parts = []

        if working_memory.known_facts:
            facts_str = "\n    ".join([f"- {fact}" for fact in working_memory.known_facts])
            parts.append(f"• KNOWN FACTS:\n    {facts_str}")

        if working_memory.current_hypothesis:
            parts.append(f"• CURRENT HYPOTHESIS: {working_memory.current_hypothesis}")

        if working_memory.evidence_gaps:
            gaps_str = "\n    ".join([f"- {gap}" for gap in working_memory.evidence_gaps])
            parts.append(f"• EVIDENCE GAPS:\n    {gaps_str}")

        if working_memory.failed_approaches:
            failed_str = "\n    ".join([f"- {approach}" for approach in working_memory.failed_approaches])
            parts.append(f"• FAILED APPROACHES:\n    {failed_str}")

        if working_memory.next_priorities:
            priorities_str = "\n    ".join([f"- {priority}" for priority in working_memory.next_priorities])
            parts.append(f"• NEXT PRIORITIES:\n    {priorities_str}")

        if working_memory.synthesis_notes:
            parts.append(f"• SYNTHESIS: {working_memory.synthesis_notes}")

        return "\n".join(parts) if parts else "• Working memory is empty"

    def _format_scratchpad_history_with_aggression(self, scratchpad: List[ScratchpadEntry], aggression_level: int) -> str:
        """Format scratchpad with specific aggression level for testing."""
        history_parts = []

        for entry in scratchpad:
            history_parts.append(f"Turn {entry.turn}:")
            if entry.progress_check:
                history_parts.append(f"Progress Check: {entry.progress_check}")
            history_parts.append(f"Thought: {entry.thought}")
            if entry.intent:
                history_parts.append(f"Intent: {entry.intent}")
            history_parts.append(f"Action: {entry.action}")
            truncated_obs = self._truncate_observation(entry.observation, aggression_level, force_truncate=(aggression_level > 0))
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
            new_entry.observation = self._truncate_observation(entry.observation, aggression_level, force_truncate=True)
            thinned_scratchpad.append(new_entry)

        return thinned_scratchpad

    def _truncate_observation(self, observation: str, aggression_level: int = 0, force_truncate: bool = False) -> str:
        """Truncate large observations with progressive aggression levels.

        Args:
            observation: The original observation text
            aggression_level: 0=light, 1=moderate, 2=aggressive
            force_truncate: If True, apply truncation even at level 0

        Returns:
            Truncated observation (or original if level 0 and not forced)
        """
        if not observation or not observation.strip():
            return observation

        # Level 0 with no forcing = return original (when context has plenty of room)
        if aggression_level == 0 and not force_truncate:
            return observation

        lines = observation.split('\n')

        # Progressive settings based on aggression level
        if aggression_level == 0:  # Light truncation (only when forced)
            max_lines, sample_lines, max_line_length = 30, 4, 200  # Very generous limits
        elif aggression_level == 1:  # Moderate truncation
            max_lines, sample_lines, max_line_length = 15, 3, 150
        else:  # Aggressive truncation (level 2+)
            max_lines, sample_lines, max_line_length = 8, 2, 100

        # Apply line length limits only for aggressive levels
        if aggression_level >= 1:
            lines = [self._smart_truncate_line(line, max_line_length) for line in lines]

        # If short enough, return as-is
        if len(lines) <= max_lines:
            return '\n'.join(lines)

        # For most aggressive levels, only show start/end (no middle)
        if aggression_level >= 2:
            truncated = []
            truncated.extend(lines[:sample_lines])
            truncated.append(f'... [{len(lines) - 2*sample_lines} lines omitted] ...')
            truncated.extend(lines[-sample_lines:])
            return '\n'.join(truncated)

        # Light/moderate: Sample from start, middle, end
        start_lines = lines[:sample_lines]
        middle_idx = len(lines) // 2
        middle_lines = lines[middle_idx-sample_lines//2:middle_idx+sample_lines//2+1]
        end_lines = lines[-sample_lines:]

        # Build truncated version
        truncated = []
        truncated.extend(start_lines)
        if aggression_level == 0:  # Only include middle for light level
            truncated.append(f'... [{len(lines) - 2*sample_lines - len(middle_lines)} lines omitted] ...')
            truncated.extend(middle_lines)
        if middle_lines != end_lines or aggression_level >= 1:
            truncated.append(f'... [showing last {sample_lines} lines] ...')
            truncated.extend(end_lines)

        return '\n'.join(truncated)

    def _smart_truncate_line(self, line: str, max_length: int) -> str:
        """Smart line truncation that preserves complete file paths and important information."""
        if len(line) <= max_length:
            return line

        # Check if line contains file paths (common patterns)
        file_path_indicators = [
            '• ', '- ', 'file:', 'path:', '.py', '.js', '.ts', '.json', '.csv', '.txt', '.md',
            '/', '\\', 'Files found:', 'Found in:', 'matches in'
        ]

        is_file_line = any(indicator in line for indicator in file_path_indicators)

        if is_file_line:
            # For file path lines, try to preserve the complete path
            # Find the actual file path in the line
            import re

            # Look for common file path patterns
            file_path_patterns = [
                r'[•\-]\s+([^\s]+\.[a-zA-Z0-9]+)',  # • filename.ext or - filename.ext
                r'([a-zA-Z0-9_/\\.-]+\.[a-zA-Z0-9]+)',  # any/path/filename.ext
                r'([a-zA-Z0-9_/\\.-]+\.py)',  # Python files specifically
                r'([a-zA-Z0-9_/\\.-]+\.js)',  # JavaScript files
                r'([a-zA-Z0-9_/\\.-]+\.json)',  # JSON files
            ]

            for pattern in file_path_patterns:
                matches = re.findall(pattern, line)
                if matches:
                    file_path = matches[0]
                    # If the file path fits, keep the essential part with file path
                    if len(file_path) <= max_length - 10:  # Leave room for context
                        # Extract key parts of the line with the file path
                        if '• ' in line:
                            return f"• {file_path}"
                        elif '- ' in line:
                            return f"- {file_path}"
                        else:
                            # Keep the file path with minimal context
                            prefix = line[:20] if len(line) > 20 else ""
                            if len(prefix + file_path) <= max_length:
                                return f"{prefix}...{file_path}"
                            else:
                                return file_path

            # If no clear file path found, truncate more carefully for file-related content
            if max_length > 20:
                return line[:max_length-3] + "..."
            else:
                return line[:max_length]
        else:
            # Regular truncation for non-file lines
            return line[:max_length] + ('...' if len(line) > max_length else '')

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
            "execute_shell", "read_file", "write_file", "create_file", "list_files",
            "smart_search", "find_files_by_name", "content_search", "find_function", "search_functions",
            "provision_tool", "ask_user", "confirm_with_user"
        ]

        return f"""You are an autonomous AI agent that accomplishes complex goals by reasoning step-by-step and using available tools.

SYSTEM CONTEXT:
• Operating System: {self.system_context['os']}
• Shell Limitations: {self.system_context['shell_notes']}
• Grep Capabilities: {self.system_context['grep_features']}
• Python Version: {self.system_context['python_version']}

## STRUCTURED REASONING FRAMEWORK

Your response MUST follow this enhanced four-part format exactly:

WORKING MEMORY UPDATE: [How should the working memory be updated based on new information? Format as structured data]
PROGRESS CHECK: [Am I making progress? Have I seen this before? What patterns am I noticing?]
Thought: [Reason about your goal using current working memory and formulate next action]
Intent: [Classify your plan into a single intent from the CANONICAL INTENTS LIST below]
Action: {{"tool_name": "tool_name", "parameters": {{"param": "value"}}}}

### WORKING MEMORY UPDATE FORMAT:
Use this structured format for working memory updates:
```
NEW_FACTS: ["fact1", "fact2"]
HYPOTHESIS: "current working theory"
EVIDENCE_GAPS: ["gap1", "gap2"]
FAILED_APPROACHES: ["approach that didn't work"]
NEXT_PRIORITIES: ["priority1", "priority2"]
SYNTHESIS: "current understanding summary"
```

### EXAMPLE:
WORKING MEMORY UPDATE:
```
NEW_FACTS: ["Goal is to find 'llm calls' - need to discover what LLM functions exist in codebase"]
HYPOTHESIS: "LLM functions likely contain 'llm' in their name or are related to language models"
EVIDENCE_GAPS: ["what specific function names are used for LLM calls", "where these functions are defined"]
FAILED_APPROACHES: []
NEXT_PRIORITIES: ["search broadly for 'llm' patterns to discover function names"]
SYNTHESIS: "Starting discovery phase to identify LLM-related functions before searching for specific calls"
```
PROGRESS CHECK: Initial step, need to discover LLM functions before I can find their calls.
Thought: I need to find "llm calls" but don't know the specific function names yet. I should start with a broad search to discover what LLM-related functions exist in this codebase.
Intent: smart_search
Action: {{"tool_name": "smart_search", "parameters": {{"pattern": "llm", "file_types": ["py"], "context_hint": "function definitions and calls"}}}}

### CANONICAL INTENTS LIST:
You MUST choose one of the following: {', '.join(canonical_intents)}

## META-COGNITIVE GUIDELINES

LOOP DETECTION: Before each action, check current working memory - are you repeating similar actions without new information?
SYNTHESIS REQUIREMENT: When working memory shows multiple facts, actively combine and analyze rather than collecting more data.
WORKING MEMORY FOCUS: Always reference your current working memory state when reasoning about next actions.

RULES FOR SYSTEMATIC EXECUTION:
1. TOOL SELECTION: Use appropriate tools for tasks. Check availability first, install if missing, consult help if needed. provision_tool_agent is ONLY for installation.

2. **EFFICIENT SEARCH & CODE DISCOVERY STRATEGY (CRITICAL)**:
   **SEARCH PRIORITIES**: ALWAYS use smart search tools BEFORE directory exploration:
   - **FIRST PRIORITY**: Use `smart_search(pattern, file_types, context_hint)` to find content in files
   - **SECOND PRIORITY**: Use `find_files_by_name(filename_pattern)` to find files by name
   - **LAST RESORT**: Only use `list_files()` for understanding directory structure, NEVER for finding specific files

   **MAXIMIZE DISCOVERY WITH BROAD REGEX PATTERNS**:
   - Use `.*{{term}}.*` patterns to catch ALL variations (e.g., `.*llm.*` finds get_llm_response, llm_call, my_llm_helper)
   - Start broad, then narrow down if needed
   - Better to find too much than miss important matches

   **TARGETED CODE READING**:
   - **Don't read entire files** - use targeted reading to focus on what you need
   - **Discovery workflow**: `smart_search(".*pattern.*", ["py"])` → find relevant code → `read_file(file, start_line=X, context_lines=10)`
   - **Function analysis**: `search_functions(".*name.*", "function", use_regex=True)` → get exact location → read with context
   - **Expand context as needed**: Start with 10 lines, increase to 20-30 for larger functions or classes

   **EXAMPLES**:
   - Finding CSV with student data: `smart_search(".*student.*", file_types=["csv"], context_hint="student data")`
   - Finding config files: `find_files_by_name(".*config.*")`
   - Finding API references: `smart_search(".*api.*", file_types=["py", "js"], context_hint="source code")`
   - Finding exact function: `search_functions("my_function", "function")`
   - Finding ALL functions containing term: `search_functions(".*llm.*", "function", use_regex=True)` to catch get_llm, llm_call, my_llm_helper, etc.
   - Finding ALL classes containing term: `search_functions(".*handler.*", "class", use_regex=True)` to catch FileHandler, DataHandler, MyHandler, etc.

   **CRITICAL RULES**:
   - When search results show filenames, use the EXACT filename returned - do NOT modify or guess filenames
   - **AVOID**: `list_files()` followed by manual file inspection - this is inefficient!

3. PYTHON SCRIPT EXECUTION: When you need to run custom Python scripts, ALWAYS follow this 2-step process:
   - Step 1: Use create_file to write the Python script to a separate .py file
   - Step 2: Use execute_shell to run the file with "python filename.py"
   - NEVER run Python scripts directly on the execute_shell command line as it is error-prone and buggy

4. FILE DISAMBIGUATION: When multiple files exist with same name, use find to discover all, analyze context (timestamps, location, size), choose intelligently with full paths. Never prompt user - decide based on context.

5. USER INTERACTION: Confirm before risky actions (delete, overwrite, install). Prompt user when stuck after trying multiple approaches or for critical decisions. Always provide options with pros/cons and your recommendation.

6. When goal is complete, use: Action: {{"tool_name": "finish", "reason": "explanation"}}
7. Be systematic and verify your work before finishing.
8. NEVER include any text outside the three-part format - no analysis, explanations, or commentary.
9. If errors occur, structure your Thought as: Error Analysis (what happened), Root Cause (why), Correction Plan (next action).

SEARCH EXECUTION PHASES:
PHASE 1 - SMART DISCOVERY: Use smart_search() or find_files_by_name() as defined in rule #2 above
PHASE 2 - TARGETED SEARCH: If insufficient, use content_search() with specific regex patterns
PHASE 3 - FALLBACK SEARCH: Only if smart tools fail, use traditional find/grep commands
PHASE 4 - VERIFICATION: Confirm comprehensive coverage before finishing

SEARCH PATTERNS: Use comprehensive patterns to avoid missing variations (e.g., 'raise ' not 'Exception', 'error|fail' not 'ERROR', include case variations).

DIRECTORY EXCLUSIONS: ALWAYS exclude these directories from searches and file operations:
- Virtual environments: venv, .venv, env, .env, ENV, venv.bak, env.bak, venv*, env*
- Build/cache: __pycache__, build, dist, node_modules, .git, site, downloads, eggs, .eggs
- IDE files: .vscode, .idea, .DS_Store, Thumbs.db, .ipynb_checkpoints
Example: find . -type f -name "*.py" -not -path "./venv/*" -not -path "./__pycache__/*" -not -path "./.git/*"

SYSTEM-SPECIFIC COMMANDS:
{self._get_system_specific_commands()}"""

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
            "CURRENT WORKING MEMORY STATE:",
            self._format_working_memory(state.working_memory),
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