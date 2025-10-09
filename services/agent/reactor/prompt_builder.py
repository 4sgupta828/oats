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
from reactor.models import ReActState, TranscriptEntry
from core.workspace_security import get_workspace_security
from core.config import UFFlowConfig

logger = logging.getLogger(__name__)

class ReActPromptBuilder:
    """Builds prompts for the ReAct agent using scratchpad history."""

    def __init__(self):
        self.system_context = self._get_system_context()
        self.prompt_version = UFFlowConfig.get_prompt_version()
        self.system_prompt = self._build_system_prompt()
        # Initialize tokenizer for accurate context management
        if TIKTOKEN_AVAILABLE:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        else:
            self.tokenizer = None
        self.max_tokens_per_turn = 12000  # Hard limit (increased for ReAct workflow)
        self.warning_threshold = 6000    # Warning threshold

    def _count_tokens(self, text: str) -> int:
        """Count tokens accurately using the tiktoken library."""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Approximate token count: ~4 characters per token
            return len(text) // 4

    def _enforce_context_limits(self, transcript: List[TranscriptEntry], prompt_base: str) -> Tuple[List[TranscriptEntry], bool]:
        """Enforce token limits using progressive thinning strategy.

        Strategy:
        1. First try: Make observations more aggressive (remove middle/end samples)
        2. Second try: Make observations minimal (start/end only)
        3. Last resort: Remove oldest turns entirely

        Returns:
            Tuple of (filtered_transcript, warning_triggered)
        """
        base_tokens = self._count_tokens(prompt_base)
        warning_triggered = False

        # Try progressive thinning levels
        for aggression_level in range(3):  # 0=normal, 1=aggressive, 2=minimal
            current_transcript = transcript.copy()

            # Test this aggression level
            history_text = self._format_transcript_history_with_aggression(current_transcript, aggression_level)
            total_tokens = base_tokens + self._count_tokens(history_text)

            if total_tokens <= self.max_tokens_per_turn:
                if total_tokens > self.warning_threshold and not warning_triggered:
                    logger.warning(f"Context approaching limit: {total_tokens}/{self.max_tokens_per_turn} tokens")
                    warning_triggered = True
                if aggression_level > 0:
                    logger.info(f"Applied aggression level {aggression_level} to fit context")
                    warning_triggered = True
                # Store the aggression level for the final formatting
                return self._apply_aggression_to_scratchpad(current_transcript, aggression_level), warning_triggered

            if aggression_level == 2:  # If even minimal didn't work, remove old turns
                logger.warning(f"Even minimal truncation exceeded limit ({total_tokens} tokens), removing old turns")

        # Last resort: Remove oldest entries with minimal truncation
        current_transcript = transcript.copy()
        aggression_level = 2  # Use minimal truncation while removing turns

        while current_transcript:
            history_text = self._format_transcript_history_with_aggression(current_transcript, aggression_level)
            total_tokens = base_tokens + self._count_tokens(history_text)

            if total_tokens <= self.max_tokens_per_turn:
                logger.warning(f"Context management: using {len(current_transcript)}/{len(transcript)} turns with minimal truncation")
                break

            current_transcript.pop(0)  # Remove oldest turn
            warning_triggered = True

        return self._apply_aggression_to_scratchpad(current_transcript, aggression_level), warning_triggered

    def _format_state(self, state) -> str:
        """Format current state for prompt."""
        import json
        return json.dumps(state.dict(), indent=2)

    def _format_transcript_history_with_aggression(self, transcript: List[TranscriptEntry], aggression_level: int) -> str:
        """Format transcript with specific aggression level for testing."""
        import json
        history_parts = []

        for entry in transcript:
            history_parts.append(f"Turn {entry.turn}:")
            history_parts.append(f"Reflect: {json.dumps(entry.reflect.dict())}")
            history_parts.append(f"Strategize: {json.dumps(entry.strategize.dict())}")
            history_parts.append(f"Act: {json.dumps(entry.act.dict())}")
            truncated_obs = self._truncate_observation(entry.observation, aggression_level, force_truncate=(aggression_level > 0))
            history_parts.append(f"Observation: {truncated_obs}")
            history_parts.append("")  # Empty line between turns

        return "\n".join(history_parts)

    def _apply_aggression_to_scratchpad(self, transcript: List[TranscriptEntry], aggression_level: int) -> List[TranscriptEntry]:
        """Apply truncation aggression level to transcript entries."""
        if aggression_level == 0:
            return transcript  # No change needed for normal level

        # Create new entries with truncated observations
        thinned_transcript = []
        for entry in transcript:
            new_entry = entry.model_copy()
            new_entry.observation = self._truncate_observation(entry.observation, aggression_level, force_truncate=True)
            thinned_transcript.append(new_entry)

        return thinned_transcript

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

        # Check if this observation contains React UI elements that should not be trimmed
        react_ui_elements = ["**New Facts:**", "**Hypothesis:**", "**Progress Check:**", "**Thought:**", "**Executing Action:**", "**Observation:**"]
        has_react_elements = any(element in observation for element in react_ui_elements)

        if has_react_elements:
            # Don't truncate if it contains React UI elements
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
            return r"""macOS Command Examples:
• Regex search: grep -E "pattern1|pattern2" file.txt
• Exception search: grep -Hn "raise " *.py
• Case-insensitive: grep -i "error" *.log
• Multi-file with filenames: find . -name "*.py" -exec grep -Hn "raise " {} \;
• Count matches: grep -c "pattern" file.txt
• Context lines: grep -A3 -B3 "pattern" file.txt
• AVOID: grep -P (not supported on macOS)"""
        elif self.system_context['os'] == 'Linux':
            return r"""Linux Command Examples:
• Perl regex: grep -P "(?<=raise )\w+" file.txt
• Extended regex: grep -E "pattern1|pattern2" file.txt
• All GNU features available
• Use -P for advanced regex patterns"""
        else:
            return """Windows Command Examples:
• Use PowerShell select-string instead of grep
• Example: select-string "pattern" -path "*.txt"
• For complex tasks, prefer Python scripts"""

    def _load_prompt_template(self) -> str:
        """Load prompt template from versioned file."""
        prompt_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        prompt_file = os.path.join(prompt_dir, f'{self.prompt_version}.txt')

        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt version '{self.prompt_version}' not found at {prompt_file}")

        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()

    def _build_system_prompt(self) -> str:
        """Build the core system prompt from versioned template file."""
        # Load the template
        template = self._load_prompt_template()

        # Get system-specific commands
        system_commands = self._get_system_specific_commands()

        # Replace placeholders with actual values
        prompt = template.format(
            os=self.system_context['os'],
            shell_notes=self.system_context['shell_notes'],
            python_version=self.system_context['python_version'],
            system_commands=system_commands
        )

        return prompt


    def build_react_prompt(self, state: ReActState, available_tools: List[UFDescriptor]) -> str:
        """Build complete prompt for the current ReAct turn."""

        # Get workspace information
        workspace_security = get_workspace_security()

        # Build base prompt without history
        base_prompt_parts = [
            self.system_prompt,
            "",
            "AVAILABLE TOOLS:",
            self._format_tool_descriptions(available_tools),
            "",
            f"**Goal:** {state.goal}",
            "",
            "**State:**",
            self._format_state(state.state),
            "",
            f"**Turn Number:** {state.turn_count + 1}",
            "",
            "HARD SECURITY BOUNDARIES:",
            f"• You are working within: {workspace_security.workspace_root}",
            f"• All file operations must stay within this directory.",
            f"• Use relative paths when possible (e.g., './logs/error.log').",
            f"• CRITICAL: Any attempt to access, modify, or list files outside of this workspace will result in immediate termination of the task.",
            "",
        ]

        base_prompt = "\n".join(base_prompt_parts)

        # Apply context limits to transcript
        filtered_transcript = state.transcript
        if state.transcript:
            filtered_transcript, warning_triggered = self._enforce_context_limits(state.transcript, base_prompt)
            if warning_triggered:
                logger.info(f"Context management applied: using {len(filtered_transcript)}/{len(state.transcript)} history entries")

        # Build final prompt
        prompt_parts = base_prompt_parts.copy()

        # Add filtered transcript history
        if filtered_transcript:
            prompt_parts.extend([
                "**Transcript:**",
                self._format_transcript_history(filtered_transcript),
                "",
            ])

        # Add current turn prompt
        prompt_parts.extend([
            f"Now execute Turn {state.turn_count + 1}. Provide your response as a single JSON object with reflect, strategize, state, and act sections."
        ])

        final_prompt = "\n".join(prompt_parts)

        # Final size check and warning
        total_tokens = self._count_tokens(final_prompt)
        if total_tokens > self.warning_threshold:
            logger.warning(f"Final prompt size: {total_tokens} tokens")

        return final_prompt

    def _format_tool_descriptions(self, tools: List[UFDescriptor]) -> str:
        """Format available tools for the prompt with enhanced visibility."""
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

            # Add warning for tools with required parameters
            required_warning = ""
            if required:
                required_list = ", ".join(required)
                required_warning = f"\n  REQUIRED: {required_list}"

            tool_desc = f"""- {tool.name}:{tool.version}
  Description: {tool.description}{required_warning}
  Parameters:
{chr(10).join(params) if params else "  None"}"""

            tool_descriptions.append(tool_desc)

        return "\n".join(tool_descriptions)

    def _format_transcript_history(self, transcript: List[TranscriptEntry]) -> str:
        """Format transcript history for the prompt with normal truncation."""
        return self._format_transcript_history_with_aggression(transcript, aggression_level=0)

    def build_messages_for_openai(self, state: ReActState, available_tools: List[UFDescriptor]) -> List[Dict[str, str]]:
        """Build messages array for OpenAI chat completion."""
        prompt = self.build_react_prompt(state, available_tools)

        return [
            {
                "role": "system",
                "content": prompt
            }
        ]
