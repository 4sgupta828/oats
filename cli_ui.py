#!/usr/bin/env python3
"""
UFFLOW Framework CLI UI Component

An interactive command-line interface for displaying and exploring UFFLOW execution details.
Provides detailed views of goals, plans, node execution, inputs/outputs, and summaries.

Usage:
    python cli_ui.py [execution_data_file]
    
Examples:
    python cli_ui.py ufflow_log_analysis_results.json
    python cli_ui.py  # Interactive mode with sample data
"""

import sys
import os
import json
import readline
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime
import textwrap
import shutil

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

class Box:
    """Utility class for creating boxed content."""
    
    @staticmethod
    def create_box(content: str, title: str = "", color: str = Colors.WHITE, width: int = 80) -> str:
        """Create a boxed content with title."""
        lines = content.split('\n')
        max_line_length = max(len(line) for line in lines) if lines else 0
        box_width = max(max_line_length + 4, len(title) + 4, width)
        
        # Create top border
        top_border = "┌" + "─" * (box_width - 2) + "┐"
        if title:
            title_line = f"│ {title:<{box_width - 4}} │"
        else:
            title_line = "│" + " " * (box_width - 2) + "│"
        
        # Create content lines
        content_lines = []
        for line in lines:
            padded_line = line.ljust(box_width - 4)
            content_lines.append(f"│ {padded_line} │")
        
        # Create bottom border
        bottom_border = "└" + "─" * (box_width - 2) + "┘"
        
        # Combine all parts
        box_parts = [top_border]
        if title:
            box_parts.append(title_line)
            box_parts.append("├" + "─" * (box_width - 2) + "┤")
        box_parts.extend(content_lines)
        box_parts.append(bottom_border)
        
        return color + '\n'.join(box_parts) + Colors.RESET
    
    @staticmethod
    def create_section(content: str, title: str = "", color: str = Colors.CYAN) -> str:
        """Create a section header with content."""
        if not title:
            return content
        
        header = f"\n{color}{Colors.BOLD}═══ {title} ═══{Colors.RESET}\n"
        return header + content

