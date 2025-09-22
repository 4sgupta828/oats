# uf_flow/orchestrator/main.py

import sys
import os
import time
from typing import Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import Goal, Plan, WorldState, ToolResult
from core.logging_config import get_logger, UFFlowLogger
from registry.main import global_registry
from executor.main import execute_tool
from memory.main import global_memory
from orchestrator.graph_utils import topological_sort
from orchestrator.input_resolver import resolve_inputs

# Initialize logging
logger = get_logger('orchestrator')

class OrchestrationError(Exception):
    """Custom exception for orchestration errors."""
    def __init__(self, message: str, node_id: str = None, error_type: str = "general"):
        super().__init__(message)
        self.node_id = node_id
        self.error_type = error_type


class Orchestrator:
    """
    The brain of the agent. It runs a plan to achieve a goal with enhanced error handling and logging.
    """

    def __init__(self):
        self.execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0
        }

    def _validate_plan(self, plan: Plan) -> None:
        """Validate plan structure before execution."""
        if not plan.nodes:
            raise OrchestrationError("Plan has no nodes to execute", error_type="validation")

        # Check that all graph references exist
        for node_id, dependencies in plan.graph.items():
            if node_id not in plan.nodes:
                raise OrchestrationError(f"Graph references non-existent node: {node_id}", error_type="validation")

            for dep in dependencies:
                if dep not in plan.nodes:
                    raise OrchestrationError(f"Node {node_id} depends on non-existent node: {dep}", error_type="validation")

    def _resolve_tool_descriptor(self, node_id: str, uf_name: str):
        """Resolve tool descriptor with proper error handling."""
        try:
            if ':' in uf_name:
                tool_name, tool_version = uf_name.split(':', 1)
            else:
                tool_name = uf_name
                tool_version = "1.0.0"

            uf_descriptor = global_registry.get_uf(tool_name, tool_version)
            if not uf_descriptor:
                available_tools = [f"{desc.name}:{desc.version}" for desc in global_registry.list_ufs()]
                raise OrchestrationError(
                    f"Tool '{uf_name}' not found. Available tools: {', '.join(available_tools)}",
                    node_id=node_id,
                    error_type="tool_not_found"
                )

            return uf_descriptor
        except Exception as e:
            if isinstance(e, OrchestrationError):
                raise
            raise OrchestrationError(f"Error resolving tool '{uf_name}': {e}", node_id=node_id, error_type="tool_resolution")

    def _execute_node(self, node_id: str, world_state: WorldState) -> ToolResult:
        """Execute a single node with comprehensive error handling."""
        node = world_state.plan.nodes[node_id]
        node_start_time = time.time()

        try:
            logger.info(f"Starting execution of node: {node_id} ({node.uf_name})")

            # 1. ORIENT: Resolve inputs
            logger.debug(f"Resolving inputs for node {node_id}")
            inputs = resolve_inputs(node, world_state)
            logger.debug(f"Resolved {len(inputs)} inputs for node {node_id}")

            # 2. DECIDE: Get the tool definition
            uf_descriptor = self._resolve_tool_descriptor(node_id, node.uf_name)

            # 3. ACT: Execute the tool
            logger.info(f"Executing tool {node.uf_name} for node {node_id}")
            result = execute_tool(uf_descriptor, inputs)

            # 4. OBSERVE: Record the result
            if hasattr(global_memory, 'remember'):
                global_memory.remember(result)

            execution_time = time.time() - node_start_time
            logger.info(f"Node {node_id} completed in {execution_time:.2f}s with status: {result.status}")

            return result

        except Exception as e:
            execution_time = time.time() - node_start_time
            logger.error(f"Node {node_id} failed after {execution_time:.2f}s: {e}")

            # Create error result
            error_result = ToolResult(
                status="failure",
                output=None,
                error=str(e),
                duration_ms=int(execution_time * 1000)
            )

            if isinstance(e, OrchestrationError):
                raise e
            raise OrchestrationError(f"Node execution failed: {e}", node_id=node_id, error_type="execution")

    def run_goal(self, goal: Goal, plan: Plan) -> WorldState:
        """
        Executes a plan to achieve a goal with enhanced error handling, logging, and state management.
        """
        start_time = time.time()
        self.execution_stats["total_executions"] += 1

        UFFlowLogger.log_execution_start(
            "orchestrator",
            "run_goal",
            goal_id=goal.id,
            plan_id=plan.id,
            node_count=len(plan.nodes)
        )

        world_state = WorldState(goal=goal, plan=plan)
        executed_nodes = []
        failed_node: Optional[str] = None

        try:
            logger.info(f"Starting goal execution: {goal.id} with plan: {plan.id}")
            logger.info(f"Plan has {len(plan.nodes)} nodes: {list(plan.nodes.keys())}")

            # Validate plan structure
            self._validate_plan(plan)

            # Determine execution order
            try:
                execution_order = topological_sort(plan.graph)
                logger.info(f"Execution order determined: {' → '.join(execution_order)}")
            except ValueError as e:
                raise OrchestrationError(f"Invalid plan graph: {e}", error_type="graph_validation")

            # Execute nodes in order
            for i, node_id in enumerate(execution_order, 1):
                node = world_state.plan.nodes[node_id]
                node.status = "running"

                logger.info(f"Executing node {i}/{len(execution_order)}: {node_id}")

                try:
                    result = self._execute_node(node_id, world_state)

                    # Update node state
                    node.result = result
                    node.status = result.status
                    world_state.execution_history.append(result)
                    executed_nodes.append(node_id)

                    if result.status == "failure":
                        failed_node = node_id
                        logger.error(f"Node {node_id} failed: {result.error}")
                        world_state.plan.status = "failed"
                        break
                    else:
                        logger.info(f"Node {node_id} completed successfully")

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
                    logger.error(f"Orchestration error in node {node_id}: {e}")
                    break

            # Set final status
            if world_state.plan.status != "failed":
                world_state.plan.status = "succeeded"
                self.execution_stats["successful_executions"] += 1
                logger.info(f"Goal execution completed successfully: {goal.id}")
            else:
                self.execution_stats["failed_executions"] += 1
                logger.error(f"Goal execution failed at node {failed_node}: {goal.id}")

            duration = time.time() - start_time

            UFFlowLogger.log_execution_end(
                "orchestrator",
                "run_goal",
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

            logger.error(f"Unexpected error during goal execution: {e}")
            world_state.plan.status = "failed"

            UFFlowLogger.log_execution_end(
                "orchestrator",
                "run_goal",
                False,
                duration_ms=int(duration * 1000),
                executed_nodes=executed_nodes,
                error_type="unexpected",
                error_message=str(e)
            )

            return world_state

    def get_execution_stats(self) -> dict:
        """Get execution statistics."""
        total = self.execution_stats["total_executions"]
        if total == 0:
            return {**self.execution_stats, "success_rate": 0.0}

        success_rate = self.execution_stats["successful_executions"] / total
        return {**self.execution_stats, "success_rate": success_rate}