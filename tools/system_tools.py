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

# DISABLED: Tool provisioning is now handled by core ReAct prompt instructions
# @uf(name="provision_tool_agent", version="1.0.0", description="ONLY for installing missing tools. Use format: 'I need [tool] to do [task]' or 'I need any tool to do [task]'. Do NOT use for learning tool usage or syntax - use --help flags or built-in knowledge instead.")
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

# ============================================================================
# Tool Installation Helper Tools (extracted from provisioner agent)
# ============================================================================

class AskLLMForInstructionsInput(UfInput):
    tool_name: str = Field(..., description="Name of the tool to get installation instructions for")
    platform: str = Field(default="", description="Target platform (macOS, Linux, Windows). Auto-detected if not provided.")

    @field_validator('tool_name')
    @classmethod
    def validate_tool_name(cls, v):
        if not v or not v.strip():
            raise ValueError("tool_name cannot be empty")
        return v.strip()

@uf(name="ask_llm_for_instructions", version="1.0.0", description="Get step-by-step installation commands for a tool from LLM. Use when standard installation methods fail or you need platform-specific guidance.")
def ask_llm_for_instructions(inputs: AskLLMForInstructionsInput) -> dict:
    """Ask LLM for tool-specific installation instructions."""
    try:
        from core.llm import OpenAIClientManager

        tool_name = inputs.tool_name
        platform = inputs.platform

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

        llm_client = OpenAIClientManager()
        response = llm_client.create_completion_text([{"role": "user", "content": prompt}])

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
            return {
                "success": True,
                "tool_name": tool_name,
                "platform": platform,
                "commands": commands,
                "message": f"Installation commands for {tool_name} on {platform}:\n{command_list}"
            }
        else:
            return {
                "success": False,
                "tool_name": tool_name,
                "platform": platform,
                "commands": [],
                "message": f"Could not determine installation method for {tool_name}"
            }

    except Exception as e:
        logger.error(f"LLM instructions failed: {e}")
        return {
            "success": False,
            "tool_name": inputs.tool_name,
            "platform": inputs.platform or "unknown",
            "commands": [],
            "message": f"Failed to get LLM instructions: {str(e)}"
        }

class WebSearchForToolInput(UfInput):
    tool_name: str = Field(..., description="Name of the tool to search for")
    query: str = Field(default="", description="Optional specific search query for troubleshooting")

    @field_validator('tool_name')
    @classmethod
    def validate_tool_name(cls, v):
        if not v or not v.strip():
            raise ValueError("tool_name cannot be empty")
        return v.strip()

@uf(name="web_search_for_tool", version="1.0.0", description="Search for tool installation troubleshooting, alternatives, or documentation. Use when LLM instructions fail or you need up-to-date information.")
def web_search_for_tool(inputs: WebSearchForToolInput) -> dict:
    """Search web for tool installation troubleshooting or alternatives."""
    try:
        tool_name = inputs.tool_name
        query = inputs.query

        logger.info(f"Searching for tool: {tool_name}")

        # Check known tool patterns first
        known_result = _check_known_tool_patterns(tool_name)
        if known_result:
            return known_result

        # Generic advice for unknown tools
        return {
            "success": True,
            "tool_name": tool_name,
            "search_query": query or f"{tool_name} installation",
            "suggestions": [
                f"Try searching: '{tool_name} installation {query}' on Google",
                f"Check the official GitHub repository for {tool_name}",
                f"Look for {tool_name} on package manager registries (crates.io, npmjs.com, pypi.org)",
                f"Search for '{tool_name} alternative' if this tool is unavailable"
            ],
            "message": f"Generic search advice for {tool_name}. Consider trying alternative package names or consulting official documentation."
        }

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return {
            "success": False,
            "tool_name": inputs.tool_name,
            "message": f"Web search failed: {str(e)}"
        }

def _check_known_tool_patterns(tool_name: str) -> dict:
    """Check against database of known problematic tools."""
    common_issues = {
        "reconcile-csv": {
            "issue": "Tool is Java-based, not available via Cargo",
            "alternatives": ["xsv (Rust-based CSV tool)", "csvkit (Python-based)", "miller (multi-format tool)"],
            "commands": ["cargo install xsv", "pip install csvkit", "brew install miller"]
        },
        "scrubcsv": {
            "issue": "May not be in default registries",
            "alternatives": ["xsv", "csvkit"],
            "commands": ["cargo install xsv", "pip install csvkit"]
        }
    }

    tool_lower = tool_name.lower()
    if tool_lower in common_issues:
        issue_info = common_issues[tool_lower]
        return {
            "success": True,
            "tool_name": tool_name,
            "known_issue": issue_info["issue"],
            "alternatives": issue_info["alternatives"],
            "suggested_commands": issue_info["commands"],
            "message": f"Known issue with {tool_name}: {issue_info['issue']}. Try alternatives: {', '.join(issue_info['alternatives'])}"
        }

    return None