class UFFLOWCLI:
    """Interactive CLI for UFFLOW execution data."""
    
    def __init__(self, data_file: Optional[str] = None):
        self.data_file = data_file
        self.execution_data = None
        self.current_view = "main"
        self.terminal_width = shutil.get_terminal_size().columns
        
    def load_data(self) -> bool:
        """Load execution data from file or create sample data."""
        if self.data_file and os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    self.execution_data = json.load(f)
                print(f"{Colors.GREEN}✅ Loaded data from {self.data_file}{Colors.RESET}")
                return True
            except Exception as e:
                print(f"{Colors.RED}❌ Error loading data: {e}{Colors.RESET}")
                return False
        else:
            # Create sample data for demonstration
            self.execution_data = self._create_sample_data()
            print(f"{Colors.YELLOW}📊 Using sample data for demonstration{Colors.RESET}")
            return True
    
    def _create_sample_data(self) -> Dict[str, Any]:
        """Create sample execution data for demonstration."""
        return {
            "goal": {
                "id": "log-analysis-abc123",
                "description": "search for all ERROR lines in log file and extract the log line that would be emitted by code and then search for all places in code where that line is emitted (with filenames, line numbers)",
                "constraints": {
                    "log_file": "/path/to/sample_server.log",
                    "code_directory": "/path/to/sample_code",
                    "file_extensions": [".java", ".js", ".py"],
                    "output_format": "json"
                }
            },
            "plan": {
                "id": "plan-xyz789",
                "goal_id": "log-analysis-abc123",
                "status": "succeeded",
                "graph": {
                    "read-log-file": ["extract-errors"],
                    "extract-errors": ["search-source-code"],
                    "search-source-code": ["generate-report"]
                },
                "nodes": {
                    "read-log-file": {
                        "id": "read-log-file",
                        "uf_name": "read_file:1.0.0",
                        "status": "success",
                        "input_resolver": {
                            "data_mapping": {
                                "filename": {
                                    "source": "literal",
                                    "value_selector": "sample_server.log"
                                }
                            }
                        },
                        "result": {
                            "status": "success",
                            "output": "2024-01-15 10:30:45.123 INFO [main] ServerStartup - Server starting on port 8080\n2024-01-15 10:30:47.112 ERROR [auth-worker] AuthenticationService - Failed to authenticate user: invalid credentials provided\n2024-01-15 10:31:16.221 ERROR [database-pool] ConnectionManager - Database connection failed: timeout after 30 seconds",
                            "error": None,
                            "cost": 0.001,
                            "duration_ms": 150
                        }
                    },
                    "extract-errors": {
                        "id": "extract-errors",
                        "uf_name": "execute_shell:2.0.0",
                        "status": "success",
                        "input_resolver": {
                            "data_mapping": {
                                "command": {
                                    "source": "literal",
                                    "value_selector": "grep 'ERROR'"
                                },
                                "input_data": {
                                    "source": "upstream",
                                    "value_selector": "output",
                                    "node_id": "read-log-file"
                                }
                            }
                        },
                        "result": {
                            "status": "success",
                            "output": {
                                "stdout": "2024-01-15 10:30:47.112 ERROR [auth-worker] AuthenticationService - Failed to authenticate user: invalid credentials provided\n2024-01-15 10:31:16.221 ERROR [database-pool] ConnectionManager - Database connection failed: timeout after 30 seconds",
                                "stderr": "",
                                "return_code": 0,
                                "success": True
                            },
                            "error": None,
                            "cost": 0.002,
                            "duration_ms": 200
                        }
                    },
                    "search-source-code": {
                        "id": "search-source-code",
                        "uf_name": "execute_task_script:1.0.0",
                        "status": "success",
                        "input_resolver": {
                            "data_mapping": {
                                "script_content": {
                                    "source": "literal",
                                    "value_selector": "#!/bin/bash\ngrep -rn 'Failed to authenticate user' /path/to/sample_code"
                                },
                                "input_data": {
                                    "source": "upstream",
                                    "value_selector": "output.stdout",
                                    "node_id": "extract-errors"
                                }
                            }
                        },
                        "result": {
                            "status": "success",
                            "output": {
                                "output": "AuthenticationService.java:12:logger.severe(\"Failed to authenticate user: invalid credentials provided\");\nAuthenticationService.java:19:logger.severe(\"Failed to authenticate user: invalid credentials provided\");",
                                "error": "",
                                "return_code": 0,
                                "success": True
                            },
                            "error": None,
                            "cost": 0.005,
                            "duration_ms": 500
                        }
                    },
                    "generate-report": {
                        "id": "generate-report",
                        "uf_name": "create_file:1.0.0",
                        "status": "success",
                        "input_resolver": {
                            "data_mapping": {
                                "filename": {
                                    "source": "literal",
                                    "value_selector": "analysis_report.json"
                                },
                                "content": {
                                    "source": "upstream",
                                    "value_selector": "output",
                                    "node_id": "search-source-code"
                                }
                            }
                        },
                        "result": {
                            "status": "success",
                            "output": {
                                "filepath": "analysis_report.json",
                                "size": 1024
                            },
                            "error": None,
                            "cost": 0.001,
                            "duration_ms": 100
                        }
                    }
                }
            },
            "execution_summary": {
                "total_nodes": 4,
                "successful_nodes": 4,
                "failed_nodes": 0,
                "total_cost": 0.009,
                "total_duration_ms": 950,
                "final_status": "succeeded"
            }
        }
    
    def display_welcome(self):
        """Display welcome message and instructions."""
        welcome_text = f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║                          UFFLOW Framework CLI UI                          ║
