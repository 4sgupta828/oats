# tools/system_tools.py

import os
import sys
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput

logger = logging.getLogger(__name__)

class ProvisionToolInput(UfInput):
    goal: str = Field(..., description="Description of what tool is needed and why")
    auto_mode: bool = Field(default=True, description="Skip user confirmations and automatically approve installations")

    @field_validator('goal')
    @classmethod
    def validate_goal(cls, v):
        if not v or not v.strip():
            raise ValueError("Goal cannot be empty")
        return v.strip()

@uf(name="provision_tool_agent", version="1.0.0", description="ONLY for installing missing tools. Use format: 'I need [tool] to do [task]' or 'I need any tool to do [task]'. Do NOT use for learning tool usage or syntax - use --help flags or built-in knowledge instead.")
def provision_tool_agent(inputs: ProvisionToolInput) -> dict:
    """Delegate tool installation to the Tool Provisioning Agent. ONLY USE FOR INSTALLING TOOLS, NOT FOR LEARNING HOW TO USE THEM."""
    try:
        logger.info(f"Delegating to Tool Provisioning Agent: {inputs.goal}")

        # Import here to avoid circular imports
        from agents.provisioner import ToolProvisioningAgent
        from registry.main import global_registry

        # Create and run the Tool Provisioning Agent with live updates
        agent = ToolProvisioningAgent(registry=global_registry, auto_mode=inputs.auto_mode)
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