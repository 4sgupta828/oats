# uf_flow/orchestrator/input_resolver.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any
from core.models import PlanNode, WorldState
from core.logging_config import get_logger

# Initialize logging
logger = get_logger('input_resolver')

def resolve_inputs(node: PlanNode, world_state: WorldState) -> Dict[str, Any]:
    """
    Resolves the inputs for a PlanNode based on its input_resolver config
    and the current world state.
    """
    resolved_inputs = {}
    
    # Create a context for resolving values from upstream nodes
    upstream_outputs = {
        node_id: node.result.output
        for node_id, node in world_state.plan.nodes.items()
        if node.result and node.result.status == 'success'
    }

    for input_name, mapping in node.input_resolver.data_mapping.items():
        if mapping.source == "literal":
            # For now, we assume literals are pre-filled.
            resolved_inputs[input_name] = mapping.value_selector
        
        elif mapping.source == "context":
            # Resolve from goal constraints, world state context, or environment
            try:
                context_value = _resolve_context_value(mapping.value_selector, world_state)
                logger.debug(f"Resolved context '{mapping.value_selector}' to '{context_value}' for input '{input_name}'")
                resolved_inputs[input_name] = context_value
            except Exception as e:
                logger.error(f"Failed to resolve context value '{mapping.value_selector}' for input '{input_name}': {e}")
                # Provide reasonable defaults for common context values
                if mapping.value_selector in ["working_directory", "workspace.working_directory"]:
                    resolved_inputs[input_name] = "."
                    logger.info(f"Using default working directory '.' for input '{input_name}'")
                else:
                    raise RuntimeError(f"Failed to resolve context input '{input_name}' from '{mapping.value_selector}': {e}")
        
        elif mapping.source == "upstream":
            if not mapping.node_id:
                raise ValueError(f"Input '{input_name}' has source 'upstream' but no node_id.")
            
            # Simple dot notation selector, e.g., "user.id"
            # In a real system, you'd use a robust library like JMESPath or JSONPath.
            try:
                source_output = upstream_outputs.get(mapping.node_id)
                if source_output is None:
                    raise RuntimeError(f"No output found from node '{mapping.node_id}'")
                
                value = source_output
                # Handle the case where value_selector starts with "output."
                if mapping.value_selector.startswith("output."):
                    path = mapping.value_selector[7:]  # Remove "output." prefix
                elif mapping.value_selector == "output":
                    # If it's just "output", use the value directly
                    resolved_inputs[input_name] = value
                    continue
                else:
                    path = mapping.value_selector
                
                for key in path.split('.'):
                    if isinstance(value, dict):
                        value = value.get(key)
                    elif hasattr(value, key): # It might be a Pydantic model
                        value = getattr(value, key)
                    else:
                        # If it's a string and we're looking for 'content', return the string itself
                        if key == 'content' and isinstance(value, str):
                            value = value
                        else:
                            raise AttributeError(f"'{type(value).__name__}' object has no attribute '{key}'")
                
                # Handle None values gracefully
                if value is None:
                    print(f"Warning: Resolved value for '{input_name}' is None from path '{mapping.value_selector}'")
                    # For None values, try to provide a default or skip
                    if input_name in ['content', 'text', 'data']:
                        value = ""  # Provide empty string for text fields
                    else:
                        value = None
                
                # Convert value to string if it's a literal value (not from upstream)
                if mapping.source == "literal" and not isinstance(value, str):
                    value = str(value)
                
                resolved_inputs[input_name] = value
            except (KeyError, AttributeError) as e:
                raise RuntimeError(f"Failed to resolve upstream input '{input_name}' from node '{mapping.node_id}': {e}")
    logger.debug(f"Resolved inputs for node {node.id}: {resolved_inputs}")
    return resolved_inputs


def _resolve_context_value(value_selector: str, world_state: WorldState) -> Any:
    """Resolve a context value from the world state, goal constraints, or environment."""
    logger.debug(f"Resolving context value: {value_selector}")

    # Handle dot notation paths like "workspace.working_directory"
    path_parts = value_selector.split('.')

    # Start with potential context sources
    context_sources = {
        "goal": world_state.goal,
        "constraints": world_state.goal.constraints,
        "workspace": world_state.goal.constraints,  # Alias for constraints
        "environment": world_state.environment_data
    }

    # If it's a single value, check common contexts
    if len(path_parts) == 1:
        key = path_parts[0]

        # Check goal constraints first
        if world_state.goal.constraints and key in world_state.goal.constraints:
            return world_state.goal.constraints[key]

        # Check environment data
        if world_state.environment_data and key in world_state.environment_data:
            return world_state.environment_data[key]

        # Common default mappings
        defaults = {
            "working_directory": ".",
            "timeout": "60",
            "current_directory": "."
        }

        if key in defaults:
            logger.info(f"Using default value '{defaults[key]}' for context key '{key}'")
            return defaults[key]

    # Handle multi-part paths like "workspace.working_directory"
    elif len(path_parts) > 1:
        root_key = path_parts[0]
        remaining_path = path_parts[1:]

        # Get the root context object
        if root_key in context_sources:
            current_value = context_sources[root_key]

            # Navigate the path
            for part in remaining_path:
                if hasattr(current_value, part):
                    current_value = getattr(current_value, part)
                elif isinstance(current_value, dict) and part in current_value:
                    current_value = current_value[part]
                else:
                    # Handle common workspace context
                    if root_key == "workspace" and part == "working_directory":
                        # Check if it's in constraints
                        if world_state.goal.constraints and "working_directory" in world_state.goal.constraints:
                            return world_state.goal.constraints["working_directory"]
                        elif world_state.goal.constraints and "workspace_path" in world_state.goal.constraints:
                            return world_state.goal.constraints["workspace_path"]
                        else:
                            return "."

                    raise ValueError(f"Context path '{value_selector}' not found - missing '{part}' in {type(current_value)}")

            return current_value

    # If we get here, we couldn't resolve the value
    raise ValueError(f"Unable to resolve context value '{value_selector}' - not found in goal constraints, environment data, or defaults")