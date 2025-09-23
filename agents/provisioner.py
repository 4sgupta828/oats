# agents/provisioner.py

import sys
import os
import time
import shutil
import importlib
import inspect
from typing import Dict, Any, List
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import get_logger
from core.llm import OpenAIClientManager
from reactor.models import ReActState, ScratchpadEntry, ParsedLLMResponse
from core.models import UFDescriptor
# Terminal colors for output formatting
class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

logger = get_logger('agents.provisioner')

class ToolProvisioningAgent:
    """
    Specialized agent for finding and installing tools.
    Operates its own ReAct loop focused solely on tool provisioning.
    """

    def __init__(self, registry=None, auto_mode=False):
        self.registry = registry  # Reference to main registry for dynamic updates
        self.llm_client = OpenAIClientManager()
        self.auto_mode = auto_mode  # Skip user confirmations when True
        # Limited toolset for provisioning - avoid circular dependencies
        self.available_tools = ["execute_shell", "check_command_exists", "user_confirm", "user_prompt", "ask_llm_for_instructions", "web_search_for_tool", "finish"]

    def run(self, goal: str, show_live_updates: bool = True, auto_mode: bool = None) -> dict:
        """
        Run the Tool Provisioning Agent's ReAct loop.

        Args:
            goal: High-level description of tool needed (e.g., "Find and install 'ruff' for Python linting")

        Returns:
            Structured result dictionary with success/failure info and alternatives
        """
        start_time = time.time()
        logger.info(f"Tool Provisioning Agent starting: {goal}")

        # Use auto_mode from parameter if provided, otherwise use instance setting
        if auto_mode is not None:
            self.auto_mode = auto_mode

        if show_live_updates:
            print(f"\n{Colors.BOLD}{Colors.BLUE}═══ TOOL PROVISIONING AGENT ═══{Colors.RESET}")
            print(f"{Colors.BOLD}Goal:{Colors.RESET} {goal}")
            auto_status = " (AUTO MODE)" if self.auto_mode else ""
            print(f"{Colors.YELLOW}🔧 Starting tool provisioning with live updates...{auto_status}{Colors.RESET}")

        # Initialize state with turn limit - allow up to 10 turns before requiring approval
        state = ReActState(goal=goal, max_turns=10)

        try:
            # Main provisioning loop
            while not state.is_complete:
                turn_start = time.time()
                turn_num = state.turn_count + 1

                # Check if we've exceeded max turns and need user confirmation
                if turn_num > state.max_turns:
                    if self.auto_mode:
                        if show_live_updates:
                            print(f"\n{Colors.YELLOW}⚠️  Reached maximum turns ({state.max_turns}). Auto mode: continuing...{Colors.RESET}")
                        logger.info("Auto mode: continuing past max turns")
                    else:
                        if show_live_updates:
                            print(f"\n{Colors.YELLOW}⚠️  Reached maximum turns ({state.max_turns}). Continue? (Y/n, Enter=Y): {Colors.RESET}", end="")
                            response = input().strip().lower()
                            if response in ['n', 'no']:
                                logger.info("Tool provisioning stopped by user after max turns")
                                break
                            # If Y, yes, or Enter (empty), continue

                logger.info(f"Provisioning turn {turn_num}/{state.max_turns}+" if turn_num > state.max_turns else f"Provisioning turn {turn_num}/{state.max_turns}")

                if show_live_updates:
                    turn_display = f"{turn_num}/{state.max_turns}+" if turn_num > state.max_turns else f"{turn_num}/{state.max_turns}"
                    print(f"\n{Colors.BOLD}{Colors.CYAN}┌─ Turn {turn_display} ─────────────────────────────────────────────────┐{Colors.RESET}")
                    print(f"{Colors.BOLD}│ Reasoning...                                              │{Colors.RESET}")
                    print(f"{Colors.BOLD}└───────────────────────────────────────────────────────────┘{Colors.RESET}")

                # Build specialized prompt for tool provisioning
                prompt = self._build_provisioner_prompt(state, goal)

                # Get LLM response
                raw_response = self.llm_client.create_completion_text([{"role": "user", "content": prompt}])

                # Parse response
                parsed_response = self._parse_provisioner_response(raw_response)

                if show_live_updates:
                    print(f"{Colors.YELLOW}💭 Thought:{Colors.RESET} {parsed_response.thought}")
                    print(f"{Colors.BLUE}🛠️  Action:{Colors.RESET} {parsed_response.action}")

                # Check for completion
                if parsed_response.is_finish:
                    logger.info("Tool provisioning agent indicated completion")

                    if show_live_updates:
                        print(f"\n{Colors.GREEN}🎉 Tool provisioning completed!{Colors.RESET}")
                        success = parsed_response.action.get('parameters', {}).get('success', False)
                        if success:
                            tool_name = parsed_response.action.get('parameters', {}).get('tool_name', 'unknown')
                            method = parsed_response.action.get('parameters', {}).get('installation_method', 'unknown')
                            print(f"{Colors.GREEN}✅ Successfully installed '{tool_name}' via {method}{Colors.RESET}")
                        else:
                            message = parsed_response.action.get('parameters', {}).get('message', 'Installation failed')
                            print(f"{Colors.RED}❌ {message}{Colors.RESET}")

                    # Return the finish result directly
                    result = parsed_response.action

                    # Ensure proper structure
                    if not isinstance(result, dict):
                        result = {"success": False, "message": "Invalid finish result"}

                    # Add execution metadata
                    result["execution_time"] = time.time() - start_time
                    result["turns_taken"] = state.turn_count + 1

                    return result

                # Check for potential loops before executing
                if self._detect_potential_loop(state, parsed_response.action):
                    logger.warning(f"Potential loop detected, forcing alternative approach")
                    observation = "LOOP_DETECTED: This command or similar has been tried before. You must try a completely different approach or finish with failure if no alternatives remain."
                    if show_live_updates:
                        print(f"{Colors.YELLOW}⚠️  Loop detected - forcing alternative approach{Colors.RESET}")
                else:
                    if show_live_updates:
                        print(f"{Colors.DIM}Executing action...{Colors.RESET}")
                    # Execute action
                    observation = self._execute_provisioner_action(parsed_response.action)

                if show_live_updates:
                    # Display observation with appropriate coloring
                    if observation.startswith("ERROR") or observation.startswith("FAILED"):
                        print(f"{Colors.RED}👀 Observation:{Colors.RESET} {observation}")
                    elif observation.startswith("SUCCESS"):
                        print(f"{Colors.GREEN}👀 Observation:{Colors.RESET} {observation}")
                    elif observation.startswith("LOOP_DETECTED"):
                        print(f"{Colors.YELLOW}👀 Observation:{Colors.RESET} {observation}")
                    else:
                        print(f"{Colors.CYAN}👀 Observation:{Colors.RESET} {observation}")

                # Add to scratchpad
                turn_duration = int((time.time() - turn_start) * 1000)
                scratchpad_entry = ScratchpadEntry(
                    turn=state.turn_count + 1,
                    thought=parsed_response.thought,
                    action=parsed_response.action,
                    observation=observation,
                    duration_ms=turn_duration
                )

                state.scratchpad.append(scratchpad_entry)
                state.turn_count += 1

                # Intelligent failure detection - if we've had multiple failures, suggest finishing
                if self._should_suggest_finishing(state):
                    logger.info("Multiple failures detected, will suggest finishing on next turn")
                    if show_live_updates:
                        print(f"{Colors.YELLOW}💡 Multiple failures detected - suggesting finish on next turn{Colors.RESET}")
                    observation += "\n\nSUGGESTION: Consider finishing with failure and providing alternatives after this many failed attempts."

            # If we exit the loop without completion, return timeout failure
            return {
                "success": False,
                "tool_name": None,
                "message": f"Tool installation timed out after {state.max_turns} turns",
                "error_type": "timeout",
                "execution_time": time.time() - start_time,
                "turns_taken": state.turn_count,
                "suggested_alternatives": self._suggest_alternatives(goal)
            }

        except Exception as e:
            logger.error(f"Tool Provisioning Agent error: {e}")
            return {
                "success": False,
                "tool_name": None,
                "message": f"Tool provisioning failed with error: {str(e)}",
                "error_type": "agent_error",
                "execution_time": time.time() - start_time,
                "suggested_alternatives": self._suggest_alternatives(goal)
            }

    def _build_provisioner_prompt(self, state: ReActState, goal: str) -> str:
        """Build specialized prompt for tool provisioning."""

        # Build history if any
        history = ""
        if state.scratchpad:
            history_parts = ["PREVIOUS ATTEMPTS:"]
            for entry in state.scratchpad:
                history_parts.extend([
                    f"Turn {entry.turn}:",
                    f"Thought: {entry.thought}",
                    f"Action: {entry.action}",
                    f"Observation: {entry.observation[:500]}{'...' if len(entry.observation) > 500 else ''}",
                    ""
                ])
            history = "\n".join(history_parts)

        prompt = f"""You are a specialized Tool Provisioning Agent. Your ONLY job is to find and install the requested tool.

GOAL: {goal}

AVAILABLE ACTIONS:
1. execute_shell - Run shell commands to install tools
2. check_command_exists - Verify if a tool is already installed
3. user_confirm - Ask user for permission before risky operations (auto-approved in auto mode)
4. user_prompt - Ask user for guidance when stuck or need information
5. ask_llm_for_instructions - Get installation instructions from LLM for a specific tool and platform
6. web_search_for_tool - Search web for tool installation troubleshooting or alternatives
7. finish - Complete the task with structured results

RESPONSE FORMAT (MANDATORY):
Thought: [Your reasoning]
Intent: provision_tool
Action: {{"tool_name": "action_name", "parameters": {{"param": "value"}}}}

RULES:
1. Always include Thought, Intent, and Action lines
2. Intent must always be "provision_tool" for this agent
3. Action must be valid JSON with double quotes only
4. No single quotes, no trailing commas, no extra text after JSON
5. Parameters must be a JSON object, even if empty

EXAMPLES:
Thought: Checking if tool exists
Intent: provision_tool
Action: {{"tool_name": "check_command_exists", "parameters": {{"command_name": "rg"}}}}

Thought: Need permission to install system packages
Intent: provision_tool
Action: {{"tool_name": "user_confirm", "parameters": {{"message": "Install ripgrep via homebrew (requires system changes)?", "default_yes": true}}}}

Thought: Installing the tool
Intent: provision_tool
Action: {{"tool_name": "execute_shell", "parameters": {{"command": "brew install ripgrep"}}}}

Thought: Need to understand what type of tool this is and correct installation method
Intent: provision_tool
Action: {{"tool_name": "ask_llm_for_instructions", "parameters": {{"tool_name": "scrubcsv", "platform": "macOS"}}}}

Thought: LLM instructions failed, searching web for installation alternatives
Intent: provision_tool
Action: {{"tool_name": "web_search_for_tool", "parameters": {{"tool_name": "reconcile-csv", "query": "reconcile-csv installation rust crates"}}}}

Thought: Multiple installation methods failed, need user guidance
Intent: provision_tool
Action: {{"tool_name": "user_prompt", "parameters": {{"question": "Failed to install via pip, brew, and apt. Do you have a preferred package manager or should I try building from source?"}}}}


Thought: Task completed successfully
Intent: provision_tool
Action: {{"tool_name": "finish", "parameters": {{"success": true, "tool_name": "ripgrep", "message": "Installed via brew"}}}}

INSTALLATION STRATEGIES (try in order):
1. First check if tool already exists with check_command_exists
2. **ASK PERMISSION** before system changes with user_confirm (automatically approved in auto mode)
3. Package managers (prioritize by OS): macOS=brew, Linux=apt/yum, Windows=chocolatey
4. **CLI applications**: pipx install (preferred for Python CLI tools like radon, black, flake8)
5. Language-specific managers: Python=pip/pip3 (only for project dependencies in venv), Node=npm/yarn, Rust=cargo
6. Alternative package names: try common variations (xsv vs rust-xsv)
7. **IF STANDARD METHODS FAIL**: Use ask_llm_for_instructions to get tool-specific installation knowledge
8. **IF LLM INSTRUCTIONS FAIL**: Use web_search_for_tool to find troubleshooting info and alternatives
9. **ASK FOR GUIDANCE** if still stuck with user_prompt
10. Direct downloads or source compilation as last resort
11. Finish with failure and suggest alternatives if all methods fail

IMPORTANT RULES:
- ALWAYS start by checking if tool already exists with check_command_exists
- **CHOOSE INSTALLATION METHOD WISELY**:
  • CLI tools (radon, black, flake8, pylint, etc.) → Use pipx install
  • Project dependencies (libraries) → Use pip install in venv
  • System tools → Use brew/apt/package manager
- **ENVIRONMENT RULES**:
  • Virtual environment is automatically created at agent startup
  • Use pip install (in venv) for project dependencies only
  • Never use --user --break-system-packages (venv handles isolation)
- **LLM KNOWLEDGE GATHERING & WEB SEARCH**:
  • Use ask_llm_for_instructions when standard package managers fail
  • If LLM instructions fail or return no results, use web_search_for_tool for troubleshooting
  • Web search can identify common issues (wrong tool type, package not published, etc.)
  • Extract tool name from goal and current platform info for queries
- **USER INTERACTION RULES**:
  • Use user_confirm BEFORE installing packages (system changes need permission)
  • Use ask_llm_for_instructions BEFORE user_prompt when installations fail
  • Use user_prompt AFTER LLM instructions fail (ask for guidance/preferences)
  • Use user_prompt when multiple approaches exist (let user choose)
  • Use user_prompt for missing info (API tokens, custom repos, etc.)
- Some packages provide multiple commands (e.g., csvkit provides csvcut, csvstat, csvlook, csvgrep)
- The check_command_exists tool is smart - use the package name and it will check for all relevant commands
- Detect OS to prioritize correct package managers (macOS=brew, Linux=apt/yum)
- Try package variations if base name fails (e.g., 'xsv' then 'rust-xsv')
- For Python tools: try 'pip install' then 'pip3 install' then 'pip install --user'
- Verify installation by re-checking command exists after install attempt using the PACKAGE NAME
- Finish early with success when tool is found/installed successfully
- After 2-3 different installation attempts fail, use ask_llm_for_instructions to get tool-specific knowledge
- If LLM instructions also fail, then ask user for guidance before giving up

LOOP PREVENTION - CRITICAL:
- NEVER repeat the exact same command that failed before
- Learn from PREVIOUS ATTEMPTS: if 'pip install xsv' failed, try 'brew install xsv' not 'pip install xsv' again
- Try systematic variations: different package managers, different package names, different flags
- Package name variations: tool → py-tool → python-tool → tool-cli → rust-tool
- If 2+ attempts with same package manager failed, switch to different manager
- If installation fails but should succeed, check if command now exists anyway

COMMON TOOL INSTALLATION PATTERNS:
- Rust tools (scrubcsv, ripgrep, fd, exa, bat): brew install rust && cargo install <tool>
- Go tools: go install github.com/author/<tool>@latest
- Node tools: npm install -g <tool>
- Python tools with system deps: brew install <deps> && pip install <tool>
- Tools with custom installers: curl <url> | sh
- Language-specific package managers often work better than system ones

FINISH ACTION STRUCTURE:
Success: {{"tool_name": "finish", "parameters": {{"success": true, "tool_name": "<name>", "installation_method": "<method>", "message": "<details>", "tool_path": "<path>", "verification_command": "<cmd>"}}}}

Failure: {{"tool_name": "finish", "parameters": {{"success": false, "tool_name": "<name>", "message": "<error_details>", "error_type": "<type>", "attempted_methods": ["<method1>", "<method2>"], "suggested_alternatives": ["<alt1>", "<alt2>"], "fallback_commands": ["<cmd1>", "<cmd2>"]}}}}

{history}

CURRENT TURN {state.turn_count + 1}:
What should you do next to install the requested tool?

Your response:"""

        return prompt

    def _parse_provisioner_response(self, raw_response: str) -> ParsedLLMResponse:
        """Parse Tool Provisioning Agent response using unified ReAct parser."""
        try:
            logger.debug(f"Parsing response: {raw_response[:100]}...")

            # Check for common LLM refusal patterns first
            if self._is_llm_refusal(raw_response):
                logger.warning(f"LLM refusal detected: {raw_response[:200]}")
                return self._handle_llm_refusal(raw_response)

            # Use the same parser as the goal-oriented ReAct agent
            from reactor.agent_controller import AgentController

            # Create a temporary agent controller to use its parser
            temp_controller = AgentController(None)  # Registry not needed for parsing
            return temp_controller._parse_llm_response(raw_response)

        except Exception as e:
            logger.error(f"Parse error: {e}")
            return ParsedLLMResponse(
                thought="Parse error occurred",
                action={"tool_name": "error", "parameters": {"error": str(e)}},
                is_finish=False,
                raw_response=raw_response
            )

    def _is_llm_refusal(self, response: str) -> bool:
        """Check if the response is an LLM refusal."""
        refusal_patterns = [
            "i'm sorry, but i can't assist",
            "i cannot assist",
            "i'm unable to help",
            "i can't help with that",
            "i cannot help with that",
            "that's not something i can help with"
        ]

        response_lower = response.lower().strip()
        return any(pattern in response_lower for pattern in refusal_patterns)

    def _handle_llm_refusal(self, raw_response: str) -> ParsedLLMResponse:
        """Handle LLM refusal by suggesting to finish with failure."""
        return ParsedLLMResponse(
            thought="LLM refused to respond in expected format, likely due to content filtering or prompt confusion",
            action={
                "tool_name": "finish",
                "parameters": {
                    "success": False,
                    "message": "Tool installation failed due to LLM response issues. The model may have misinterpreted the request.",
                    "error_type": "llm_refusal",
                    "suggested_alternatives": [
                        "Try installing the tool manually using system package manager",
                        "Search for the tool on GitHub or official documentation",
                        "Check if the tool name is spelled correctly"
                    ]
                }
            },
            is_finish=True,
            raw_response=raw_response
        )



    def _execute_provisioner_action(self, action: Dict[str, Any]) -> str:
        """Execute a provisioner action."""
        tool_name = action.get("tool_name")
        parameters = action.get("parameters", {})

        try:
            if tool_name == "execute_shell":
                return self._execute_shell_action(parameters)
            elif tool_name == "check_command_exists":
                return self._execute_check_command_action(parameters)
            elif tool_name == "user_confirm":
                return self._execute_user_confirm_action(parameters)
            elif tool_name == "user_prompt":
                return self._execute_user_prompt_action(parameters)
            elif tool_name == "ask_llm_for_instructions":
                return self._execute_ask_llm_for_instructions_action(parameters)
            elif tool_name == "web_search_for_tool":
                return self._execute_web_search_for_tool_action(parameters)
            elif tool_name == "finish":
                # Finish actions are handled at the loop level
                return f"FINISH: {parameters}"
            else:
                return f"ERROR: Unknown action '{tool_name}'"

        except Exception as e:
            logger.error(f"Error executing action {tool_name}: {e}")
            return f"ERROR: Action execution failed: {str(e)}"

    def _execute_shell_action(self, parameters: Dict[str, Any]) -> str:
        """Execute shell command for provisioner."""
        import subprocess

        command = parameters.get("command", "")
        if not command:
            return "ERROR: No command provided"

        # Python environment setup now handled at agent startup

        try:
            logger.info(f"Provisioner executing: {command}")

            # Display command line for transparency like react agent
            print(f"💻 Command: {command}")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for installations
            )

            output_parts = []
            if result.stdout:
                output_parts.append(f"stdout: {result.stdout[:1000]}")
            if result.stderr:
                output_parts.append(f"stderr: {result.stderr[:1000]}")

            status = "SUCCESS" if result.returncode == 0 else "FAILED"
            output_parts.append(f"return_code: {result.returncode}")

            return f"{status}: {' | '.join(output_parts)}"

        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 2 minutes"
        except Exception as e:
            return f"ERROR: Command execution failed: {str(e)}"

    def _execute_check_command_action(self, parameters: Dict[str, Any]) -> str:
        """Execute command existence check for provisioner."""
        command_name = parameters.get("command_name", "")
        if not command_name:
            return "ERROR: No command_name provided"

        # Always use simple shutil.which check - don't rely on LLM guessing commands
        # The complex goal-aware approach was causing false positives where LLM would
        # incorrectly identify standard Unix commands (join, write) as belonging to csvfix
        path = shutil.which(command_name)
        if path:
            return f"SUCCESS: Command '{command_name}' found at: {path}"
        else:
            return f"NOT_FOUND: Command '{command_name}' not available on system"

    def _parse_goal(self, goal: str) -> dict:
        """Parse goal in format 'I need [tool] to do [purpose]' or 'I need any tool to do [purpose]'."""
        import re

        # Pattern: "I need <tool> to do <purpose>" or "I need any tool to do <purpose>"
        pattern = r"I need (?P<tool>[\w\-]+|any tool) to (?:do )?(?P<purpose>.*)"
        match = re.search(pattern, goal, re.IGNORECASE)

        if match:
            tool = match.group("tool")
            purpose = match.group("purpose").strip()
            return {
                "tool": None if tool.lower() == "any tool" else tool,
                "purpose": purpose,
                "raw_goal": goal
            }

        # Fallback: try to extract from free-form goal
        if "to do" in goal.lower():
            parts = goal.lower().split("to do", 1)
            if len(parts) == 2:
                return {"tool": None, "purpose": parts[1].strip(), "raw_goal": goal}

        return {"tool": None, "purpose": goal, "raw_goal": goal}


    def _execute_user_confirm_action(self, parameters: Dict[str, Any]) -> str:
        """Execute user confirmation for provisioner."""
        from tools.file_system import user_confirm, UserConfirmInput

        try:
            # In auto mode, automatically approve all confirmations
            if self.auto_mode:
                message = parameters.get("message", "Proceed?")
                logger.info(f"Auto mode: automatically approving: {message}")
                return f"AUTO_CONFIRMED: {message}"

            inputs = UserConfirmInput(
                message=parameters.get("message", "Proceed?"),
                default_yes=parameters.get("default_yes", True)
            )
            result = user_confirm(inputs)

            if result["confirmed"]:
                return f"USER_CONFIRMED: {result['message']}"
            else:
                return f"USER_DENIED: {result['message']}"

        except Exception as e:
            logger.error(f"User confirm action failed: {e}")
            return f"ERROR: User confirmation failed: {str(e)}"

    def _execute_user_prompt_action(self, parameters: Dict[str, Any]) -> str:
        """Execute user prompt for provisioner."""
        from tools.file_system import user_prompt, UserPromptInput

        try:
            inputs = UserPromptInput(
                question=parameters.get("question", "Need guidance - what should I do?")
            )
            result = user_prompt(inputs)

            if result["action"] == "abort":
                return f"USER_ABORT: {result['message']}"
            elif result["action"] == "stop":
                return f"USER_STOP: {result['message']}"
            elif result["action"] == "skip":
                return f"USER_SKIP: {result['message']}"
            else:
                return f"USER_RESPONSE: {result['response']}"

        except Exception as e:
            logger.error(f"User prompt action failed: {e}")
            return f"ERROR: User prompt failed: {str(e)}"

    def _execute_ask_llm_for_instructions_action(self, parameters: Dict[str, Any]) -> str:
        """Ask LLM for tool-specific installation instructions."""
        try:
            tool_name = parameters.get("tool_name", "")
            platform = parameters.get("platform", "")

            if not tool_name:
                return "ERROR: No tool_name provided"

            # Detect platform if not provided
            if not platform:
                import platform as plat
                system = plat.system().lower()
                if system == "darwin":
                    platform = "macOS"
                elif system == "linux":
                    platform = "Linux"
                elif system == "windows":
                    platform = "Windows"
                else:
                    platform = system

            prompt = f"""How to install tool '{tool_name}' - give me step by step shell commands for platform {platform}

Tool: {tool_name}
Platform: {platform}

Provide ONLY the shell commands needed to install this tool, one command per line.
Consider these installation patterns:

RUST TOOLS (like scrubcsv, ripgrep, fd, exa):
- First install Rust: brew install rust (macOS) or curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
- Then: cargo install {tool_name}

GO TOOLS:
- go install github.com/author/{tool_name}@latest

NODE TOOLS:
- npm install -g {tool_name}

PYTHON CLI TOOLS (radon, black, flake8, pylint):
- pipx install {tool_name} (preferred for CLI tools)

PYTHON LIBRARIES/DEPENDENCIES:
- pip install {tool_name} (only in virtual environment)

NATIVE PACKAGES:
- macOS: brew install {tool_name}
- Linux: apt install {tool_name} or yum install {tool_name}
- Windows: choco install {tool_name}

TOOLS WITH SYSTEM DEPENDENCIES:
- Install dependencies first, then the tool

Return only the commands, no explanations. If unsure about the tool, provide the most likely installation method."""

            logger.info(f"Asking LLM for installation instructions for {tool_name} on {platform}")

            response = self.llm_client.create_completion_text([{"role": "user", "content": prompt}])

            # Clean up the response to extract commands
            commands = []
            for line in response.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('//'):
                    # Remove common prefixes that might be in the response
                    if line.startswith('$ '):
                        line = line[2:]
                    elif line.startswith('> '):
                        line = line[2:]
                    if line:
                        commands.append(line)

            if commands:
                command_list = '\n'.join(commands)
                return f"LLM_INSTRUCTIONS: Installation commands for {tool_name} on {platform}:\n{command_list}"
            else:
                return f"LLM_NO_INSTRUCTIONS: Could not determine installation method for {tool_name}"

        except Exception as e:
            logger.error(f"LLM instructions action failed: {e}")
            return f"ERROR: LLM instructions failed: {str(e)}"

    def _execute_web_search_for_tool_action(self, parameters: Dict[str, Any]) -> str:
        """Search web for tool installation troubleshooting or alternatives."""
        try:
            tool_name = parameters.get("tool_name", "")

            if not tool_name:
                return "ERROR: No tool_name provided"

            logger.info(f"Searching web for: {tool_name}")

            # For now, return a structured response that simulates what web search would find
            # In a real implementation, you'd integrate with search APIs
            search_results = self._simulate_web_search_results(tool_name, parameters.get("query", ""))

            return f"WEB_SEARCH_RESULTS: {search_results}"

        except Exception as e:
            logger.error(f"Web search action failed: {e}")
            return f"ERROR: Web search failed: {str(e)}"

    def _simulate_web_search_results(self, tool_name: str, query: str) -> str:
        """Enhanced web search with both simulated and basic real search capabilities."""

        # First, check if we have a known pattern for this tool
        result = self._check_known_tool_patterns(tool_name)
        if result:
            return result

        # For unknown tools, try a basic web search approach
        try:
            return self._perform_basic_web_search(tool_name, query)
        except Exception as e:
            logger.warning(f"Real web search failed, using fallback: {e}")
            return self._get_generic_search_advice(tool_name)

    def _check_known_tool_patterns(self, tool_name: str) -> str:
        """Check against database of known problematic tools."""
        common_issues = {
            "reconcile-csv": {
                "issue": "Tool is Java-based, not available via Cargo",
                "alternatives": [
                    "Use qsv (Rust CSV toolkit): cargo install qsv",
                    "Use csv-diff (Rust CSV comparison): cargo install csv-diff",
                    "Download original Java version from GitHub"
                ],
                "original_location": "https://github.com/rufuspollock-okfn/reconcile-csv"
            },
            "scrubcsv": {
                "issue": "Tool may not be published to crates.io",
                "alternatives": [
                    "Use csvkit (Rust): cargo install csvkit",
                    "Use qsv for CSV processing: cargo install qsv",
                    "Build from source if GitHub repo exists"
                ]
            }
        }

        tool_lower = tool_name.lower()
        for pattern, info in common_issues.items():
            if pattern in tool_lower or tool_lower in pattern:
                result = f"Found common issue: {info['issue']}. "
                result += f"Alternatives: {'; '.join(info['alternatives'])}"
                if 'original_location' in info:
                    result += f". Original tool: {info['original_location']}"
                return result
        return None

    def _perform_basic_web_search(self, tool_name: str, query: str) -> str:
        """Perform basic web search using DuckDuckGo (no API key required)."""
        try:
            import requests
            from urllib.parse import quote

            # Use custom query if provided, otherwise default to tool installation
            search_query = query if query.strip() else f"{tool_name} installation"
            url = f"https://api.duckduckgo.com/?q={quote(search_query)}&format=json&no_html=1"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Extract useful information from the response
            results = []

            if data.get('Abstract'):
                results.append(f"Info: {data['Abstract'][:200]}...")

            if data.get('AbstractURL'):
                results.append(f"Source: {data['AbstractURL']}")

            # Check for related topics
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:3]:  # Limit to 3 related topics
                    if isinstance(topic, dict) and topic.get('Text'):
                        results.append(f"Related: {topic['Text'][:100]}...")

            if results:
                return f"Web search found: {' | '.join(results)}"
            else:
                return self._get_generic_search_advice(tool_name)

        except Exception as e:
            logger.debug(f"Web search API failed: {e}")
            raise e

    def _get_generic_search_advice(self, tool_name: str) -> str:
        """Return generic search advice when specific information isn't available."""
        return (f"Web search suggests checking: "
                f"1) GitHub repositories for {tool_name}, "
                f"2) Alternative package names (rust-{tool_name}, {tool_name}-cli), "
                f"3) Language-specific package managers, "
                f"4) Building from source")

    def refresh_registry_for_tool(self, tool_name: str):
        """Attempt to discover and register a newly installed tool."""
        if not self.registry:
            logger.warning("No registry reference available for tool registration")
            return

        logger.info(f"Attempting to refresh registry for tool: {tool_name}")

        # Strategy 1: Check if it's a Python package with UF decorators
        try:
            module = importlib.import_module(tool_name)
            descriptors = self._scan_module_for_ufs(module)
            for desc in descriptors:
                self.registry.register_uf(desc)
                logger.info(f"Registered newly installed UF: {desc.name}")
        except ImportError:
            logger.debug(f"Tool '{tool_name}' is not a Python module")

        # Strategy 2: Create a shell command wrapper UF if command is available
        if shutil.which(tool_name):
            try:
                shell_wrapper_uf = self._create_shell_wrapper_uf(tool_name)
                self.registry.register_uf(shell_wrapper_uf)
                logger.info(f"Created shell wrapper UF for: {tool_name}")
            except Exception as e:
                logger.warning(f"Failed to create shell wrapper for {tool_name}: {e}")

    def _scan_module_for_ufs(self, module) -> List[UFDescriptor]:
        """Scan a module for functions decorated with @uf."""
        descriptors = []

        try:
            for _, func in inspect.getmembers(module, inspect.isfunction):
                if hasattr(func, '_uf_descriptor'):
                    descriptor = getattr(func, '_uf_descriptor')
                    if isinstance(descriptor, UFDescriptor):
                        descriptor.callable_func = func
                        descriptors.append(descriptor)
        except Exception as e:
            logger.warning(f"Error scanning module for UFs: {e}")

        return descriptors

    def _create_shell_wrapper_uf(self, tool_name: str) -> UFDescriptor:
        """Create a shell wrapper UF for a command-line tool."""

        # Create a dynamic UF descriptor
        descriptor = UFDescriptor(
            name=f"{tool_name}_shell",
            version="1.0.0",
            description=f"Shell wrapper for {tool_name} command",
            input_schema={
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": f"Arguments to pass to {tool_name}"
                    }
                },
                "required": ["args"]
            }
        )

        # Create a wrapper function
        def shell_wrapper(inputs):
            import subprocess
            command = f"{tool_name} {inputs.get('args', '')}"
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode,
                    "success": result.returncode == 0
                }
            except Exception as e:
                return {"error": str(e), "success": False}

        descriptor.callable_func = shell_wrapper
        return descriptor

    def _suggest_alternatives(self, goal: str) -> List[str]:
        """Suggest alternative approaches when tool installation fails."""
        alternatives = []
        goal_lower = goal.lower()

        # Pattern-based suggestions
        if any(word in goal_lower for word in ["linting", "lint", "ruff", "flake8", "pylint"]):
            alternatives.extend([
                "Use Python's built-in ast module for syntax checking",
                "Implement custom linting with grep patterns for common issues",
                "Use your IDE's built-in linting features"
            ])
        elif any(word in goal_lower for word in ["formatting", "format", "black", "autopep8"]):
            alternatives.extend([
                "Use manual formatting following PEP 8 guidelines",
                "Use simple string manipulation for basic formatting",
                "Apply formatting rules with sed/awk commands"
            ])
        elif any(word in goal_lower for word in ["testing", "test", "pytest", "unittest"]):
            alternatives.extend([
                "Use Python's built-in unittest module",
                "Write custom test scripts with assert statements",
                "Create simple validation scripts"
            ])
        elif any(word in goal_lower for word in ["package", "dependency", "install"]):
            alternatives.extend([
                "Download and install manually from source",
                "Use alternative package managers",
                "Find equivalent tools already available"
            ])
        else:
            alternatives.extend([
                "Use built-in system tools for similar functionality",
                "Implement custom scripts to achieve the same goal",
                "Search for alternative tools with similar features"
            ])

        return alternatives[:3]  # Limit to top 3 suggestions

    def _detect_potential_loop(self, state: ReActState, new_action: Dict[str, Any]) -> bool:
        """Detect if the agent is about to repeat a failed command or approach."""
        if not state.scratchpad:
            return False

        new_tool = new_action.get("tool_name")
        new_params = new_action.get("parameters", {})

        # For shell commands, check if we're repeating the same or very similar command
        if new_tool == "execute_shell":
            new_command = new_params.get("command", "").lower().strip()

            if not new_command:
                return False

            # Count recent failed attempts with this package manager
            package_manager_failures = self._count_package_manager_failures(state, new_command)
            if package_manager_failures >= 2:
                logger.debug(f"Too many failures with this package manager: {new_command}")
                return True

            # Check against previous shell commands for exact repeats
            for entry in state.scratchpad:
                if entry.action.get("tool_name") == "execute_shell":
                    prev_command = entry.action.get("parameters", {}).get("command", "").lower().strip()

                    # Exact match - always block
                    if new_command == prev_command:
                        logger.debug(f"Exact command repeat detected: {new_command}")
                        return True

                    # Similar commands only if both failed
                    prev_failed = entry.observation and ("ERROR" in entry.observation or "FAILED" in entry.observation)
                    if prev_failed and self._commands_too_similar(new_command, prev_command):
                        logger.debug(f"Similar failed command detected: {new_command} vs {prev_command}")
                        return True

        # Check for repeated check_command_exists - more lenient (allow 3 checks)
        elif new_tool == "check_command_exists":
            new_cmd_name = new_params.get("command_name", "").lower()
            check_count = sum(1 for entry in state.scratchpad
                            if entry.action.get("tool_name") == "check_command_exists"
                            and entry.action.get("parameters", {}).get("command_name", "").lower() == new_cmd_name)

            if check_count >= 3:  # Allow up to 3 checks for variations
                logger.debug(f"Too many tool checks detected: {new_cmd_name}")
                return True

        return False

    def _count_package_manager_failures(self, state: ReActState, command: str) -> int:
        """Count recent failures with the same package manager."""
        import re

        # Extract package manager from command
        pm_match = re.search(r'^(pip|pip3|brew|apt|apt-get|yum|npm|yarn)\b', command)
        if not pm_match:
            return 0

        package_manager = pm_match.group(1)
        failure_count = 0

        # Count recent failures with this package manager
        for entry in state.scratchpad[-3:]:  # Only check last 3 attempts
            if entry.action.get("tool_name") == "execute_shell":
                prev_cmd = entry.action.get("parameters", {}).get("command", "")
                if prev_cmd.startswith(package_manager) and entry.observation:
                    if "ERROR" in entry.observation or "FAILED" in entry.observation:
                        failure_count += 1

        return failure_count

    def _commands_too_similar(self, cmd1: str, cmd2: str) -> bool:
        """Check if two shell commands are too similar (indicating potential loop)."""
        # Extract key components from commands
        import re

        # Common package managers
        package_managers = ["pip", "pip3", "brew", "apt", "apt-get", "yum", "npm", "yarn"]

        for pm in package_managers:
            # Check if both commands use same package manager and same base package name
            pattern = rf"{pm}\s+install\s+([^\s]+)"

            match1 = re.search(pattern, cmd1)
            match2 = re.search(pattern, cmd2)

            if match1 and match2:
                package1 = match1.group(1).strip()
                package2 = match2.group(1).strip()

                # Same package manager + same package = too similar
                if package1 == package2:
                    return True

                # Very similar package names (but allow some legitimate variations)
                if self._package_names_similar(package1, package2):
                    return True

            # Same package manager but different packages = different approach (OK)
            elif match1 and match2:
                return False

        return False

    def _package_names_similar(self, pkg1: str, pkg2: str) -> bool:
        """Check if package names are very similar."""
        # Remove common variations
        clean1 = pkg1.lower().replace("-", "").replace("_", "").replace("python", "").replace("py", "")
        clean2 = pkg2.lower().replace("-", "").replace("_", "").replace("python", "").replace("py", "")

        # If one is substring of another and they're close in length
        if clean1 in clean2 or clean2 in clean1:
            length_diff = abs(len(clean1) - len(clean2))
            if length_diff <= 2:  # Very close in length
                return True

        return False

    def _should_suggest_finishing(self, state: ReActState) -> bool:
        """Determine if we should suggest finishing due to repeated failures."""
        if len(state.scratchpad) < 2:
            return False

        # Count recent failures (more aggressive - shorter limit)
        recent_failures = 0
        installation_attempts = 0

        for entry in state.scratchpad[-4:]:  # Last 4 attempts
            observation = entry.observation.upper()
            action = entry.action

            # Count installation attempts vs checks
            if action.get("tool_name") == "execute_shell":
                command = action.get("parameters", {}).get("command", "")
                if any(pm in command for pm in ["install", "brew", "pip", "apt", "yum", "npm"]):
                    installation_attempts += 1

            # Count failures
            if any(keyword in observation for keyword in ["ERROR", "FAILED", "NOT FOUND", "COMMAND NOT FOUND", "PERMISSION DENIED", "LOOP_DETECTED"]):
                recent_failures += 1

        # Suggest finishing if:
        # - 3+ total failures, OR
        # - 2+ installation attempts failed, OR
        # - More than 4 total turns taken
        return (recent_failures >= 3 or
                (installation_attempts >= 2 and recent_failures >= 2) or
                len(state.scratchpad) >= 4)

    def _analyze_failure_patterns(self, state: ReActState) -> List[str]:
        """Analyze failure patterns to suggest better approaches."""
        patterns = []

        for entry in state.scratchpad:
            observation = entry.observation.upper()
            action = entry.action

            if "PERMISSION DENIED" in observation:
                patterns.append("permission_issues")
            elif "COMMAND NOT FOUND" in observation or "NOT FOUND" in observation:
                patterns.append("missing_package_manager")
            elif "NO SUCH FILE" in observation:
                patterns.append("wrong_package_name")
            elif "NETWORK" in observation or "TIMEOUT" in observation:
                patterns.append("network_issues")
            elif action.get("tool_name") == "execute_shell" and "pip" in str(action.get("parameters", {})):
                if "ERROR" in observation:
                    patterns.append("pip_failed")

        return list(set(patterns))  # Remove duplicates