║                        Interactive Execution Explorer                      ║
╚══════════════════════════════════════════════════════════════════════════════╝{Colors.RESET}

{Colors.YELLOW}Welcome to the UFFLOW Framework CLI!{Colors.RESET}

This interactive interface allows you to explore:
• Goal definitions and constraints
• Generated execution plans
• Node-by-node execution details
• Input/output data for each step
• Success/failure status and error details
• Comprehensive execution summaries

{Colors.GREEN}Available Commands:{Colors.RESET}
  {Colors.BOLD}help{Colors.RESET}     - Show this help message
  {Colors.BOLD}goal{Colors.RESET}     - Display goal information
  {Colors.BOLD}plan{Colors.RESET}     - Display execution plan
  {Colors.BOLD}nodes{Colors.RESET}    - List all execution nodes
  {Colors.BOLD}node <id>{Colors.RESET} - Show detailed node information
  {Colors.BOLD}summary{Colors.RESET}  - Display execution summary
  {Colors.BOLD}raw{Colors.RESET}      - Show raw JSON data
  {Colors.BOLD}quit{Colors.RESET}     - Exit the application

{Colors.DIM}Terminal width: {self.terminal_width} characters{Colors.RESET}
"""
        print(welcome_text)
    
    def display_goal(self):
        """Display goal information."""
        if not self.execution_data or 'goal' not in self.execution_data:
            print(f"{Colors.RED}❌ No goal data available{Colors.RESET}")
            return
        
        goal = self.execution_data['goal']
        
        # Goal ID and Description
        goal_info = f"""
{Colors.BOLD}Goal ID:{Colors.RESET} {goal.get('id', 'N/A')}
{Colors.BOLD}Description:{Colors.RESET} {goal.get('description', 'N/A')}
"""
        
        # Constraints
        constraints = goal.get('constraints', {})
        if constraints:
            constraints_text = "\n".join([f"  {k}: {v}" for k, v in constraints.items()])
            constraints_box = Box.create_box(constraints_text, "Constraints", Colors.BLUE)
        else:
            constraints_box = Box.create_box("No constraints specified", "Constraints", Colors.YELLOW)
        
        print(Box.create_section(goal_info + constraints_box, "GOAL INFORMATION"))
    
    def display_plan(self):
        """Display execution plan information."""
        if not self.execution_data or 'plan' not in self.execution_data:
            print(f"{Colors.RED}❌ No plan data available{Colors.RESET}")
            return
        
        plan = self.execution_data['plan']
        
        # Plan Overview
        plan_info = f"""
{Colors.BOLD}Plan ID:{Colors.RESET} {plan.get('id', 'N/A')}
{Colors.BOLD}Goal ID:{Colors.RESET} {plan.get('goal_id', 'N/A')}
{Colors.BOLD}Status:{Colors.RESET} {self._format_status(plan.get('status', 'unknown'))}
{Colors.BOLD}Total Nodes:{Colors.RESET} {len(plan.get('nodes', {}))}
"""
        
        # Execution Graph
        graph = plan.get('graph', {})
        if graph:
            graph_text = "\n".join([f"  {node} → {', '.join(deps)}" for node, deps in graph.items()])
            graph_box = Box.create_box(graph_text, "Execution Graph", Colors.GREEN)
        else:
            graph_box = Box.create_box("No graph data available", "Execution Graph", Colors.YELLOW)
        
        # Node List
        nodes = plan.get('nodes', {})
        if nodes:
            node_list = []
            for node_id, node_data in nodes.items():
                status = self._format_status(node_data.get('status', 'unknown'))
                uf_name = node_data.get('uf_name', 'unknown')
                node_list.append(f"  {node_id:<20} {status:<10} {uf_name}")
            
            node_text = "\n".join(node_list)
            node_box = Box.create_box(node_text, "Execution Nodes", Colors.CYAN)
        else:
            node_box = Box.create_box("No nodes available", "Execution Nodes", Colors.YELLOW)
        
        print(Box.create_section(plan_info + graph_box + "\n" + node_box, "EXECUTION PLAN"))
    
    def display_nodes(self):
        """Display list of all nodes."""
        if not self.execution_data or 'plan' not in self.execution_data:
            print(f"{Colors.RED}❌ No plan data available{Colors.RESET}")
            return
        
        nodes = self.execution_data['plan'].get('nodes', {})
        if not nodes:
            print(f"{Colors.YELLOW}⚠️ No nodes available{Colors.RESET}")
            return
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══ EXECUTION NODES ═══{Colors.RESET}\n")
        
        for i, (node_id, node_data) in enumerate(nodes.items(), 1):
            status = self._format_status(node_data.get('status', 'unknown'))
            uf_name = node_data.get('uf_name', 'unknown')
            
            print(f"{Colors.BOLD}{i:2d}.{Colors.RESET} {Colors.CYAN}{node_id}{Colors.RESET}")
            print(f"     Status: {status}")
            print(f"     Tool:   {Colors.DIM}{uf_name}{Colors.RESET}")
            print()
    
    def display_node(self, node_id: str):
        """Display detailed information for a specific node."""
        if not self.execution_data or 'plan' not in self.execution_data:
            print(f"{Colors.RED}❌ No plan data available{Colors.RESET}")
            return
        
        nodes = self.execution_data['plan'].get('nodes', {})
        if node_id not in nodes:
            print(f"{Colors.RED}❌ Node '{node_id}' not found{Colors.RESET}")
            print(f"Available nodes: {', '.join(nodes.keys())}")
            return
        
        node_data = nodes[node_id]
        
        # Node Header
        header = f"""
{Colors.BOLD}Node ID:{Colors.RESET} {node_id}
{Colors.BOLD}Tool:{Colors.RESET} {node_data.get('uf_name', 'unknown')}
{Colors.BOLD}Status:{Colors.RESET} {self._format_status(node_data.get('status', 'unknown'))}
"""
        
        # Input Resolver
        input_resolver = node_data.get('input_resolver', {})
        if input_resolver:
            resolver_text = self._format_input_resolver(input_resolver)
            resolver_box = Box.create_box(resolver_text, "Input Resolver", Colors.BLUE)
        else:
            resolver_box = Box.create_box("No input resolver data", "Input Resolver", Colors.YELLOW)
        
        # Execution Result
        result = node_data.get('result')
        if result:
            result_text = self._format_execution_result(result)
            result_box = Box.create_box(result_text, "Execution Result", Colors.GREEN)
        else:
            result_box = Box.create_box("No execution result", "Execution Result", Colors.YELLOW)
        
        print(Box.create_section(header + resolver_box + "\n" + result_box, f"NODE: {node_id}"))
    
    def display_summary(self):
        """Display execution summary."""
        if not self.execution_data:
            print(f"{Colors.RED}❌ No execution data available{Colors.RESET}")
            return
        
        # Calculate summary if not provided
        if 'execution_summary' not in self.execution_data:
            summary = self._calculate_summary()
        else:
            summary = self.execution_data['execution_summary']
        
        # Summary Statistics
        stats_text = f"""
{Colors.BOLD}Total Nodes:{Colors.RESET} {summary.get('total_nodes', 0)}
{Colors.BOLD}Successful:{Colors.RESET} {Colors.GREEN}{summary.get('successful_nodes', 0)}{Colors.RESET}
{Colors.BOLD}Failed:{Colors.RESET} {Colors.RED}{summary.get('failed_nodes', 0)}{Colors.RESET}
{Colors.BOLD}Success Rate:{Colors.RESET} {(summary.get('successful_nodes', 0) / max(summary.get('total_nodes', 1), 1) * 100):.1f}%
{Colors.BOLD}Total Cost:{Colors.RESET} ${summary.get('total_cost', 0):.4f}
{Colors.BOLD}Total Duration:{Colors.RESET} {summary.get('total_duration_ms', 0)}ms
{Colors.BOLD}Final Status:{Colors.RESET} {self._format_status(summary.get('final_status', 'unknown'))}
"""
        
        # Node Status Breakdown
        if 'plan' in self.execution_data:
            nodes = self.execution_data['plan'].get('nodes', {})
            status_breakdown = []
            for node_id, node_data in nodes.items():
                status = node_data.get('status', 'unknown')
                status_breakdown.append(f"  {node_id:<20} {self._format_status(status)}")
            
            if status_breakdown:
                breakdown_text = "\n".join(status_breakdown)
                breakdown_box = Box.create_box(breakdown_text, "Node Status Breakdown", Colors.CYAN)
            else:
                breakdown_box = Box.create_box("No node data available", "Node Status Breakdown", Colors.YELLOW)
        else:
            breakdown_box = Box.create_box("No plan data available", "Node Status Breakdown", Colors.YELLOW)
        
        print(Box.create_section(stats_text + "\n" + breakdown_box, "EXECUTION SUMMARY"))
    
    def display_raw_data(self):
        """Display raw JSON data."""
        if not self.execution_data:
            print(f"{Colors.RED}❌ No execution data available{Colors.RESET}")
            return
        
        # Pretty print JSON with proper formatting
        json_str = json.dumps(self.execution_data, indent=2, default=str)
        
        # Wrap long lines
        wrapped_lines = []
        for line in json_str.split('\n'):
            if len(line) > self.terminal_width - 4:
                wrapped = textwrap.fill(line, width=self.terminal_width - 4, 
                                      initial_indent='', subsequent_indent='  ')
                wrapped_lines.append(wrapped)
            else:
                wrapped_lines.append(line)
        
        wrapped_json = '\n'.join(wrapped_lines)
        print(Box.create_box(wrapped_json, "Raw JSON Data", Colors.MAGENTA))
    
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
    
    def _format_input_resolver(self, resolver: Dict[str, Any]) -> str:
        """Format input resolver data."""
        lines = []
        
        # Data mapping
        data_mapping = resolver.get('data_mapping', {})
        if data_mapping:
            lines.append(f"{Colors.BOLD}Data Mapping:{Colors.RESET}")
            for input_name, mapping in data_mapping.items():
                source = mapping.get('source', 'unknown')
                value_selector = mapping.get('value_selector', 'unknown')
                node_id = mapping.get('node_id')
                
                line = f"  {input_name}: {source} -> {value_selector}"
                if node_id:
                    line += f" (from {node_id})"
                lines.append(line)
        
        # Invocation
        invocation = resolver.get('invocation', {})
        if invocation:
            lines.append(f"\n{Colors.BOLD}Invocation:{Colors.RESET}")
            lines.append(f"  Type: {invocation.get('type', 'unknown')}")
            lines.append(f"  Template: {invocation.get('template', 'unknown')}")
            
            params = invocation.get('params', {})
            if params:
                lines.append(f"  Params: {params}")
        
        return '\n'.join(lines) if lines else "No resolver data"
    
    def _format_execution_result(self, result: Dict[str, Any]) -> str:
        """Format execution result data."""
        lines = []
        
        # Basic info
        status = result.get('status', 'unknown')
        lines.append(f"{Colors.BOLD}Status:{Colors.RESET} {self._format_status(status)}")
        
        # Cost and duration
        cost = result.get('cost')
        if cost is not None:
            lines.append(f"{Colors.BOLD}Cost:{Colors.RESET} ${cost:.4f}")
        
        duration = result.get('duration_ms')
        if duration is not None:
            lines.append(f"{Colors.BOLD}Duration:{Colors.RESET} {duration}ms")
        
        # Output
        output = result.get('output')
        if output is not None:
            lines.append(f"\n{Colors.BOLD}Output:{Colors.RESET}")
            if isinstance(output, dict):
                for key, value in output.items():
                    if isinstance(value, str) and len(value) > 1000:
                        lines.append(f"  {key}: {value[:1000]}...")
                    else:
                        lines.append(f"  {key}: {value}")
            elif isinstance(output, str):
                if len(output) > 2000:
                    lines.append(f"  {output[:2000]}...")
                else:
                    lines.append(f"  {output}")
            else:
                lines.append(f"  {output}")
        
        # Error
        error = result.get('error')
        if error:
            lines.append(f"\n{Colors.BOLD}Error:{Colors.RESET} {Colors.RED}{error}{Colors.RESET}")
        
        return '\n'.join(lines) if lines else "No result data"
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate execution summary from plan data."""
        if 'plan' not in self.execution_data:
            return {}
        
        nodes = self.execution_data['plan'].get('nodes', {})
        total_nodes = len(nodes)
        successful_nodes = sum(1 for node in nodes.values() 
                             if node.get('status', '').lower() in ['success', 'succeeded'])
        failed_nodes = total_nodes - successful_nodes
        
        # Calculate total cost and duration
        total_cost = 0
        total_duration = 0
        for node in nodes.values():
            result = node.get('result', {})
            total_cost += result.get('cost', 0)
            total_duration += result.get('duration_ms', 0)
        
        # Determine final status
        plan_status = self.execution_data['plan'].get('status', 'unknown')
        if failed_nodes > 0:
            final_status = 'failed'
        elif successful_nodes == total_nodes and total_nodes > 0:
            final_status = 'succeeded'
        else:
            final_status = plan_status
        
        return {
            'total_nodes': total_nodes,
            'successful_nodes': successful_nodes,
            'failed_nodes': failed_nodes,
            'total_cost': total_cost,
            'total_duration_ms': total_duration,
            'final_status': final_status
        }
    
    def run_interactive(self):
        """Run the interactive CLI."""
        if not self.load_data():
            return
        
        self.display_welcome()
        
        while True:
            try:
                # Get user input
                command = input(f"\n{Colors.CYAN}ufflow> {Colors.RESET}").strip().lower()
                
                if not command:
                    continue
                
                # Parse command
                parts = command.split()
                cmd = parts[0]
                args = parts[1:] if len(parts) > 1 else []
                
                # Execute command
                if cmd in ['quit', 'exit', 'q']:
                    print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}")
                    break
                elif cmd == 'help' or cmd == 'h':
                    self.display_welcome()
                elif cmd == 'goal' or cmd == 'g':
                    self.display_goal()
                elif cmd == 'plan' or cmd == 'p':
                    self.display_plan()
                elif cmd == 'nodes' or cmd == 'n':
                    self.display_nodes()
                elif cmd == 'node':
                    if args:
                        self.display_node(args[0])
                    else:
                        print(f"{Colors.RED}❌ Please specify a node ID{Colors.RESET}")
                        print(f"Use 'nodes' to see available node IDs")
                elif cmd == 'summary' or cmd == 's':
                    self.display_summary()
                elif cmd == 'raw' or cmd == 'r':
                    self.display_raw_data()
                else:
                    print(f"{Colors.RED}❌ Unknown command: {cmd}{Colors.RESET}")
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
        description="UFFLOW Framework CLI UI - Interactive Execution Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_ui.py                                    # Interactive mode with sample data
  python cli_ui.py execution_results.json            # Load data from file
  python cli_ui.py ufflow_log_analysis_results.json  # Load UFFLOW results
        """
    )
    
    parser.add_argument(
        'data_file',
        nargs='?',
        default=None,
        help='JSON file containing UFFLOW execution data'
    )
    
    args = parser.parse_args()
    
    # Create and run CLI
    cli = UFFLOWCLI(args.data_file)
    cli.run_interactive()

if __name__ == "__main__":
    main()
