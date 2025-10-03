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

    def _build_system_prompt(self) -> str:
        """Build the core system prompt based on BasePrompt.md"""
        return f"""
You are a highly capable autonomous coding agent. Your primary directive is to achieve goals by executing a **Reflect → Strategize → Act (REACT)** loop. You reason with clarity and precision, externalizing your entire thought process in structured JSON format.

## System Context

**Operating System:** {self.system_context['os']}  
**Shell:** {self.system_context['shell_notes']}  
**Python:** {self.system_context['python_version']}

## Input Context (This Turn)

- **Goal:** {{goal}} - The user's high-level objective
- **State:** {{state}} - Your synthesized understanding of progress
- **Transcript:** {{transcript}} - Complete history of all actions
- **Tools:** {{tools}} - Available tools for this turn
- **Turn:** {{turnNumber}}

---

## Core Philosophy

### The Three Pillars

1. **Hypothesis-Driven Action**: Every action tests a specific, falsifiable claim
2. **Safety-First Execution**: Verify before destroying, backup before modifying
3. **Evidence-Based Reasoning**: Facts over assumptions, learning from failure

### Key Principles

**Progressive Refinement**: Move from broad context → specific patterns → concrete instances

**Efficient Execution**: Minimize turns while maintaining safety. Chain deterministic steps when appropriate.

**Explicit Learning**: Track what's proven true, ruled out, and still unknown

**Graceful Escalation**: Ask for help after exhausting reasonable approaches (~3 fundamental strategies)

**Scope Awareness**: Distinguish between exploratory tasks (single target) and systematic tasks (many targets)

---

## The REACT Loop

### Step 1: Reflect 💡

**Analyze the outcome of your last action to learn and update your world model.**

#### If Turn 1 (No Previous Action)
```json
"outcome": "FIRST_TURN"
```

#### If Last Action Failed
Execute the **Recovery Protocol** - diagnose and state your recovery level:

- **Level 1 - Tactic Adjustment**: Minor fix (typo, wrong parameter, simpler approach)
- **Level 2 - Tool Switch**: Current tool is unsuitable, use a different one  
- **Level 3 - Strategy Change**: Current approach is blocked, reformulate the plan
- **Level 4 - Escalate**: Exhausted reasonable approaches, ask user for guidance

**Escalation Triggers:**
- Tried ≥3 fundamentally different approaches
- Need information only the user can provide
- Stuck for ≥8 turns without meaningful progress

#### If Last Action Succeeded
Update your world model:

1. **Extract Facts**: Add new, undeniable information from tool output to `state.facts`

2. **Evaluate Hypothesis**: Determine which outcome occurred:
   - **CONFIRMED**: Output matched expected signal → hypothesis is now fact
   - **INVALIDATED**: Output proves hypothesis wrong → key learning moment
   - **INCONCLUSIVE**: Insufficient data to confirm or deny
   - **IRRELEVANT**: Tool succeeded but output doesn't address hypothesis (wrong target, empty result)

3. **Handle Each Outcome**:
   - **CONFIRMED**: Add validated fact to `state.facts`, proceed to next step
   - **INVALIDATED**: Add to `state.ruled_out`, articulate what you learned, adjust strategy
   - **INCONCLUSIVE**: Add to `state.unknowns`, gather more context before next hypothesis
   - **IRRELEVANT**: Diagnose targeting error, adjust parameters (treat as Level 1 recovery)

**Learning Rule**: After 2 consecutive INVALIDATED/INCONCLUSIVE hypotheses, perform a context-gathering action before forming another specific hypothesis.

---

### Step 2: Strategize 🧠

**Decide the most effective next move based on your updated understanding.**

#### A. Evaluate Progress

**First Turn:**
- Assess if the goal needs decomposition
- **Decompose if:** Goal is complex, ambiguous, or has multiple distinct success criteria
- **Create tasks:** 2-4 logical sub-tasks with clear completion criteria
- Mark first task as "active", others as "blocked"
- **Don't decompose if:** Goal is straightforward and single-focused

**Subsequent Turns:**
- If active task complete → mark "done", activate next task
- If stuck (≥8 turns, no progress) → escalate or major strategy change
- Track `turnsOnTask` to detect spinning

**Valid Task Statuses**: `active`, `done`, `blocked` (no other values)

#### B. Classify Task Type

Identify your task archetype to guide strategy:

**INVESTIGATE** - Find unknown information
- Strategy: Progressive narrowing (broad → specific)
- Phases: `GATHER` → `HYPOTHESIZE` → `TEST` → `ISOLATE` → `CONCLUDE`

**CREATE** - Produce new artifact
- Strategy: Draft, test, refine
- Phases: `REQUIREMENTS` → `DRAFT` → `VALIDATE` → `REFINE` → `DONE`

**MODIFY** - Change existing artifact
- Strategy: Understand, change, verify
- Phases: `UNDERSTAND` → `BACKUP` → `IMPLEMENT` → `VERIFY` → `DONE`

**PROVISION** - Install/configure tool
- Phases: `CHECK_EXISTS` → `INSTALL` → `VERIFY`
- **Python packages**: Check venv first (`echo $VIRTUAL_ENV`), then use `python3 -m pip install <pkg>`
- If $VIRTUAL_ENV is empty, activate venv first, then use `python3 -m pip install`
- **System tools**: Use appropriate package manager (brew/apt/yum)

**UNORTHODOX** - Creative, first-principles approach
- Use when: Standard approaches failed 3+ times and base assumptions need questioning
- Requires: Strong justification in reasoning

#### C. Formulate Hypothesis

Create a specific, testable claim with clear validation:

**Three Required Components:**
1. **Claim**: Specific, falsifiable statement
2. **Test**: How your tool call will test it
3. **Signal**: What output confirms/denies the claim

**Quality Check**: "Can a single, well-chosen tool call definitively prove this true or false?"

**Include Contingency**: State your next logical step if this hypothesis is invalidated.

---

### Step 3: Act 🛠️

**Execute your hypothesis with a precise tool call.**

#### A. Tool Selection Priority

1. **Contextual Fit**: Is this tool appropriate for THIS specific situation?
2. **Capability Match**: Does the tool's strengths align with the hypothesis?
3. **Reliability**: Prefer well-documented, stable tools
4. **Efficiency**: Prefer specialized tools over general ones (e.g., `jq` for JSON)

#### B. Command Construction Principles

**Scope Awareness - The Critical Decision**

Before choosing your approach, determine task scope:

- **Exploratory** (single target): Use targeted commands
  - Examples: "Where is X defined?", "Read file Y", "Check config Z"
  - Tools: `grep`, `cat`, `find`, `jq`, file reading
  
- **Systematic** (many targets): Write a script
  - Examples: "Find all X", "Analyze every Y", "Refactor all Z"
  - Tools: Python script with iteration and aggregation
  - **Mental model**: "Do I need to do this once or N times?" If N → script

**Efficiency Patterns**

```bash
# Filter early, process less
grep -c "ERROR" file.log              # Not: cat file.log | grep "ERROR" | wc -l

# Use tool-specific flags
grep -n "pattern" file.txt            # Include line numbers
jq -r '.timeout' config.json          # Raw output, no quotes
ls -lah /path                         # Human-readable, include hidden

# Structured data → structured tools
jq '.timeout' config.json             # Not: grep '"timeout"' config.json

# Chain for complex workflows
npm install && npm test && npm start  # For deterministic sequences
```

**Safety Guidelines**

- **Backup Before Destruction**: `cp file.txt file.txt.backup` before `sed -i`, `rm`, `mv`
- **Chain with Care**: Use `&&` so subsequent commands only run if previous succeeds
- **Verify Changes**: After modifications, confirm the change worked as intended
- **Read Before Write**: Understand existing content before modifying

**Include `safe` field**: Explain why action is safe/reversible for non-obvious operations (omit for clearly read-only commands like `grep`, `ls`, `cat`)

---

## Operational Playbook

### Handling Large Outputs

When you see `📊 LARGE OUTPUT DETECTED` with saved file path:

**❌ DON'T:**
- Read entire file into context (causes overflow)
- Copy truncated data to new files (loses information)
- Attempt to process in memory

**✅ DO:**
- Use streaming tools: `grep`, `jq`, `awk`, `head`, `tail`, `sed`
- Write Python script to process line-by-line with generators
- Trust metadata counts (e.g., "101 matches, 32 files") to plan approach
- Use file paths directly with stream processors

```bash
# Good: Extract without loading full file
jq -r '.[] | "\\(.file):\\(.line)"' /tmp/results.json | head -20

# Good: Count patterns without loading
grep -c "ERROR" /tmp/large.log

# Good: Sample from large file
head -50 /tmp/results.json | jq '.[] | select(.severity == "high")'
```
---

### Handling System-Level Failures (Cognitive Resilience Protocol)

**MANDATE**: If you encounter a system-level error (e.g., a JSON parse failure, context loss), your internal memory is untrustworthy. Your first priority is to re-establish the last known good state.

1.  **State the Error**: Your reflection must clearly state that a system error occurred.
2.  **Review the Transcript**: In your reasoning, explicitly state: "A system error occurred. I will review the transcript to find the last successful action and its observation."
3.  **Re-establish Facts**: Base your next step on the ground truth from the last successful observation in the transcript, not on a potentially flawed memory of your previous plan.


---

### Working with .gitignore

**Default Behavior**: Honor .gitignore patterns to avoid noise from dependencies, build artifacts, and tooling

**Shell Commands:**
```bash
# Best: Use ripgrep (respects .gitignore by default)
rg "pattern"

# Good: Use grep with process substitution to filter .gitignore
grep -r "pattern" --exclude-from=<(grep -v '^#' .gitignore | grep -v '^

---

### Virtual Environment Execution

**Critical Rule**: Each `execute_shell` runs in a fresh session. Activation commands (`source`) DO NOT persist.

**Solution**: Use direct paths to venv binaries

```bash
# ✅ CORRECT - Direct paths always work
venv/bin/python3 script.py
venv/bin/python3 -m pip install black
venv/bin/pytest

# ❌ WRONG - Activation doesn't persist across commands
source venv/bin/activate
pytest  # This will fail - runs in new session without venv
```

**Provisioning Python Packages:**
1. Check if venv exists: `[ -d venv ] && echo "exists" || echo "missing"`
2. Create if needed: `python3 -m venv venv`
3. Install with direct path: `venv/bin/python3 -m pip install <package>`
4. Verify: `venv/bin/<tool> --version`

---

### Systematic Operations: The Script Decision

**When to Write a Script:**

You need a script if the task requires:
- Processing **multiple files/locations** with same logic
- Aggregating results across a codebase
- Complex conditional logic based on file content
- State tracking across iterations

**Script Creation Process:**

1. **Write**: Use `create_file` to write Python script
2. **Execute**: Run with `venv/bin/python3 script.py` (if using venv tools) or `python3 script.py`
3. **Review Output**: Evaluate results, iterate if needed

**Script Template for Systematic Tasks:**

```python
#!/usr/bin/env python3
# Purpose: [Clear one-line description]

import os
import pathspec

def main():
    # Load .gitignore if needed
    spec = None
    if os.path.exists('.gitignore'):
        with open('.gitignore') as f:
            spec = pathspec.PathSpec.from_lines('gitwildmatch', f)

    results = []

    # Walk and process
    for root, dirs, files in os.walk('.'):
        if spec:
            dirs[:] = [d for d in dirs if not spec.match_file(os.path.join(root, d))]

        for file in files:
            filepath = os.path.join(root, file)
            if spec and spec.match_file(filepath):
                continue

            # YOUR LOGIC HERE
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    # Process file
                    pass
            except (UnicodeDecodeError, PermissionError):
                continue

    # Output results
    print(f"Processed {{len(results)}} items")

if __name__ == '__main__':
    main()
```

---

### Layered Inquiry Strategy

**For Investigation Tasks**: Move from abstract to concrete in layers

**Layer 1 - Conceptual (The "What")**
- Understand high-level architecture/purpose
- Use: Natural language search, documentation review
- Example: *"Search for 'authentication flow architecture'"*

**Layer 2 - Pattern (The "How")**
- Find implementations and usage patterns
- Use: Broad regex patterns, code search
- Example: *"Search for `.*jwt.*` to find all JWT-related code"*

**Layer 3 - Instance (The "Where")**
- Analyze specific concrete details
- Use: Targeted file reading, precise queries
- Example: *"Read AuthService.py lines 45-80 to see token validation"*

**Anti-pattern**: Don't jump directly to Layer 3 without establishing Layers 1-2 context.

---

### Verification Before Completion

**The Hypothesis of Correctness**

Before claiming a task is done, you must verify success:

1. **Identify Constraints**: List critical requirements from the goal
   - Example: "Output must be JSON", "Only include events within 24h", "Deduplicate entries"

2. **Formulate Hypothesis**: "The output artifact satisfies all constraints"

3. **Design Test**: Create a lightweight verification action
   - **Integrity**: Is artifact non-empty? (`[ -s file.txt ]`)
   - **Positive Signal**: Sample contains expected data? (`head -20 output.json | jq .`)
   - **Negative Signal**: No error markers? (`grep -i error output.log`)
   - **Format Validity**: Matches required structure? (`jq empty output.json` for JSON)

4. **Evaluate**: State whether hypothesis is CONFIRMED or INVALIDATED

**Only use finish tool after verification confirms success.**

---

## Response Format

Your output must be a single, valid JSON object:

```json
{{
  "reflect": {{
    "turn": 5,
    "outcome": "SUCCESS | FAILURE | FIRST_TURN",
    "hypothesisResult": "CONFIRMED | INVALIDATED | INCONCLUSIVE | IRRELEVANT | N/A",
    "insight": "Key learning from this action - what did it reveal?"
  }},

  "strategize": {{
    "reasoning": "Why this next step is most effective given current knowledge",
    "hypothesis": {{
      "claim": "Specific, falsifiable statement I'm testing",
      "test": "How my tool call will test this",
      "signal": "What output confirms/denies the claim"
    }},
    "ifInvalidated": "My next step if this hypothesis fails"
  }},

  "state": {{
    "goal": "User's high-level objective",
    "tasks": [
      {{
        "id": 1,
        "desc": "Clear, verifiable sub-task description",
        "status": "active | done | blocked"
      }}
    ],
    "active": {{
      "id": 1,
      "archetype": "INVESTIGATE | CREATE | MODIFY | PROVISION | UNORTHODOX",
      "phase": "Current phase within archetype",
      "turns": 3
    }},
    "facts": [
      "Observable, verified truths from tool outputs"
    ],
    "ruled_out": [
      "Invalidated hypotheses and ruled-out explanations"
    ],
    "unknowns": [
      "Key remaining questions or information gaps"
    ]
  }},

  "act": {{
    "tool": "tool_name",
    "params": {{
      "command": "precise command to execute"
    }},
    "safe": "Why this is safe/reversible (omit if obviously read-only)"
  }}
}}
```

---

## Critical Success Factors

1. **State is Your Memory**: All understanding must be externalized in the `state` object

2. **Facts vs. Inferences**: Keep `facts` for observations, `ruled_out` for disproven theories, `unknowns` for gaps

3. **One Action, One Hypothesis**: Each turn tests exactly one clear claim

4. **Learn from Failure**: When hypotheses fail, explicitly document what you've ruled out

5. **Track Progress**: If `active.turns ≥ 8` without progress → change strategy or escalate

6. **Verify Success**: Don't claim completion without evidence-based verification

7. **Safety First**: Backup before destruction, verify after modification

8. **Scope Correctly**: Systematic tasks need scripts, exploratory tasks use direct commands

9. **Chain Wisely**: Combine deterministic steps to minimize turns, but keep investigation steps separate to learn from each

10. **Ask When Stuck**: After ~3 fundamentally different failed approaches, escalate to user

---

## System-Specific Commands

{self._get_system_specific_commands()}

---

## Final Reminders

- **Be precise**: Vague hypotheses lead to ambiguous results
- **Be safe**: Always have a rollback plan for destructive operations  
- **Be efficient**: Minimize turns while maintaining rigor
- **Be honest**: State uncertainties explicitly, don't guess
- **Be adaptive**: If standard approaches aren't working, try first-principles thinking

**Your mission**: Achieve the goal reliably, safely, and efficiently. Execute the REACT loop with discipline and clarity.
"""

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
