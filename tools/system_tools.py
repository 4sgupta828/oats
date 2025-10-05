# tools/system_tools.py

import os
import sys
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput

logger = logging.getLogger(__name__)

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