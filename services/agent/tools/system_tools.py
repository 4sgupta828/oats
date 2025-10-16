# tools/system_tools.py

import os
import sys
import logging
import subprocess
import shutil
from typing import List, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput

logger = logging.getLogger(__name__)

# ============================================================================
# Pre-Flight Capability Check Tool (P1 - Critical for Efficiency)
# ============================================================================

class CheckAvailableToolsInput(UfInput):
    """Input for checking available system tools."""
    tool_categories: Optional[List[str]] = Field(
        default=None,
        description="Optional list of tool categories to check: 'kubernetes', 'aws', 'database', 'network', 'all'. If None, checks all."
    )

@uf(name="check_available_tools", version="1.0.0",
    description="Pre-flight check to discover what CLI tools are available in the environment. Use this FIRST before attempting infrastructure operations to avoid wasted turns.")
def check_available_tools(inputs: CheckAvailableToolsInput) -> dict:
    """
    Check availability of common infrastructure and cloud tools.
    Returns a comprehensive report of what tools are installed and their versions.
    """
    try:
        # Define tool categories
        tool_definitions = {
            "kubernetes": [
                "kubectl", "helm", "k9s", "kubectx", "kubens", "stern", "eksctl"
            ],
            "aws": [
                "aws", "eksctl", "sam", "cdk"
            ],
            "azure": [
                "az"
            ],
            "gcp": [
                "gcloud", "gsutil"
            ],
            "database": [
                "psql", "mysql", "redis-cli", "mongosh", "mongo"
            ],
            "network": [
                "curl", "wget", "nc", "netcat", "dig", "nslookup", "ping", "telnet", "traceroute", "nmap"
            ],
            "process": [
                "ps", "top", "htop", "lsof", "strace"
            ],
            "text": [
                "jq", "yq", "grep", "awk", "sed", "vim", "nano"
            ],
            "version_control": [
                "git"
            ],
            "containers": [
                "docker", "podman", "crictl"
            ]
        }

        # Determine which categories to check
        categories_to_check = inputs.tool_categories or list(tool_definitions.keys())
        if "all" in categories_to_check:
            categories_to_check = list(tool_definitions.keys())

        available_tools = {}
        unavailable_tools = {}
        tool_versions = {}

        total_checked = 0
        total_available = 0

        for category in categories_to_check:
            if category not in tool_definitions:
                continue

            available_tools[category] = []
            unavailable_tools[category] = []

            for tool in tool_definitions[category]:
                total_checked += 1

                # Check if tool exists using 'which'
                tool_path = shutil.which(tool)

                if tool_path:
                    available_tools[category].append(tool)
                    total_available += 1

                    # Try to get version
                    version = None
                    version_commands = [
                        [tool, "--version"],
                        [tool, "version"],
                        [tool, "-v"],
                        [tool, "-version"]
                    ]

                    for ver_cmd in version_commands:
                        try:
                            result = subprocess.run(
                                ver_cmd,
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                # Take first line of output
                                version = result.stdout.strip().split('\n')[0][:100]
                                break
                            elif result.stderr.strip():
                                version = result.stderr.strip().split('\n')[0][:100]
                                break
                        except:
                            continue

                    tool_versions[tool] = {
                        "path": tool_path,
                        "version": version or "unknown"
                    }
                else:
                    unavailable_tools[category].append(tool)

        # Create summary
        summary = {
            "total_checked": total_checked,
            "total_available": total_available,
            "total_unavailable": total_checked - total_available,
            "availability_percentage": round((total_available / total_checked) * 100, 1) if total_checked > 0 else 0
        }

        # Create recommendations
        recommendations = []

        # Check critical tools
        if "kubectl" not in [t for cat in available_tools.values() for t in cat]:
            recommendations.append("⚠ kubectl not found - Kubernetes operations will require Python client")
        if "curl" not in [t for cat in available_tools.values() for t in cat]:
            recommendations.append("⚠ curl not found - HTTP operations will require Python requests")
        if "aws" not in [t for cat in available_tools.values() for t in cat]:
            recommendations.append("⚠ aws CLI not found - AWS operations will require boto3")
        if "jq" not in [t for cat in available_tools.values() for t in cat]:
            recommendations.append("⚠ jq not found - JSON processing will require Python")
        if "ps" not in [t for cat in available_tools.values() for t in cat]:
            recommendations.append("⚠ ps not found - Process inspection limited")

        return {
            "success": True,
            "summary": summary,
            "available_tools": available_tools,
            "unavailable_tools": unavailable_tools,
            "tool_versions": tool_versions,
            "recommendations": recommendations,
            "message": f"Tool check complete: {total_available}/{total_checked} tools available ({summary['availability_percentage']}%)"
        }

    except Exception as e:
        logger.error(f"Tool availability check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to check tool availability: {e}"
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