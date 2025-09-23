#!/usr/bin/env python3
"""
Interactive UFFLOW React Framework with Goal Creation and Execution

This enhanced CLI allows you to:
1. Create goals interactively
2. Run ReAct executions with live reasoning display
3. Explore results with the CLI UI
4. All in one interactive session using the new ReAct framework

Usage:
    python interactive_ufflow_react.py
"""

import sys
import os
import json
import argparse
from typing import Dict, Any
from datetime import datetime
import shutil

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))

# Import UFFLOW components
from core.models import Goal
from core.logging_config import get_logger
from registry.main import global_registry
from reactor.agent_controller import AgentController
from reactor.models import ReActResult

# Initialize logger
logger = get_logger('interactive_ufflow_react')
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

class InteractiveUFFLOWReact:
    """Interactive UFFLOW React framework with goal creation and execution."""

    def __init__(self, fast_mode=False):
        self.registry = None
        self.agent_controller = None
        self.current_goal = None
        self.current_execution = None
        self.execution_history = []
        self.terminal_width = shutil.get_terminal_size().columns
        self.fast_mode = fast_mode

    def setup_ufflow(self):
        """Setup UFFLOW environment."""
        print(f"{Colors.CYAN}🔧 Setting up UFFLOW React environment...{Colors.RESET}")

        try:
            # Load tools
            global_registry.load_ufs_from_directory('./tools')
            self.registry = global_registry

            # Create ReAct agent controller
            self.agent_controller = AgentController(self.registry)

            available_tools = self.registry.list_ufs()
            print(f"{Colors.GREEN}✅ Loaded {len(available_tools)} tools:{Colors.RESET}")
            for tool in available_tools:
                print(f"   - {tool}")

            return True
        except Exception as e:
            print(f"{Colors.RED}❌ Error setting up UFFLOW: {e}{Colors.RESET}")
            return False

    def _get_robust_input(self, prompt: str) -> str:
        """Get robust input that handles long text and potential truncation issues."""
        # Use multiline mode by default
        print(prompt)
        return self._get_multiline_input()

    def _get_multiline_input(self) -> str:
        """Get multiline input using readline for better key handling."""
        print(f"{Colors.YELLOW}Multiline mode: Enter your text. Press Enter on empty line to finish.{Colors.RESET}")
        print(f"{Colors.DIM}(You can paste long text and press Enter to finish){Colors.RESET}")

        lines = []
        try:
            while True:
                try:
                    line = input()
                    if line.strip() == "":
                        # Empty line - finish input
                        break
                    lines.append(line)
                except EOFError:
                    break

            result = '\n'.join(lines).strip()
            print(f"{Colors.GREEN}✅ Received {len(result)} characters{Colors.RESET}")
            return result

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Input cancelled{Colors.RESET}")
            return ""

    def create_goal_interactive(self):
        """Create a goal interactively."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ CREATE NEW GOAL ═══{Colors.RESET}")

        # Get goal description
        print(f"\n{Colors.YELLOW}Enter your goal description:{Colors.RESET}")
        print(f"{Colors.DIM}Example: 'Create a file called test.txt with Hello World and read it back'{Colors.RESET}")
        print(f"{Colors.DIM}Enter your text, then press Enter on empty line to finish{Colors.RESET}")

        description = self._get_robust_input(f"\n{Colors.CYAN}Goal> {Colors.RESET}")

        if not description:
            print(f"{Colors.RED}❌ Goal description cannot be empty{Colors.RESET}")
            return None

        constraints = {}

        # Skip constraints prompt in FAST mode and auto-set CWD
        if not self.fast_mode:
            # Get constraints (optional for ReAct)
            print(f"\n{Colors.YELLOW}Enter constraints (JSON format, or press Enter for empty):{Colors.RESET}")
            print(f"{Colors.DIM}Example: {{\"max_turns\": 20, \"workspace\": \"/tmp\"}}{Colors.RESET}")
            constraints_input = self._get_robust_input(f"\n{Colors.CYAN}Constraints> {Colors.RESET}")

            if constraints_input:
                try:
                    constraints = json.loads(constraints_input)
                except json.JSONDecodeError as e:
                    print(f"{Colors.RED}❌ Invalid JSON format: {e}{Colors.RESET}")
                    print(f"{Colors.YELLOW}Using empty constraints{Colors.RESET}")
        else:
            # Auto-set workspace to current working directory in FAST mode
            current_dir = os.getcwd()
            constraints = {
                "workspace": current_dir,
                "max_turns": 10
            }
            print(f"\n{Colors.BLUE}🚀 FAST mode: Auto-setting constraints{Colors.RESET}")
            print(f"{Colors.BLUE}   • workspace: {current_dir}{Colors.RESET}")
            print(f"{Colors.BLUE}   • max_turns: 10{Colors.RESET}")

        # Create goal
        goal_id = f"react-goal-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        goal = Goal(
            id=goal_id,
            description=description,
            constraints=constraints
        )

        print(f"\n{Colors.GREEN}✅ Goal created successfully!{Colors.RESET}")
        print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {goal.id}")
        print(f"{Colors.BOLD}Description:{Colors.RESET} {goal.description}")
        if constraints:
            print(f"{Colors.BOLD}Constraints:{Colors.RESET} {json.dumps(constraints, indent=2)}")

        return goal

    def create_goal_from_template(self):
        """Create a goal from predefined templates."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ GOAL TEMPLATES ═══{Colors.RESET}")

        templates = {
            "1": {
                "name": "File Operations",
                "description": "Create a file named 'hello.txt' with content 'Hello, ReAct World!' and then read it back to verify",
                "constraints": {}
            },
            "2": {
                "name": "Log Analysis",
                "description": "search for all ERROR lines in log file and extract the log line that would be emitted by code and then search for all places in code where that line is emitted",
                "constraints": {
                    "log_file": "/path/to/your/logfile.log",
                    "code_directory": "/path/to/your/source/code",
                    "file_extensions": [".java", ".js", ".py", ".ts", ".go"],
                    "output_format": "json"
                }
            },
            "3": {
                "name": "Code Analysis",
                "description": "analyze source code files, identify patterns, and generate a summary report with findings",
                "constraints": {
                    "source_directory": "/path/to/source/code",
                    "analysis_type": "complexity",
                    "output_format": "markdown"
                }
            },
            "4": {
                "name": "Data Processing",
                "description": "process data files, transform content, and generate output with validation",
                "constraints": {
                    "input_file": "/path/to/input/data.csv",
                    "output_file": "/path/to/output/result.json",
                    "transformation_type": "csv_to_json"
                }
            }
        }

        print(f"\n{Colors.YELLOW}Available templates:{Colors.RESET}")
        for key, template in templates.items():
            print(f"  {key}. {template['name']}")
            print(f"     {Colors.DIM}{template['description'][:80]}...{Colors.RESET}")

        choice = input(f"\n{Colors.CYAN}Select template (1-4) or 'custom' for custom goal: {Colors.RESET}").strip()

        if choice in templates:
            template = templates[choice]
            print(f"\n{Colors.GREEN}Selected template: {template['name']}{Colors.RESET}")

            # Allow customization
            print(f"\n{Colors.YELLOW}Customize constraints (press Enter to use defaults):{Colors.RESET}")
            print(f"{Colors.DIM}Current constraints: {json.dumps(template['constraints'], indent=2)}{Colors.RESET}")

            custom_constraints = input(f"\n{Colors.CYAN}New constraints (JSON) or Enter for defaults: {Colors.RESET}").strip()

            if custom_constraints:
                try:
                    constraints = json.loads(custom_constraints)
                except json.JSONDecodeError as e:
                    print(f"{Colors.RED}❌ Invalid JSON format: {e}{Colors.RESET}")
                    print(f"{Colors.YELLOW}Using template defaults{Colors.RESET}")
                    constraints = template['constraints']
            else:
                constraints = template['constraints']

            # Create goal
            goal_id = f"template-goal-{choice}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            goal = Goal(
                id=goal_id,
                description=template['description'],
                constraints=constraints
            )

            print(f"\n{Colors.GREEN}✅ Goal created from template!{Colors.RESET}")
            return goal

        elif choice.lower() == 'custom':
            return self.create_goal_interactive()
        else:
            print(f"{Colors.RED}❌ Invalid choice{Colors.RESET}")
            return None

    def execute_goal_react(self, goal: Goal, max_turns: int = 10):
        """Execute a goal using ReAct framework with live updates."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTING GOAL (REACT) ═══{Colors.RESET}")
        print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {goal.id}")
        print(f"{Colors.BOLD}Description:{Colors.RESET} {goal.description}")
        print(f"{Colors.BOLD}Max Turns:{Colors.RESET} {max_turns}")

        # Auto-enable live reasoning in FAST mode, otherwise ask user
        if self.fast_mode:
            show_reasoning = True
            print(f"\n{Colors.BLUE}🚀 FAST mode: Auto-enabling live reasoning{Colors.RESET}")
        else:
            show_reasoning = input(f"\n{Colors.CYAN}Show live reasoning? (y/N): {Colors.RESET}").strip().lower() == 'y'

        print(f"\n{Colors.YELLOW}🧠 Starting ReAct execution...{Colors.RESET}")

        try:
            # Get max_turns from constraints if specified
            if goal.constraints and 'max_turns' in goal.constraints:
                max_turns = goal.constraints['max_turns']

            if show_reasoning:
                # Execute with live updates
                result = self._execute_with_live_updates(goal, max_turns)
            else:
                # Execute normally
                result = self.agent_controller.execute_goal(goal.description, max_turns)

            if not result:
                print(f"{Colors.RED}❌ Failed to execute goal{Colors.RESET}")
                return None

            # Display execution summary
            self._display_react_summary(result)

            # Convert to format compatible with CLI explorer
            execution_data = self._convert_react_to_execution_data(goal, result)

            self.current_execution = execution_data
            self.execution_history.append(execution_data)

            return execution_data

        except Exception as e:
            print(f"{Colors.RED}❌ Error during execution: {e}{Colors.RESET}")
            return None

    def _execute_with_live_updates(self, goal: Goal, max_turns: int):
        """Execute goal with live reasoning display."""
        from reactor.models import ReActState

        # Initialize state
        state = ReActState(goal=goal.description, max_turns=max_turns)

        print(f"\n{Colors.BOLD}{Colors.BLUE}═══ LIVE REACT EXECUTION ═══{Colors.RESET}")

        # Get available tools
        available_tools = self.registry.list_ufs()

        while not state.is_complete:
            turn_num = state.turn_count + 1

            # Check if we've exceeded max turns and need user confirmation
            if turn_num > state.max_turns:
                print(f"\n{Colors.YELLOW}⚠️  Reached maximum turns ({state.max_turns}). Continue? (Y/n, Enter=Y): {Colors.RESET}", end="")
                response = input().strip().lower()
                if response in ['n', 'no']:
                    print(f"{Colors.RED}❌ Execution stopped by user{Colors.RESET}")
                    break
                # If Y, yes, or Enter (empty), continue

            print(f"\n{Colors.BOLD}{Colors.CYAN}┌─ Turn {turn_num}/{state.max_turns}+ ─────────────────────────────────────────────────┐{Colors.RESET}" if turn_num > state.max_turns else f"\n{Colors.BOLD}{Colors.CYAN}┌─ Turn {turn_num}/{state.max_turns} ─────────────────────────────────────────────────┐{Colors.RESET}")
            print(f"{Colors.BOLD}│ {Colors.YELLOW}**Reasoning...**{Colors.RESET}{Colors.BOLD}                                      │{Colors.RESET}")
            print(f"{Colors.BOLD}└───────────────────────────────────────────────────────────┘{Colors.RESET}")

            try:
                # Build prompt and get LLM response
                messages = self.agent_controller.prompt_builder.build_messages_for_openai(state, available_tools)
                raw_response = self.agent_controller.llm_client.create_completion_text(messages)

                # Parse response
                parsed_response = self.agent_controller._parse_llm_response(raw_response)

                # Display enhanced reasoning
                if parsed_response.working_memory_update:
                    wm = parsed_response.working_memory_update
                    if wm.new_facts:
                        print(f"{Colors.CYAN}🧠 {Colors.BOLD}**New Facts:**{Colors.RESET} {', '.join(wm.new_facts[:2])}{'...' if len(wm.new_facts) > 2 else ''}")
                    if wm.updated_hypothesis:
                        print(f"{Colors.CYAN}💡 {Colors.BOLD}**Hypothesis:**{Colors.RESET} {wm.updated_hypothesis[:100]}...")
                if parsed_response.progress_check:
                    print(f"{Colors.MAGENTA}📊 {Colors.BOLD}**Progress Check:**{Colors.RESET} {parsed_response.progress_check}")
                print(f"{Colors.YELLOW}💭 {Colors.BOLD}**Thought:**{Colors.RESET} {parsed_response.thought}")
                print(f"{Colors.BLUE}🛠️  {Colors.BOLD}**Action:**{Colors.RESET} {parsed_response.action}")

                # Check for goal completion
                if parsed_response.is_finish:
                    print(f"\n{Colors.GREEN}🎉 Agent indicated goal completion!{Colors.RESET}")
                    print(f"{Colors.GREEN}🏁 Completion Reason:{Colors.RESET} {parsed_response.action.get('reason', 'Goal completed')}")

                    # Still add this final turn to scratchpad
                    from reactor.models import ScratchpadEntry
                    final_entry = ScratchpadEntry(
                        turn=turn_num,
                        thought=parsed_response.thought,
                        action=parsed_response.action,
                        observation=f"FINISH: {parsed_response.action.get('reason', 'Goal completed')}",
                        progress_check=parsed_response.progress_check
                    )
                    state.scratchpad.append(final_entry)
                    state.turn_count += 1

                    state.is_complete = True
                    state.completion_reason = parsed_response.action.get("reason", "Goal completed")
                    break

                # Execute action
                print(f"{Colors.CYAN}{Colors.BOLD}**Executing Action:**{Colors.RESET} {Colors.DIM}{parsed_response.action.get('tool_name', 'unknown')} with parameters {parsed_response.action.get('parameters', {})}{Colors.RESET}")
                observation = self.agent_controller.tool_executor.execute_action(parsed_response.action)

                # Display observation
                if observation.startswith("ERROR"):
                    print(f"{Colors.RED}👀 {Colors.BOLD}**Observation:**{Colors.RESET} {self._format_observation_output(observation)}")
                else:
                    print(f"{Colors.GREEN}👀 {Colors.BOLD}**Observation:**{Colors.RESET} {self._format_observation_output(observation)}")

                # Update state
                from reactor.models import ScratchpadEntry
                entry = ScratchpadEntry(
                    turn=turn_num,
                    thought=parsed_response.thought,
                    action=parsed_response.action,
                    observation=observation,
                    progress_check=parsed_response.progress_check
                )
                state.scratchpad.append(entry)
                state.turn_count += 1

            except Exception as e:
                print(f"{Colors.RED}❌ Error in turn {turn_num}: {e}{Colors.RESET}")
                state.turn_count += 1
                break

        # Finalize state
        state.end_time = datetime.now()

        # Create result
        from reactor.models import ReActResult
        success = state.is_complete
        execution_summary = self.agent_controller._generate_execution_summary(state)

        return ReActResult(
            success=success,
            state=state,
            execution_summary=execution_summary
        )

    def _display_react_summary(self, result: ReActResult):
        """Display ReAct execution summary."""
        print(f"\n{Colors.BOLD}{Colors.GREEN}═══ REACT EXECUTION SUMMARY ═══{Colors.RESET}")

        state = result.state

        # Basic info
        print(f"{Colors.BOLD}Success:{Colors.RESET} {Colors.GREEN if result.success else Colors.RED}{result.success}{Colors.RESET}")
        print(f"{Colors.BOLD}Total Turns:{Colors.RESET} {state.turn_count}")
        print(f"{Colors.BOLD}Goal Achieved:{Colors.RESET} {Colors.GREEN if state.is_complete else Colors.RED}{state.is_complete}{Colors.RESET}")

        if state.completion_reason:
            print(f"{Colors.BOLD}Completion Reason:{Colors.RESET} {state.completion_reason}")

        # Execution duration
        if state.end_time and state.start_time:
            duration = state.end_time - state.start_time
            print(f"{Colors.BOLD}Duration:{Colors.RESET} {duration.total_seconds():.2f}s")

        # Show turn-by-turn summary
        if state.scratchpad:
            print(f"\n{Colors.BOLD}Turn Summary:{Colors.RESET}")
            actions_used = []
            for entry in state.scratchpad:
                tool_name = entry.action.get('tool_name', 'unknown')
                actions_used.append(tool_name)

                # Special handling for final turn
                if tool_name == 'finish':
                    status_icon = "🏁"
                    display_name = f"finish ({entry.action.get('reason', 'Goal completed')})"
                else:
                    status_icon = "✅" if not entry.observation.startswith("ERROR") else "❌"
                    display_name = tool_name

                print(f"  {status_icon} Turn {entry.turn}: {display_name}")

            # Show unique tools used (excluding 'finish')
            unique_tools = list(set([t for t in actions_used if t != 'finish']))
            if unique_tools:
                print(f"\n{Colors.BOLD}Tools Used:{Colors.RESET} {', '.join(unique_tools)}")

        print(f"\n{Colors.BOLD}Summary:{Colors.RESET} {result.execution_summary}")

    def _format_observation_output(self, observation: str) -> str:
        """Format observation output with proper code/JSON formatting."""
        try:
            # Check if observation contains JSON
            import re
            json_pattern = r'\{[^{}]*\}'
            json_matches = re.findall(json_pattern, observation)

            formatted_obs = observation

            # Format JSON objects
            for json_match in json_matches:
                try:
                    import json
                    parsed = json.loads(json_match)
                    pretty_json = json.dumps(parsed, indent=2)
                    # Add code block formatting
                    formatted_json = f"\n```json\n{pretty_json}\n```"
                    formatted_obs = formatted_obs.replace(json_match, formatted_json)
                except json.JSONDecodeError:
                    continue

            # Check if observation contains code output (shell commands, etc.)
            if 'stdout:' in observation:
                # Extract stdout content and format it
                stdout_match = re.search(r'stdout:\s*([^|]+)', observation)
                if stdout_match:
                    stdout_content = stdout_match.group(1).strip()
                    # Check if it looks like code or structured output
                    if any(keyword in stdout_content.lower() for keyword in ['def ', 'class ', 'import ', 'function', 'const ', 'var ', '#!/']):
                        # Format as code block
                        formatted_stdout = f"\n```\n{stdout_content}\n```"
                        formatted_obs = formatted_obs.replace(stdout_content, formatted_stdout)
                    elif stdout_content.count('\n') > 3:  # Multi-line output
                        # Format as code block for readability
                        formatted_stdout = f"\n```\n{stdout_content}\n```"
                        formatted_obs = formatted_obs.replace(stdout_content, formatted_stdout)

            return formatted_obs
        except Exception:
            # If formatting fails, return original observation
            return observation

    def _convert_react_to_execution_data(self, goal: Goal, result: ReActResult) -> Dict[str, Any]:
        """Convert ReAct result to format compatible with CLI explorer."""
        state = result.state

        # Convert scratchpad to plan-like structure for CLI compatibility
        nodes = {}
        graph = {}

        for i, entry in enumerate(state.scratchpad):
            node_id = f"turn-{entry.turn}"
            tool_name = entry.action.get('tool_name', 'unknown')

            # Create a mock result for CLI display
            success = not entry.observation.startswith("ERROR")
            mock_result = {
                "status": "success" if success else "failure",
                "output": entry.observation,
                "error": entry.observation if not success else None,
                "duration_ms": entry.duration_ms or 0
            }

            nodes[node_id] = {
                "id": node_id,
                "uf_name": tool_name,
                "status": "success" if success else "failure",
                "input_resolver": {
                    "data_mapping": entry.action.get('parameters', {}),
                    "invocation": {
                        "type": "react",
                        "template": "ReAct Framework",
                        "params": {}
                    }
                },
                "result": mock_result,
                "thought": entry.thought
            }

            # Simple linear graph for ReAct turns
            if i > 0:
                prev_node_id = f"turn-{state.scratchpad[i-1].turn}"
                graph[node_id] = [prev_node_id]
            else:
                graph[node_id] = []

        return {
            "goal": {
                "id": goal.id,
                "description": goal.description,
                "constraints": goal.constraints
            },
            "plan": {
                "id": f"react-plan-{goal.id}",
                "goal_id": goal.id,
                "status": "succeeded" if result.success else "failed",
                "graph": graph,
                "nodes": nodes,
                "framework": "ReAct"
            },
            "execution_summary": {
                "total_nodes": len(nodes),
                "successful_nodes": sum(1 for node in nodes.values() if node['status'] == 'success'),
                "failed_nodes": sum(1 for node in nodes.values() if node['status'] == 'failure'),
                "total_cost": 0.0,  # ReAct doesn't track detailed costs yet
                "total_duration_ms": sum(entry.duration_ms or 0 for entry in state.scratchpad),
                "final_status": "succeeded" if result.success else "failed",
                "framework": "ReAct",
                "turns_taken": state.turn_count,
                "goal_achieved": state.is_complete,
                "timestamp": datetime.now().isoformat()
            }
        }

    def save_execution(self, execution_data: Dict[str, Any], filename: str = None):
        """Save execution data to file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ufflow_react_execution_{timestamp}.json"

        try:
            import json
            from core.workspace_security import secure_write_text
            content = json.dumps(execution_data, indent=2, default=str)
            secure_write_text(filename, content)
            print(f"{Colors.GREEN}✅ Execution saved to {filename}{Colors.RESET}")
            return filename
        except Exception as e:
            print(f"{Colors.RED}❌ Error saving execution: {e}{Colors.RESET}")
            return None

    def explore_execution(self, execution_data: Dict[str, Any]):
        """Display execution summary (simplified exploration)."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTION SUMMARY ═══{Colors.RESET}")

        # Show basic summary info
        if 'execution_summary' in execution_data:
            summary = execution_data['execution_summary']
            print(f"{Colors.BOLD}Result:{Colors.RESET} {summary}")

        # Show goal info
        if 'goal' in execution_data:
            goal = execution_data['goal']
            print(f"{Colors.BOLD}Goal:{Colors.RESET} {goal.get('description', 'N/A')}")

        # Show turn count
        if 'state' in execution_data and 'turn_count' in execution_data['state']:
            turns = execution_data['state']['turn_count']
            print(f"{Colors.BOLD}Turns Taken:{Colors.RESET} {turns}")

        print(f"\n{Colors.DIM}Note: For detailed exploration, use the save command to export data{Colors.RESET}")

    def _prompt_for_next_goal(self):
        """Prompt user to create and execute next goal after successful completion."""
        print(f"\n{Colors.GREEN}🎉 Goal completed successfully!{Colors.RESET}")

        # Ask if user wants to create a new goal
        next_choice = input(f"{Colors.CYAN}Would you like to create a new goal? (Y/n): {Colors.RESET}").strip().lower()

        if next_choice not in ['n', 'no']:
            print(f"\n{Colors.YELLOW}Creating a new goal...{Colors.RESET}")

            # Reset current state
            self.current_goal = None

            # Reset the agent controller to ensure fresh state
            self._reset_agent_controller()

            # Create new goal
            new_goal = self.create_goal_interactive()

            if new_goal:
                self.current_goal = new_goal
                print(f"\n{Colors.GREEN}✅ New goal created!{Colors.RESET}")

                # Ask if they want to execute immediately
                execute_choice = input(f"{Colors.CYAN}Execute this goal now? (Y/n): {Colors.RESET}").strip().lower()

                if execute_choice not in ['n', 'no']:
                    # Get max turns
                    max_turns_input = input(f"{Colors.CYAN}Max turns (default 10): {Colors.RESET}").strip()
                    try:
                        max_turns = int(max_turns_input) if max_turns_input else 10
                    except ValueError:
                        max_turns = 10

                    # Execute the new goal
                    self.current_execution = self.execute_goal_react(self.current_goal, max_turns)

                    # Recursively check for next goal if this one completes
                    if self.current_execution:
                        summary = self.current_execution.get('execution_summary', {})
                        if summary.get('goal_achieved', False):
                            self._prompt_for_next_goal()
                return True
            else:
                print(f"{Colors.YELLOW}Goal creation cancelled. Returning to main menu.{Colors.RESET}")
                return False
        else:
            print(f"{Colors.YELLOW}No new goal created. Returning to main menu.{Colors.RESET}")
            return False

    def _run_fast_mode_loop(self):
        """Run continuous goal creation and execution loop for FAST mode."""
        print(f"\n{Colors.YELLOW}🚀 FAST mode: Continuous goal execution mode!{Colors.RESET}")
        print(f"{Colors.DIM}Create and execute goals continuously. Press Ctrl+C to exit.{Colors.RESET}")

        while True:
            try:
                # Create a new goal
                print(f"\n{Colors.CYAN}━━━ Creating New Goal ━━━{Colors.RESET}")

                # Reset the agent controller for each new goal in FAST mode
                self._reset_agent_controller()

                self.current_goal = self.create_goal_interactive()

                if not self.current_goal:
                    print(f"\n{Colors.RED}❌ Goal creation failed. Exiting FAST mode.{Colors.RESET}")
                    break

                print(f"\n{Colors.GREEN}✅ Goal created successfully!{Colors.RESET}")
                print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {self.current_goal.id}")
                print(f"{Colors.BOLD}Description:{Colors.RESET} {self.current_goal.description}")

                # Auto-execute the goal
                print(f"\n{Colors.BLUE}🚀 FAST mode: Auto-executing goal with default settings (10 max turns)...{Colors.RESET}")
                self.current_execution = self.execute_goal_react(self.current_goal, 10)

                if self.current_execution:

                    # Check if goal was completed successfully
                    summary = self.current_execution.get('execution_summary', {})
                    if summary.get('goal_achieved', False):
                        print(f"\n{Colors.GREEN}🎉 Goal completed successfully!{Colors.RESET}")

                        # Ask if they want to continue with another goal
                        continue_choice = input(f"{Colors.CYAN}Create and execute another goal? (Y/n): {Colors.RESET}").strip().lower()
                        if continue_choice in ['n', 'no']:
                            print(f"\n{Colors.GREEN}🎉 FAST mode session completed!{Colors.RESET}")
                            break
                        # If yes or Enter, continue the loop
                    else:
                        print(f"\n{Colors.YELLOW}⚠️ Goal was not fully completed.{Colors.RESET}")
                        # Ask if they want to try another goal
                        retry_choice = input(f"{Colors.CYAN}Try a different goal? (Y/n): {Colors.RESET}").strip().lower()
                        if retry_choice in ['n', 'no']:
                            print(f"\n{Colors.YELLOW}Exiting FAST mode.{Colors.RESET}")
                            break
                else:
                    print(f"\n{Colors.RED}❌ Execution failed.{Colors.RESET}")
                    # Ask if they want to try another goal
                    retry_choice = input(f"{Colors.CYAN}Try a different goal? (Y/n): {Colors.RESET}").strip().lower()
                    if retry_choice in ['n', 'no']:
                        print(f"\n{Colors.RED}Exiting FAST mode.{Colors.RESET}")
                        break

            except KeyboardInterrupt:
                print(f"\n\n{Colors.YELLOW}⚠️ FAST mode interrupted by user{Colors.RESET}")
                break
            except Exception as e:
                print(f"\n{Colors.RED}❌ Error in FAST mode: {e}{Colors.RESET}")
                retry_choice = input(f"{Colors.CYAN}Continue anyway? (Y/n): {Colors.RESET}").strip().lower()
                if retry_choice in ['n', 'no']:
                    break

    def _reset_agent_controller(self):
        """Reset the agent controller to ensure fresh state for new goals."""
        try:
            print(f"{Colors.DIM}🔄 Resetting agent state for new goal...{Colors.RESET}")

            # Create a fresh agent controller
            self.agent_controller = AgentController(self.registry)

            logger.info("Agent controller reset successfully")

        except Exception as e:
            print(f"{Colors.YELLOW}⚠️ Warning: Could not fully reset agent controller: {e}{Colors.RESET}")
            logger.warning(f"Agent controller reset failed: {e}")

    def display_main_menu(self):
        """Display the main interactive menu."""
        mode_indicator = " - FAST MODE" if self.fast_mode else ""
        print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗")
        print(f"║                   INTERACTIVE REACT FRAMEWORK{mode_indicator:<20} ║")
        print(f"║                      Create, Execute, and Explore Goals                    ║")
        print(f"╚══════════════════════════════════════════════════════════════════════════════╝{Colors.RESET}")

        print(f"\n{Colors.GREEN}Available Commands:{Colors.RESET}")
        print(f"  {Colors.BOLD}create{Colors.RESET}     - Create a new goal (custom)")
        print(f"  {Colors.BOLD}template{Colors.RESET}   - Create goal from template")
        print(f"  {Colors.BOLD}execute{Colors.RESET}    - Execute current goal with ReAct framework")
        print(f"  {Colors.BOLD}explore{Colors.RESET}    - Show summary of last execution")
        print(f"  {Colors.BOLD}save{Colors.RESET}       - Save last execution to file")
        print(f"  {Colors.BOLD}history{Colors.RESET}    - Show execution history")
        print(f"  {Colors.BOLD}status{Colors.RESET}     - Show current status")
        print(f"  {Colors.BOLD}help{Colors.RESET}       - Show this help")
        print(f"  {Colors.BOLD}quit{Colors.RESET}       - Exit")

        if self.fast_mode:
            print(f"\n{Colors.BLUE}💨 FAST mode features:{Colors.RESET}")
            print(f"   • Skip constraints prompt (auto-set workspace to CWD)")
            print(f"   • Auto-enable live reasoning")
            print(f"   • Auto-execute after goal creation")

    def display_status(self):
        """Display current status."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ CURRENT STATUS ═══{Colors.RESET}")

        if self.current_goal:
            print(f"{Colors.BOLD}Current Goal:{Colors.RESET} {self.current_goal.id}")
            print(f"{Colors.BOLD}Description:{Colors.RESET} {self.current_goal.description}")
        else:
            print(f"{Colors.YELLOW}No current goal{Colors.RESET}")

        if self.current_execution:
            summary = self.current_execution.get('execution_summary', {})
            print(f"{Colors.BOLD}Last Execution:{Colors.RESET} {summary.get('final_status', 'unknown')}")
            print(f"{Colors.BOLD}Framework:{Colors.RESET} {summary.get('framework', 'ReAct')}")
            print(f"{Colors.BOLD}Turns Taken:{Colors.RESET} {summary.get('turns_taken', 0)}")
            print(f"{Colors.BOLD}Goal Achieved:{Colors.RESET} {summary.get('goal_achieved', False)}")
        else:
            print(f"{Colors.YELLOW}No executions yet{Colors.RESET}")

        print(f"{Colors.BOLD}Execution History:{Colors.RESET} {len(self.execution_history)} executions")

    def display_history(self):
        """Display execution history."""
        if not self.execution_history:
            print(f"{Colors.YELLOW}No execution history{Colors.RESET}")
            return

        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTION HISTORY ═══{Colors.RESET}")

        for i, execution in enumerate(self.execution_history, 1):
            goal = execution.get('goal', {})
            summary = execution.get('execution_summary', {})

            print(f"\n{Colors.BOLD}{i}. {goal.get('id', 'unknown')}{Colors.RESET}")
            print(f"   Description: {goal.get('description', 'N/A')[:80]}...")
            print(f"   Framework: {summary.get('framework', 'ReAct')}")
            print(f"   Status: {summary.get('final_status', 'unknown')}")
            print(f"   Turns: {summary.get('turns_taken', 0)}")
            print(f"   Goal Achieved: {summary.get('goal_achieved', False)}")
            print(f"   Timestamp: {summary.get('timestamp', 'N/A')}")

    def run_interactive(self):
        """Run the interactive UFFLOW React session."""
        if self.fast_mode:
            print(f"{Colors.GREEN}🧠 Starting Interactive UFFLOW React Framework - FAST MODE{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}🧠 Starting Interactive UFFLOW React Framework{Colors.RESET}")

        # Setup UFFLOW
        if not self.setup_ufflow():
            return

        # Auto-start with goal creation mode
        if self.fast_mode:
            print(f"\n{Colors.YELLOW}🚀 FAST mode: Let's create and execute a goal!{Colors.RESET}")
            print(f"{Colors.DIM}ReAct will reason step-by-step and adapt based on observations.{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}🚀 Let's start by creating a goal for the ReAct framework!{Colors.RESET}")
            print(f"{Colors.DIM}ReAct will reason step-by-step and adapt based on observations.{Colors.RESET}")

        # In FAST mode, enter a continuous goal creation and execution loop
        if self.fast_mode:
            self._run_fast_mode_loop()
            return

        # Regular mode - Go directly to goal creation
        self.current_goal = self.create_goal_interactive()
        if self.current_goal:
            print(f"\n{Colors.GREEN}✅ Goal created successfully!{Colors.RESET}")
            print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {self.current_goal.id}")
            print(f"{Colors.BOLD}Description:{Colors.RESET} {self.current_goal.description}")
        else:
            print(f"\n{Colors.RED}❌ Goal creation failed. You can try again later.{Colors.RESET}")

        while True:
            try:
                self.display_main_menu()
                command = input(f"\n{Colors.CYAN}react> {Colors.RESET}").strip().lower()

                if not command:
                    continue

                if command in ['quit', 'exit', 'q']:
                    print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}")
                    break

                elif command in ['help', 'h']:
                    self.display_main_menu()

                elif command == 'create':
                    self.current_goal = self.create_goal_interactive()

                elif command == 'template':
                    self.current_goal = self.create_goal_from_template()

                elif command == 'execute':
                    if not self.current_goal:
                        print(f"{Colors.RED}❌ No current goal. Create one first.{Colors.RESET}")
                    else:
                        # Ask for max turns
                        max_turns_input = input(f"{Colors.CYAN}Max turns (default 10): {Colors.RESET}").strip()
                        try:
                            max_turns = int(max_turns_input) if max_turns_input else 10
                        except ValueError:
                            max_turns = 10

                        self.current_execution = self.execute_goal_react(self.current_goal, max_turns)

                        # Check if goal was completed and prompt for next goal
                        if self.current_execution:
                            summary = self.current_execution.get('execution_summary', {})
                            if summary.get('goal_achieved', False):
                                self._prompt_for_next_goal()

                elif command == 'explore':
                    if not self.current_execution:
                        print(f"{Colors.RED}❌ No execution to explore. Execute a goal first.{Colors.RESET}")
                    else:
                        self.explore_execution(self.current_execution)

                elif command == 'save':
                    if not self.current_execution:
                        print(f"{Colors.RED}❌ No execution to save. Execute a goal first.{Colors.RESET}")
                    else:
                        filename = input(f"{Colors.CYAN}Filename (or Enter for auto-generated): {Colors.RESET}").strip()
                        if not filename:
                            filename = None
                        self.save_execution(self.current_execution, filename)

                elif command == 'history':
                    self.display_history()

                elif command == 'status':
                    self.display_status()

                else:
                    print(f"{Colors.RED}❌ Unknown command: {command}{Colors.RESET}")
                    print(f"Type 'help' for available commands")

            except KeyboardInterrupt:
                print(f"\n\n{Colors.YELLOW}⚠️ Interrupted by user{Colors.RESET}")
                break
            except EOFError:
                print(f"\n\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}")
                break
            except Exception as e:
                print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Interactive UFFLOW React Framework - Create, Execute, and Explore Goals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python interactive_ufflow_react.py                        # Start interactive ReAct session
  python interactive_ufflow_react.py --fast                # Start in FAST mode (auto-execute)
  python interactive_ufflow_react.py --suppress-info       # Hide INFO logs (cleaner output)
  python interactive_ufflow_react.py --fast --suppress-info # FAST mode with minimal logging
  python interactive_ufflow_react.py --help                # Show help

ReAct Features:
  • Dynamic reasoning at each step
  • Adaptive execution based on observations
  • Live reasoning display during execution
  • Compatible with existing CLI explorer
  • FAST mode: Skip prompts and auto-execute with live reasoning
  • Suppress INFO logs for cleaner console output
        """
    )

    parser.add_argument(
        '--fast',
        action='store_true',
        help='Enable FAST mode: auto-execute goals without prompts, default to live reasoning'
    )

    parser.add_argument(
        '--suppress-info',
        action='store_true',
        help='Suppress INFO log messages in console output (only show WARNING and ERROR)'
    )

    args = parser.parse_args()

    # Setup logging with suppress INFO flag if specified
    if args.suppress_info:
        from core.logging_config import setup_logging
        setup_logging(suppress_info_logs=True)

    # Create and run interactive UFFLOW React
    interactive_ufflow = InteractiveUFFLOWReact(fast_mode=args.fast)
    interactive_ufflow.run_interactive()

if __name__ == "__main__":
    main()