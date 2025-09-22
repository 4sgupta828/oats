#!/usr/bin/env python3
"""
Interactive Orchestrator for UF-Flow Framework

Provides step-by-step execution with detailed visualization of plans, DAG structure,
and comprehensive node execution details. Pauses after each node for inspection.
"""

import sys
import os
import time
import json
from typing import Optional, Dict, Any, List
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.models import Goal, Plan, WorldState, ToolResult, PlanNode
from core.logging_config import get_logger, UFFlowLogger
from registry.main import global_registry
from executor.main import execute_tool
from memory.main import global_memory
from orchestrator.graph_utils import topological_sort
from orchestrator.input_resolver import resolve_inputs
from orchestrator.main import OrchestrationError

# Initialize logging
logger = get_logger('interactive_orchestrator')


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
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_RED = '\033[41m'


class InteractiveOrchestrator:
    """
    Enhanced orchestrator with step-by-step execution and detailed visualization.
    """

    def __init__(self):
        self.execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0
        }
        self.pause_after_each_node = True
        self.show_detailed_output = True

    def display_plan_overview(self, plan: Plan, goal: Goal):
        """Display comprehensive plan overview with DAG visualization."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}")
        print(f"🎯 EXECUTION PLAN OVERVIEW")
        print(f"{'='*80}{Colors.RESET}")

        # Goal Information
        print(f"\n{Colors.BOLD}{Colors.YELLOW}📋 GOAL DETAILS:{Colors.RESET}")
        print(f"   ID: {goal.id}")
        print(f"   Description: {goal.description}")
        if goal.constraints:
            print(f"   Constraints: {json.dumps(goal.constraints, indent=6)}")

        # Plan Information
        print(f"\n{Colors.BOLD}{Colors.BLUE}🗺️  PLAN DETAILS:{Colors.RESET}")
        print(f"   Plan ID: {plan.id}")
        print(f"   Status: {self._format_status(plan.status)}")
        print(f"   Total Nodes: {len(plan.nodes)}")
        print(f"   Confidence Score: {Colors.GREEN}{plan.confidence_score:.2%}{Colors.RESET}")

        # DAG Visualization
        self._display_dag_structure(plan)

        # Node Details
        self._display_node_details(plan)

    def _display_dag_structure(self, plan: Plan):
        """Display the DAG structure in a visual format."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}🔗 DAG STRUCTURE:{Colors.RESET}")

        # Show dependencies
        if plan.graph:
            print("   Dependencies:")
            for node_id, dependencies in plan.graph.items():
                if dependencies:
                    deps_str = " → ".join(dependencies)
                    print(f"      {Colors.CYAN}{node_id}{Colors.RESET} depends on: {Colors.YELLOW}{deps_str}{Colors.RESET}")
                else:
                    print(f"      {Colors.CYAN}{node_id}{Colors.RESET} (no dependencies)")

        # Show execution order
        try:
            execution_order = topological_sort(plan.graph)
            print(f"\n   Execution Order:")
            for i, node_id in enumerate(execution_order, 1):
                node = plan.nodes[node_id]
                arrow = " → " if i < len(execution_order) else ""
                print(f"      {Colors.BOLD}{i:2d}.{Colors.RESET} {Colors.GREEN}{node_id}{Colors.RESET} ({Colors.DIM}{node.uf_name}{Colors.RESET}){arrow}", end="")
            print()  # Final newline
        except ValueError as e:
            print(f"      {Colors.RED}❌ Invalid DAG: {e}{Colors.RESET}")

    def _display_node_details(self, plan: Plan):
        """Display detailed information about each node."""
        print(f"\n{Colors.BOLD}{Colors.WHITE}📊 NODE DETAILS:{Colors.RESET}")

        for i, (node_id, node) in enumerate(plan.nodes.items(), 1):
            print(f"\n   {Colors.BOLD}{i:2d}. {Colors.CYAN}{node_id}{Colors.RESET}")
            print(f"      Tool: {Colors.YELLOW}{node.uf_name}{Colors.RESET}")
            print(f"      Status: {self._format_status(node.status)}")

            # Input resolver details
            if node.input_resolver and node.input_resolver.data_mapping:
                print(f"      Inputs:")
                for input_name, mapping in node.input_resolver.data_mapping.items():
                    source_color = {
                        "literal": Colors.GREEN,
                        "context": Colors.BLUE,
                        "upstream": Colors.MAGENTA
                    }.get(mapping.source, Colors.WHITE)

                    print(f"        • {input_name}: {source_color}{mapping.source}{Colors.RESET} → {mapping.value_selector}")
                    if mapping.node_id:
                        print(f"          (from node: {Colors.CYAN}{mapping.node_id}{Colors.RESET})")

    def _format_status(self, status: str) -> str:
        """Format status with appropriate color."""
        status_colors = {
            'success': f"{Colors.BG_GREEN}{Colors.WHITE} SUCCESS {Colors.RESET}",
            'failure': f"{Colors.BG_RED}{Colors.WHITE} FAILURE {Colors.RESET}",
            'running': f"{Colors.BG_YELLOW}{Colors.WHITE} RUNNING {Colors.RESET}",
            'pending': f"{Colors.CYAN} PENDING {Colors.RESET}",
            'succeeded': f"{Colors.BG_GREEN}{Colors.WHITE} SUCCEEDED {Colors.RESET}",
            'failed': f"{Colors.BG_RED}{Colors.WHITE} FAILED {Colors.RESET}"
        }
        return status_colors.get(status.lower(), f"{Colors.WHITE}{status.upper()}{Colors.RESET}")

    def _display_node_execution_start(self, node_id: str, node: PlanNode, step: int, total: int):
        """Display node execution start information."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}")
        print(f"🚀 EXECUTING NODE {step}/{total}: {node_id}")
        print(f"{'='*80}{Colors.RESET}")

        print(f"\n{Colors.BOLD}Node Information:{Colors.RESET}")
        print(f"   ID: {Colors.CYAN}{node_id}{Colors.RESET}")
        print(f"   Tool: {Colors.YELLOW}{node.uf_name}{Colors.RESET}")
        print(f"   Status: {self._format_status(node.status)}")

    def _display_resolved_inputs(self, node_id: str, inputs: Dict[str, Any]):
        """Display resolved inputs for a node."""
        print(f"\n{Colors.BOLD}📥 Resolved Inputs:{Colors.RESET}")
        if inputs:
            for key, value in inputs.items():
                # Show more content - approximately 100 lines worth (assuming ~80 chars per line)
                display_value = self._format_output_content(str(value), max_chars=8000)
                print(f"   {Colors.GREEN}{key}:{Colors.RESET} {display_value}")
        else:
            print(f"   {Colors.DIM}(No inputs){Colors.RESET}")

    def _display_execution_result(self, node_id: str, result: ToolResult):
        """Display node execution result."""
        print(f"\n{Colors.BOLD}📤 Execution Result:{Colors.RESET}")
        print(f"   Status: {self._format_status(result.status)}")

        if result.output:
            print(f"   Output:")
            if isinstance(result.output, dict):
                for key, value in result.output.items():
                    display_value = self._format_output_content(str(value), max_chars=8000)
                    print(f"     {Colors.BLUE}{key}:{Colors.RESET} {display_value}")
            elif isinstance(result.output, str):
                display_value = self._format_output_content(result.output, max_chars=8000)
                print(f"     {Colors.BLUE}content:{Colors.RESET} {display_value}")
            else:
                display_value = self._format_output_content(str(result.output), max_chars=8000)
                print(f"     {display_value}")

        if result.error:
            # Show full error messages - they're usually important
            error_display = self._format_output_content(result.error, max_chars=4000)
            print(f"   Error: {Colors.RED}{error_display}{Colors.RESET}")

        # Performance metrics
        metrics = []
        if result.cost:
            metrics.append(f"Cost: ${result.cost:.4f}")
        if result.duration_ms:
            metrics.append(f"Duration: {result.duration_ms}ms")
        if metrics:
            print(f"   Metrics: {Colors.DIM}{' | '.join(metrics)}{Colors.RESET}")

    def _wait_for_user_input(self, prompt: str = "Press Enter to continue, 'q' to quit, 's' to skip pauses: "):
        """Wait for user input with options."""
        try:
            user_input = input(f"\n{Colors.YELLOW}{prompt}{Colors.RESET}").strip().lower()
            if user_input == 'q':
                print(f"{Colors.YELLOW}Execution interrupted by user.{Colors.RESET}")
                return 'quit'
            elif user_input == 's':
                print(f"{Colors.YELLOW}Skipping remaining pauses.{Colors.RESET}")
                self.pause_after_each_node = False
                return 'continue'
            return 'continue'
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Execution interrupted by user.{Colors.RESET}")
            return 'quit'

    def run_goal_interactive(self, goal: Goal, plan: Plan) -> WorldState:
        """
        Execute a plan interactively with step-by-step visualization and user control.
        """
        start_time = time.time()
        self.execution_stats["total_executions"] += 1

        # Display comprehensive plan overview
        self.display_plan_overview(plan, goal)

        # Ask user if they want to proceed
        if self._wait_for_user_input("📋 Plan displayed. Press Enter to start execution: ") == 'quit':
            world_state = WorldState(goal=goal, plan=plan)
            world_state.plan.status = "failed"
            return world_state

        UFFlowLogger.log_execution_start(
            "interactive_orchestrator",
            "run_goal_interactive",
            goal_id=goal.id,
            plan_id=plan.id,
            node_count=len(plan.nodes)
        )

        world_state = WorldState(goal=goal, plan=plan)
        executed_nodes = []
        failed_node: Optional[str] = None

        try:
            logger.info(f"Starting interactive goal execution: {goal.id} with plan: {plan.id}")

            # Validate plan structure
            if not plan.nodes:
                raise OrchestrationError("Plan has no nodes to execute", error_type="validation")

            # Determine execution order
            try:
                execution_order = topological_sort(plan.graph)
            except ValueError as e:
                raise OrchestrationError(f"Invalid plan graph: {e}", error_type="graph_validation")

            # Execute nodes in order
            for i, node_id in enumerate(execution_order, 1):
                node = world_state.plan.nodes[node_id]
                node.status = "running"

                # Display node execution start
                self._display_node_execution_start(node_id, node, i, len(execution_order))

                try:
                    # Resolve inputs
                    inputs = resolve_inputs(node, world_state)
                    self._display_resolved_inputs(node_id, inputs)

                    # Get tool definition
                    if ':' in node.uf_name:
                        tool_name, tool_version = node.uf_name.split(':', 1)
                    else:
                        tool_name = node.uf_name
                        tool_version = "1.0.0"

                    uf_descriptor = global_registry.get_uf(tool_name, tool_version)
                    if not uf_descriptor:
                        available_tools = [f"{desc.name}:{desc.version}" for desc in global_registry.list_ufs()]
                        raise OrchestrationError(
                            f"Tool '{node.uf_name}' not found. Available tools: {', '.join(available_tools)}",
                            node_id=node_id,
                            error_type="tool_not_found"
                        )

                    # Pause before execution if requested
                    if self.pause_after_each_node:
                        action = self._wait_for_user_input("🔄 Ready to execute. Press Enter to run: ")
                        if action == 'quit':
                            world_state.plan.status = "failed"
                            return world_state

                    # Execute the tool
                    print(f"\n{Colors.YELLOW}⚙️  Executing {node.uf_name}...{Colors.RESET}")
                    result = execute_tool(uf_descriptor, inputs)

                    # Record result
                    if hasattr(global_memory, 'remember'):
                        global_memory.remember(result)

                    node.result = result
                    node.status = result.status
                    world_state.execution_history.append(result)
                    executed_nodes.append(node_id)

                    # Display execution result
                    self._display_execution_result(node_id, result)

                    if result.status == "failure":
                        failed_node = node_id
                        print(f"\n{Colors.RED}❌ Node '{node_id}' failed!{Colors.RESET}")
                        world_state.plan.status = "failed"

                        # Ask user if they want to continue or stop
                        if self.pause_after_each_node:
                            action = self._wait_for_user_input("❌ Node failed. Press Enter to continue with summary: ")
                            if action == 'quit':
                                return world_state
                        break
                    else:
                        print(f"\n{Colors.GREEN}✅ Node '{node_id}' completed successfully!{Colors.RESET}")

                    # Pause after successful execution
                    if self.pause_after_each_node and i < len(execution_order):
                        action = self._wait_for_user_input(f"✅ Node completed. Continue to next node ({i+1}/{len(execution_order)})? ")
                        if action == 'quit':
                            world_state.plan.status = "failed"
                            return world_state

                except OrchestrationError as e:
                    failed_node = node_id
                    node.status = "failure"
                    if not node.result:
                        node.result = ToolResult(
                            status="failure",
                            output=None,
                            error=str(e)
                        )
                    world_state.plan.status = "failed"
                    print(f"\n{Colors.RED}❌ Orchestration error in node '{node_id}': {e}{Colors.RESET}")
                    break

            # Set final status and display summary
            if world_state.plan.status != "failed":
                world_state.plan.status = "succeeded"
                self.execution_stats["successful_executions"] += 1
            else:
                self.execution_stats["failed_executions"] += 1

            self._display_final_summary(world_state, executed_nodes, failed_node, start_time)

            duration = time.time() - start_time
            UFFlowLogger.log_execution_end(
                "interactive_orchestrator",
                "run_goal_interactive",
                world_state.plan.status == "succeeded",
                duration_ms=int(duration * 1000),
                executed_nodes=executed_nodes,
                failed_node=failed_node,
                total_cost=sum(r.cost or 0 for r in world_state.execution_history)
            )

            return world_state

        except Exception as e:
            duration = time.time() - start_time
            self.execution_stats["failed_executions"] += 1

            print(f"\n{Colors.RED}❌ Unexpected error during goal execution: {e}{Colors.RESET}")
            world_state.plan.status = "failed"

            UFFlowLogger.log_execution_end(
                "interactive_orchestrator",
                "run_goal_interactive",
                False,
                duration_ms=int(duration * 1000),
                executed_nodes=executed_nodes,
                error_type="unexpected",
                error_message=str(e)
            )

            return world_state

    def _display_final_summary(self, world_state: WorldState, executed_nodes: List[str],
                             failed_node: Optional[str], start_time: float):
        """Display final execution summary."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}")
        print(f"📊 EXECUTION SUMMARY")
        print(f"{'='*80}{Colors.RESET}")

        # Overall status
        final_status = world_state.plan.status
        status_display = self._format_status(final_status)
        print(f"\n{Colors.BOLD}Final Status:{Colors.RESET} {status_display}")

        # Execution statistics
        total_nodes = len(world_state.plan.nodes)
        executed_count = len(executed_nodes)
        success_count = sum(1 for node_id in executed_nodes
                          if world_state.plan.nodes[node_id].status == "success")

        print(f"\n{Colors.BOLD}Execution Statistics:{Colors.RESET}")
        print(f"   Total Nodes: {total_nodes}")
        print(f"   Executed: {executed_count}")
        print(f"   Successful: {Colors.GREEN}{success_count}{Colors.RESET}")
        print(f"   Failed: {Colors.RED}{executed_count - success_count}{Colors.RESET}")

        if executed_count > 0:
            success_rate = (success_count / executed_count) * 100
            print(f"   Success Rate: {Colors.GREEN}{success_rate:.1f}%{Colors.RESET}")

        # Performance metrics
        duration = time.time() - start_time
        total_cost = sum(r.cost or 0 for r in world_state.execution_history if r.cost)
        total_duration_ms = sum(r.duration_ms or 0 for r in world_state.execution_history if r.duration_ms)

        print(f"\n{Colors.BOLD}Performance Metrics:{Colors.RESET}")
        print(f"   Total Execution Time: {duration:.2f}s")
        if total_cost > 0:
            print(f"   Total Cost: ${total_cost:.4f}")
        if total_duration_ms > 0:
            print(f"   Total Tool Duration: {total_duration_ms}ms")

        # Node-by-node results
        print(f"\n{Colors.BOLD}Node Results:{Colors.RESET}")
        for node_id, node in world_state.plan.nodes.items():
            status_display = self._format_status(node.status)
            executed_marker = "✓" if node_id in executed_nodes else "○"
            print(f"   {executed_marker} {Colors.CYAN}{node_id:<20}{Colors.RESET} {status_display} {Colors.DIM}({node.uf_name}){Colors.RESET}")

            if node.result and self.show_detailed_output:
                if node.result.output and isinstance(node.result.output, (str, dict)):
                    output_preview = self._format_output_content(str(node.result.output), max_chars=500, show_lines=True)
                    print(f"     Output: {Colors.DIM}{output_preview}{Colors.RESET}")

        if failed_node:
            print(f"\n{Colors.RED}❌ Execution stopped at node: {failed_node}{Colors.RESET}")

        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")

    def _format_output_content(self, content: str, max_chars: int = 8000, show_lines: bool = False) -> str:
        """Format output content with intelligent truncation showing ~100 lines."""
        if not content:
            return content

        # Convert to string if not already
        content_str = str(content)

        # If content is short enough, return as-is
        if len(content_str) <= max_chars:
            return content_str

        # For longer content, try to truncate at line boundaries to show ~100 lines
        lines = content_str.split('\n')

        if len(lines) <= 100:
            # If 100 lines or fewer, but still too many characters, truncate by characters
            truncated = content_str[:max_chars]
            return truncated + f"\n{Colors.DIM}... (truncated {len(content_str) - max_chars} more characters){Colors.RESET}"

        # Show first 100 lines
        displayed_lines = lines[:100]
        remaining_lines = len(lines) - 100
        remaining_chars = len('\n'.join(lines[100:]))

        result = '\n'.join(displayed_lines)

        if show_lines:
            result += f"\n{Colors.DIM}... (truncated {remaining_lines} more lines, {remaining_chars} more characters){Colors.RESET}"
        else:
            result += f"\n{Colors.DIM}... (truncated {remaining_lines} more lines){Colors.RESET}"

        return result

    def get_execution_stats(self) -> dict:
        """Get execution statistics."""
        total = self.execution_stats["total_executions"]
        if total == 0:
            return {**self.execution_stats, "success_rate": 0.0}

        success_rate = self.execution_stats["successful_executions"] / total
        return {**self.execution_stats, "success_rate": success_rate}