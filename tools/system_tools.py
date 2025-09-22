# tools/system_tools.py

import os
import sys
import shutil
import logging
from typing import Dict, Any, List, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput

logger = logging.getLogger(__name__)

class CheckCommandInput(UfInput):
    command_name: str = Field(..., description="Name of the command to check for existence")

    @field_validator('command_name')
    @classmethod
    def validate_command_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Command name cannot be empty")
        return v.strip()

class ProvisionToolInput(UfInput):
    goal: str = Field(..., description="Description of what tool is needed and why")

    @field_validator('goal')
    @classmethod
    def validate_goal(cls, v):
        if not v or not v.strip():
            raise ValueError("Goal cannot be empty")
        return v.strip()

@uf(name="check_command_exists", version="1.0.0", description="Check if a command/tool exists on the system using cross-platform detection.")
def check_command_exists(inputs: CheckCommandInput) -> dict:
    """Check if a command exists on the system using shutil.which() for cross-platform compatibility."""
    try:
        logger.info(f"Checking if command '{inputs.command_name}' exists")

        # Use shutil.which for cross-platform command detection
        command_path = shutil.which(inputs.command_name)
        exists = command_path is not None

        result = {
            "exists": exists,
            "path": command_path,
            "command_name": inputs.command_name
        }

        if exists:
            logger.info(f"Command '{inputs.command_name}' found at: {command_path}")
        else:
            logger.info(f"Command '{inputs.command_name}' not found on system")

        return result

    except Exception as e:
        logger.error(f"Error checking command existence: {e}")
        return {
            "exists": False,
            "path": None,
            "command_name": inputs.command_name,
            "error": str(e)
        }

@uf(name="provision_tool_agent", version="1.0.0", description="ONLY for installing missing tools. Use format: 'I need [tool] to do [task]' or 'I need any tool to do [task]'. Do NOT use for learning tool usage or syntax - use --help flags or built-in knowledge instead.")
def provision_tool_agent(inputs: ProvisionToolInput) -> dict:
    """Delegate tool installation to the Tool Provisioning Agent. ONLY USE FOR INSTALLING TOOLS, NOT FOR LEARNING HOW TO USE THEM."""
    try:
        logger.info(f"Delegating to Tool Provisioning Agent: {inputs.goal}")

        # Import here to avoid circular imports
        from agents.provisioner import ToolProvisioningAgent
        from registry.main import global_registry

        # Create and run the Tool Provisioning Agent with live updates
        agent = ToolProvisioningAgent(registry=global_registry)
        result = agent.run(inputs.goal, show_live_updates=True)

        # If tool was successfully installed, attempt to refresh registry
        if result.get("success") and result.get("tool_name"):
            try:
                logger.info(f"Attempting to refresh registry for newly installed tool: {result['tool_name']}")
                agent.refresh_registry_for_tool(result["tool_name"])
                result["registry_updated"] = True
            except Exception as e:
                logger.warning(f"Failed to register newly installed tool {result['tool_name']}: {e}")
                result["registry_updated"] = False
                result["registry_error"] = str(e)

        return result

    except Exception as e:
        logger.error(f"Tool Provisioning Agent failed: {e}")
        return {
            "success": False,
            "tool_name": None,
            "message": f"Tool provisioning agent failed: {str(e)}",
            "error_type": "agent_failure",
            "suggested_alternatives": [
                "Try manual installation using shell commands",
                "Use built-in alternatives",
                "Search for alternative tools"
            ]
        }