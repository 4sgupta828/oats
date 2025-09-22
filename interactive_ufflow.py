#!/usr/bin/env python3
"""
Interactive UFFLOW Framework with Goal Creation and Execution

This enhanced CLI allows you to:
1. Create goals interactively
2. Run UFFLOW executions
3. Explore results with the CLI UI
4. All in one interactive session

Usage:
    python interactive_ufflow.py
"""

import sys
import os
import json
import readline
import argparse
import tempfile
from typing import Dict, List, Any, Optional
from datetime import datetime
import textwrap
import shutil

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))

# Import UFFLOW components
from core.models import Goal, Plan
from registry.main import global_registry
from planner.main import create_plan_for_goal
from orchestrator.main import Orchestrator
from cli_ui import UFFLOWCLI, Colors, Box

class InteractiveUFFLOW:
    """Interactive UFFLOW framework with goal creation and execution."""
    
    def __init__(self):
        self.registry = None
        self.current_goal = None
        self.current_plan = None
        self.current_execution = None
        self.execution_history = []
        self.terminal_width = shutil.get_terminal_size().columns
    
    def setup_ufflow(self):
        """Setup UFFLOW environment."""
        print(f"{Colors.CYAN}🔧 Setting up UFFLOW environment...{Colors.RESET}")
        
        try:
            # Load tools
            global_registry.load_ufs_from_directory('./tools')
            self.registry = global_registry
            
            available_tools = self.registry.list_ufs()
            print(f"{Colors.GREEN}✅ Loaded {len(available_tools)} tools:{Colors.RESET}")
            for tool in available_tools:
                print(f"   - {tool}")
            
            return True
        except Exception as e:
            print(f"{Colors.RED}❌ Error setting up UFFLOW: {e}{Colors.RESET}")
            return False
    
    def create_goal_interactive(self):
        """Create a goal interactively."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ CREATE NEW GOAL ═══{Colors.RESET}")
        
        # Get goal description
        print(f"\n{Colors.YELLOW}Enter your goal description:{Colors.RESET}")
        print(f"{Colors.DIM}Example: 'search for all ERROR lines in log file and find their source locations'{Colors.RESET}")
        description = input(f"\n{Colors.CYAN}Goal> {Colors.RESET}").strip()
        
        if not description:
            print(f"{Colors.RED}❌ Goal description cannot be empty{Colors.RESET}")
            return None
        
        # Get constraints
        print(f"\n{Colors.YELLOW}Enter constraints (JSON format, or press Enter for empty):{Colors.RESET}")
        print(f"{Colors.DIM}Example: {{\"log_file\": \"/path/to/log\", \"code_directory\": \"/path/to/code\"}}{Colors.RESET}")
        print(f"{Colors.DIM}For multi-line strings, use \\n for newlines: {{\"sample_code\": \"class MyClass:\\n    def method1(self):\\n        pass\"}}{Colors.RESET}")
        constraints_input = input(f"\n{Colors.CYAN}Constraints> {Colors.RESET}").strip()
        
        constraints = {}
        if constraints_input:
            try:
                constraints = json.loads(constraints_input)
            except json.JSONDecodeError as e:
                print(f"{Colors.RED}❌ Invalid JSON format: {e}{Colors.RESET}")
                print(f"{Colors.YELLOW}Using empty constraints{Colors.RESET}")
        
        # Create goal
        goal_id = f"interactive-goal-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
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
    
    def _create_default_log_analysis_goal(self):
        """Create a default log analysis goal for auto-start."""
        goal_id = f"default-goal-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        goal = Goal(
            id=goal_id,
            description="search for all ERROR lines in log file and extract the log line that would be emitted by code and then search for all places in code where that line is emitted (with filenames, line numbers)",
            constraints={
                "log_file": "/Users/sgupta/moko/dynamic_agentic_loop/sample_code/sample_server.log",
                "code_directory": "/Users/sgupta/moko/dynamic_agentic_loop/sample_code",
                "file_extensions": [".java", ".js", ".py", ".ts", ".go"],
                "output_format": "json"
            }
        )
        return goal
    
    def create_goal_from_template(self):
        """Create a goal from predefined templates."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ GOAL TEMPLATES ═══{Colors.RESET}")
        
        templates = {
            "1": {
                "name": "Log Analysis",
                "description": "search for all ERROR lines in log file and extract the log line that would be emitted by code and then search for all places in code where that line is emitted (with filenames, line numbers)",
                "constraints": {
                    "log_file": "/path/to/your/logfile.log",
                    "code_directory": "/path/to/your/source/code",
                    "file_extensions": [".java", ".js", ".py", ".ts", ".go"],
                    "output_format": "json"
                }
            },
            "2": {
                "name": "File Processing",
                "description": "process all files in a directory, extract specific information, and generate a summary report",
                "constraints": {
                    "input_directory": "/path/to/input/files",
                    "output_file": "/path/to/output/report.json",
                    "file_pattern": "*.txt",
                    "extract_fields": ["timestamp", "level", "message"]
                }
            },
            "3": {
                "name": "Code Analysis",
                "description": "analyze source code for specific patterns, generate metrics, and create documentation",
                "constraints": {
                    "source_directory": "/path/to/source/code",
                    "analysis_type": "complexity",
                    "output_format": "markdown",
                    "include_metrics": True
                }
            },
            "4": {
                "name": "Data Transformation",
                "description": "transform data from one format to another with validation and error handling",
                "constraints": {
                    "input_file": "/path/to/input/data.csv",
                    "output_file": "/path/to/output/data.json",
                    "transformation_rules": "convert_csv_to_json",
                    "validate_output": True
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
    
    def _execute_goal_standard(self, goal: Goal):
        """Execute a goal using standard orchestrator (non-interactive)."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTING GOAL (STANDARD) ═══{Colors.RESET}")
        print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {goal.id}")
        print(f"{Colors.BOLD}Description:{Colors.RESET} {goal.description}")

        try:
            # Generate plan
            print(f"\n{Colors.YELLOW}📋 Generating execution plan...{Colors.RESET}")
            plan = create_plan_for_goal(goal, self.registry)

            if not plan:
                print(f"{Colors.RED}❌ Failed to generate plan{Colors.RESET}")
                return None

            print(f"{Colors.GREEN}✅ Plan generated successfully!{Colors.RESET}")
            print(f"{Colors.BOLD}Plan ID:{Colors.RESET} {plan.id}")
            print(f"{Colors.BOLD}Nodes:{Colors.RESET} {len(plan.nodes)}")

            # Show plan overview
            print(f"\n{Colors.BOLD}{Colors.BLUE}📋 Execution Plan:{Colors.RESET}")
            for node_id, node in plan.nodes.items():
                print(f"  {Colors.CYAN}•{Colors.RESET} {node_id} ({node.uf_name})")

            # Execute plan with standard orchestrator
            print(f"\n{Colors.YELLOW}🚀 Executing plan with standard orchestrator...{Colors.RESET}")
            from orchestrator.main import Orchestrator
            orchestrator = Orchestrator()
            final_state = orchestrator.run_goal(goal, plan)

            if not final_state:
                print(f"{Colors.RED}❌ Failed to execute plan{Colors.RESET}")
                return None

            # Show execution summary
            self._display_execution_summary(final_state)

            # Store execution data
            execution_data = {
                "goal": {
                    "id": goal.id,
                    "description": goal.description,
                    "constraints": goal.constraints
                },
                "plan": {
                    "id": plan.id,
                    "goal_id": goal.id,
                    "status": final_state.plan.status,
                    "graph": plan.graph,
                    "nodes": {node_id: {
                        "id": node.id,
                        "uf_name": node.uf_name,
                        "status": node.status,
                        "input_resolver": node.input_resolver,
                        "result": node.result
                    } for node_id, node in final_state.plan.nodes.items()}
                },
                "execution_summary": {
                    "total_nodes": len(final_state.plan.nodes),
                    "successful_nodes": sum(1 for node in final_state.plan.nodes.values()
                                          if node.status in ['success', 'succeeded']),
                    "failed_nodes": sum(1 for node in final_state.plan.nodes.values()
                                      if node.status in ['failure', 'failed']),
                    "total_cost": sum(node.result.cost for node in final_state.plan.nodes.values()
                                    if node.result and node.result.cost),
                    "total_duration_ms": sum(node.result.duration_ms for node in final_state.plan.nodes.values()
                                           if node.result and node.result.duration_ms),
                    "final_status": final_state.plan.status,
                    "timestamp": datetime.now().isoformat()
                }
            }

            self.execution_history.append(execution_data)
            return execution_data

        except Exception as e:
            print(f"{Colors.RED}❌ Error during execution: {e}{Colors.RESET}")
            return None

    def execute_goal(self, goal: Goal):
        """Execute a goal using UFFLOW framework."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTING GOAL ═══{Colors.RESET}")
        print(f"{Colors.BOLD}Goal ID:{Colors.RESET} {goal.id}")
        print(f"{Colors.BOLD}Description:{Colors.RESET} {goal.description}")
        
        try:
            # Generate plan
            print(f"\n{Colors.YELLOW}📋 Generating execution plan...{Colors.RESET}")
            plan = create_plan_for_goal(goal, self.registry)
            
            if not plan:
                print(f"{Colors.RED}❌ Failed to generate plan{Colors.RESET}")
                return None
            
            print(f"{Colors.GREEN}✅ Plan generated successfully!{Colors.RESET}")
            print(f"{Colors.BOLD}Plan ID:{Colors.RESET} {plan.id}")
            print(f"{Colors.BOLD}Nodes:{Colors.RESET} {len(plan.nodes)}")
            
            # Show plan overview
            print(f"\n{Colors.BOLD}{Colors.BLUE}📋 Execution Plan:{Colors.RESET}")
            for node_id, node in plan.nodes.items():
                print(f"  {Colors.CYAN}•{Colors.RESET} {node_id} ({node.uf_name})")
            
            # Execute plan with interactive orchestrator
            print(f"\n{Colors.YELLOW}🚀 Starting interactive execution...{Colors.RESET}")
            from interactive_orchestrator import InteractiveOrchestrator
            interactive_orchestrator = InteractiveOrchestrator()
            final_state = interactive_orchestrator.run_goal_interactive(goal, plan)
            
            if not final_state:
                print(f"{Colors.RED}❌ Failed to execute plan{Colors.RESET}")
                return None
            
            # Show execution summary
            self._display_execution_summary(final_state)
            
            # Store execution data
            execution_data = {
                "goal": {
                    "id": goal.id,
                    "description": goal.description,
                    "constraints": goal.constraints
                },
                "plan": {
                    "id": plan.id,
                    "goal_id": goal.id,
                    "status": final_state.plan.status,
                    "graph": plan.graph,
                    "nodes": {node_id: {
                        "id": node.id,
                        "uf_name": node.uf_name,
                        "status": node.status,
                        "input_resolver": node.input_resolver,
                        "result": node.result
                    } for node_id, node in final_state.plan.nodes.items()}
                },
                "execution_summary": {
                    "total_nodes": len(final_state.plan.nodes),
                    "successful_nodes": sum(1 for node in final_state.plan.nodes.values() 
                                          if node.status in ['success', 'succeeded']),
                    "failed_nodes": sum(1 for node in final_state.plan.nodes.values() 
                                      if node.status in ['failure', 'failed']),
                    "total_cost": sum(node.result.cost for node in final_state.plan.nodes.values() 
                                    if node.result and node.result.cost),
                    "total_duration_ms": sum(node.result.duration_ms for node in final_state.plan.nodes.values() 
                                           if node.result and node.result.duration_ms),
                    "final_status": final_state.plan.status,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            self.current_execution = execution_data
            self.execution_history.append(execution_data)
            
            return execution_data
            
        except Exception as e:
            print(f"{Colors.RED}❌ Error during execution: {e}{Colors.RESET}")
            return None
    
    def _execute_plan_with_detailed_output(self, goal: Goal, plan: Plan):
        """Execute plan with detailed, formatted output."""
        from orchestrator.graph_utils import topological_sort
        from orchestrator.input_resolver import resolve_inputs
        from executor.main import execute_tool
        from memory.main import global_memory
        from core.models import WorldState, ToolResult
        
        world_state = WorldState(goal=goal, plan=plan)
        
        try:
            execution_order = topological_sort(plan.graph)
            print(f"{Colors.DIM}Execution order: {' → '.join(execution_order)}{Colors.RESET}\n")
        except ValueError as e:
            print(f"{Colors.RED}❌ Invalid plan: {e}{Colors.RESET}")
            world_state.plan.status = "failed"
            return world_state

        for i, node_id in enumerate(execution_order, 1):
            node = world_state.plan.nodes[node_id]
            node.status = "running"
            
            # Node header
            print(f"{Colors.BOLD}{Colors.CYAN}┌─ Step {i}/{len(execution_order)}: {node_id} ─────────────────────────────────────────┐{Colors.RESET}")
            print(f"{Colors.BOLD}│ Tool: {node.uf_name:<60} │{Colors.RESET}")
            print(f"{Colors.BOLD}└─────────────────────────────────────────────────────────────────────────────┘{Colors.RESET}")
            
            try:
                # Resolve inputs
                inputs = resolve_inputs(node, world_state)
                
                # Show inputs (truncated if too long)
                if inputs:
                    print(f"{Colors.YELLOW}📥 Inputs:{Colors.RESET}")
                    for key, value in inputs.items():
                        # Show more content - approximately 100 lines worth
                        if isinstance(value, str) and len(value) > 8000:
                            lines = value.split('\n')
                            if len(lines) > 100:
                                display_value = '\n'.join(lines[:100]) + f"\n... (truncated {len(lines) - 100} more lines)"
                            else:
                                display_value = value[:8000] + f"... (truncated {len(value) - 8000} more characters)"
                        else:
                            display_value = str(value)
                        print(f"   {Colors.DIM}{key}:{Colors.RESET} {display_value}")
                    print()
                
                # Get tool definition
                if ':' in node.uf_name:
                    uf_name, uf_version = node.uf_name.split(':', 1)
                else:
                    uf_name = node.uf_name
                    uf_version = "1.0.0"
                
                uf_descriptor = self.registry.get_uf(uf_name, uf_version)
                if not uf_descriptor:
                    raise RuntimeError(f"Tool '{node.uf_name}' not found in registry.")

                # Execute the tool
                result = execute_tool(uf_descriptor, inputs)
                
                # Record result
                global_memory.remember(result)
                node.result = result
                node.status = result.status
                world_state.execution_history.append(result)
                
                # Display result
                self._display_node_result(node_id, result)
                
                if result.status == "failure":
                    print(f"{Colors.RED}❌ Node '{node_id}' failed: {result.error}{Colors.RESET}")
                    world_state.plan.status = "failed"
                    return world_state
                else:
                    print(f"{Colors.GREEN}✅ Node '{node_id}' completed successfully{Colors.RESET}")
                
            except Exception as e:
                print(f"{Colors.RED}❌ Error in node '{node_id}': {e}{Colors.RESET}")
                node.status = "failure"
                if not node.result:
                    node.result = ToolResult(status='failure', output=None, error=str(e))
                world_state.plan.status = "failed"
                return world_state
            
            print()  # Add spacing between nodes

        world_state.plan.status = "succeeded"
        return world_state
    
    def _display_node_result(self, node_id: str, result):
        """Display node execution result in a formatted way."""
        if result.status == "success":
            print(f"{Colors.GREEN}📤 Output:{Colors.RESET}")
            
            if result.output:
                if isinstance(result.output, dict):
                    # Handle structured output
                    for key, value in result.output.items():
                        if key in ['stdout', 'output'] and isinstance(value, str):
                            # This is likely the main output
                            self._display_output_content(value, key)
                        elif isinstance(value, str) and len(value) > 2000:
                            # Long string value - show more content
                            print(f"   {Colors.DIM}{key}:{Colors.RESET}")
                            self._display_output_content(value, "content")
                        else:
                            print(f"   {Colors.DIM}{key}:{Colors.RESET} {value}")
                elif isinstance(result.output, str):
                    # Direct string output
                    self._display_output_content(result.output, "content")
                else:
                    print(f"   {result.output}")
            else:
                print(f"   {Colors.DIM}(No output){Colors.RESET}")
            
            # Show performance metrics
            if result.cost or result.duration_ms:
                metrics = []
                if result.cost:
                    metrics.append(f"Cost: ${result.cost:.4f}")
                if result.duration_ms:
                    metrics.append(f"Duration: {result.duration_ms}ms")
                if metrics:
                    print(f"   {Colors.DIM}{' | '.join(metrics)}{Colors.RESET}")
        
        elif result.status == "failure":
            print(f"{Colors.RED}❌ Error:{Colors.RESET} {result.error}")
            if result.output:
                print(f"{Colors.YELLOW}Output:{Colors.RESET} {result.output}")
    
    def _display_output_content(self, content: str, label: str = "content"):
        """Display output content with proper formatting, showing up to 100 lines."""
        if not content:
            print(f"   {Colors.DIM}(Empty {label}){Colors.RESET}")
            return

        # Split into lines
        lines = content.split('\n')

        if len(lines) == 1 and len(content) < 200:
            # Single line, reasonably short content
            print(f"   {content}")
        elif len(lines) <= 100:
            # Show all lines if 100 or fewer
            for i, line in enumerate(lines, 1):
                # Truncate very long individual lines
                display_line = line[:200] + "..." if len(line) > 200 else line
                print(f"   {Colors.DIM}{i:2d}:{Colors.RESET} {display_line}")
        else:
            # Show first 100 lines, then truncate
            for i, line in enumerate(lines[:100], 1):
                display_line = line[:200] + "..." if len(line) > 200 else line
                print(f"   {Colors.DIM}{i:2d}:{Colors.RESET} {display_line}")

            remaining_lines = len(lines) - 100
            print(f"   {Colors.DIM}... (truncated {remaining_lines} more lines){Colors.RESET}")
    
    def _display_execution_summary(self, final_state):
        """Display execution summary."""
        print(f"\n{Colors.BOLD}{Colors.GREEN}═══ EXECUTION SUMMARY ═══{Colors.RESET}")
        
        # Count results
        total_nodes = len(final_state.plan.nodes)
        successful_nodes = sum(1 for node in final_state.plan.nodes.values() 
                             if node.status in ['success', 'succeeded'])
        failed_nodes = total_nodes - successful_nodes
        
        # Calculate totals
        total_cost = sum(node.result.cost for node in final_state.plan.nodes.values() 
                        if node.result and node.result.cost)
        total_duration = sum(node.result.duration_ms for node in final_state.plan.nodes.values() 
                           if node.result and node.result.duration_ms)
        
        # Display summary
        print(f"{Colors.BOLD}Final Status:{Colors.RESET} {self._format_status(final_state.plan.status)}")
        print(f"{Colors.BOLD}Total Nodes:{Colors.RESET} {total_nodes}")
        print(f"{Colors.BOLD}Successful:{Colors.RESET} {Colors.GREEN}{successful_nodes}{Colors.RESET}")
        print(f"{Colors.BOLD}Failed:{Colors.RESET} {Colors.RED}{failed_nodes}{Colors.RESET}")
        print(f"{Colors.BOLD}Success Rate:{Colors.RESET} {(successful_nodes/total_nodes*100):.1f}%")
        
        if total_cost > 0:
            print(f"{Colors.BOLD}Total Cost:{Colors.RESET} ${total_cost:.4f}")
        if total_duration > 0:
            print(f"{Colors.BOLD}Total Duration:{Colors.RESET} {total_duration}ms")
        
        # Show node status breakdown
        print(f"\n{Colors.BOLD}Node Results:{Colors.RESET}")
        for node_id, node in final_state.plan.nodes.items():
            status = self._format_status(node.status)
            tool_name = node.uf_name
            print(f"  {Colors.CYAN}•{Colors.RESET} {node_id:<20} {status:<10} {Colors.DIM}({tool_name}){Colors.RESET}")
    
    def _format_status(self, status: str) -> str:
        """Format status with appropriate color."""
        status_colors = {
            'success': Colors.GREEN + Colors.BOLD,
            'failure': Colors.RED + Colors.BOLD,
            'running': Colors.YELLOW + Colors.BOLD,
            'pending': Colors.CYAN + Colors.BOLD,
            'succeeded': Colors.GREEN + Colors.BOLD,
            'failed': Colors.RED + Colors.BOLD,
            'unknown': Colors.DIM
        }
        color = status_colors.get(status.lower(), Colors.WHITE)
        return f"{color}{status.upper()}{Colors.RESET}"
    
    def save_execution(self, execution_data: Dict[str, Any], filename: str = None):
        """Save execution data to file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ufflow_execution_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(execution_data, f, indent=2, default=str)
            print(f"{Colors.GREEN}✅ Execution saved to {filename}{Colors.RESET}")
            return filename
        except Exception as e:
            print(f"{Colors.RED}❌ Error saving execution: {e}{Colors.RESET}")
            return None
    
    def explore_execution(self, execution_data: Dict[str, Any]):
        """Explore execution data using CLI UI."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXPLORING EXECUTION ═══{Colors.RESET}")
        
        # Create temporary file for CLI UI using path manager
        from core.path_manager import get_tmp_file
        import uuid
        temp_filename = f"cli_ui_data_{uuid.uuid4().hex[:8]}"
        temp_file = get_tmp_file(temp_filename, "json")

        with open(temp_file, 'w') as f:
            json.dump(execution_data, f, indent=2, default=str)
        
        try:
            # Create CLI UI instance
            cli = UFFLOWCLI(temp_file)
            cli.run_interactive()
        finally:
            # Clean up temporary file
            os.unlink(temp_file)
    
    def display_main_menu(self):
        """Display the main interactive menu."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗")
        print(f"║                        INTERACTIVE UFFLOW FRAMEWORK                        ║")
        print(f"║                      Create, Execute, and Explore Goals                    ║")
        print(f"╚══════════════════════════════════════════════════════════════════════════════╝{Colors.RESET}")
        
        print(f"\n{Colors.GREEN}Available Commands:{Colors.RESET}")
        print(f"  {Colors.BOLD}create{Colors.RESET}     - Create a new goal (custom)")
        print(f"  {Colors.BOLD}template{Colors.RESET}   - Create goal from template")
        print(f"  {Colors.BOLD}execute{Colors.RESET}    - Execute current goal with interactive orchestrator")
        print(f"  {Colors.BOLD}run{Colors.RESET}        - Execute current goal with standard orchestrator")
        print(f"  {Colors.BOLD}explore{Colors.RESET}    - Explore last execution with CLI UI")
        print(f"  {Colors.BOLD}save{Colors.RESET}       - Save last execution to file")
        print(f"  {Colors.BOLD}history{Colors.RESET}    - Show execution history")
        print(f"  {Colors.BOLD}status{Colors.RESET}     - Show current status")
        print(f"  {Colors.BOLD}help{Colors.RESET}       - Show this help")
        print(f"  {Colors.BOLD}quit{Colors.RESET}       - Exit")
    
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
            print(f"{Colors.BOLD}Nodes Executed:{Colors.RESET} {summary.get('total_nodes', 0)}")
            print(f"{Colors.BOLD}Success Rate:{Colors.RESET} {(summary.get('successful_nodes', 0) / max(summary.get('total_nodes', 1), 1) * 100):.1f}%")
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
            print(f"   Status: {summary.get('final_status', 'unknown')}")
            print(f"   Nodes: {summary.get('total_nodes', 0)}")
            print(f"   Success Rate: {(summary.get('successful_nodes', 0) / max(summary.get('total_nodes', 1), 1) * 100):.1f}%")
            print(f"   Timestamp: {summary.get('timestamp', 'N/A')}")
    
    def run_interactive(self):
        """Run the interactive UFFLOW session."""
        print(f"{Colors.GREEN}🚀 Starting Interactive UFFLOW Framework{Colors.RESET}")
        
        # Setup UFFLOW
        if not self.setup_ufflow():
            return
        
        # Auto-start with goal creation mode
        print(f"\n{Colors.YELLOW}🚀 Let's start by creating a goal!{Colors.RESET}")
        
        # Go directly to goal creation
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
                command = input(f"\n{Colors.CYAN}ufflow> {Colors.RESET}").strip().lower()
                
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
                        self.current_execution = self.execute_goal(self.current_goal)

                elif command == 'run':
                    if not self.current_goal:
                        print(f"{Colors.RED}❌ No current goal. Create one first.{Colors.RESET}")
                    else:
                        self.current_execution = self._execute_goal_standard(self.current_goal)
                
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
        description="Interactive UFFLOW Framework - Create, Execute, and Explore Goals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python interactive_ufflow.py                    # Start interactive session
  python interactive_ufflow.py --help            # Show help
        """
    )
    
    args = parser.parse_args()
    
    # Create and run interactive UFFLOW
    interactive_ufflow = InteractiveUFFLOW()
    interactive_ufflow.run_interactive()

if __name__ == "__main__":
    main()
