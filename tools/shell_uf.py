#!/usr/bin/env python3
"""
Shell Script UF Wrapper - Simple wrapper to register shell scripts as UFs
"""

import os
import sys
import subprocess
import tempfile
from typing import Dict, Any

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sdk import uf, UfInput
from pydantic import Field

class ShellUFInput(UfInput):
    """Input model for shell script UFs."""
    input_data: str = Field(default="", description="Input data to pass to the script via stdin")
    working_directory: str = Field(default=".", description="Working directory for script execution")
    timeout: int = Field(default=60, description="Timeout in seconds")

def create_shell_uf(script_path: str, uf_id: str, description: str) -> callable:
    """
    Create a UF function from a shell script.
    
    Args:
        script_path: Path to the shell script
        uf_id: Unique identifier for the UF
        description: Description of what the script does
    
    Returns:
        A UF function that can be registered
    """
    
    @uf(name=uf_id, version="1.0.0", description=description)
    def shell_uf_func(inputs: ShellUFInput) -> Dict[str, Any]:
        """
        Execute the shell script with the given inputs.
        """
        try:
            # Execute the script
            result = subprocess.run(
                [script_path],
                input=inputs.input_data,
                text=True,
                capture_output=True,
                cwd=inputs.working_directory,
                timeout=inputs.timeout
            )
            
            return {
                "output": result.stdout,
                "error": result.stderr,
                "return_code": result.returncode,
                "success": result.returncode == 0,
                "script_path": script_path
            }
            
        except subprocess.TimeoutExpired:
            return {
                "output": "",
                "error": f"Script execution timed out after {inputs.timeout} seconds",
                "return_code": -1,
                "success": False,
                "script_path": script_path
            }
        except Exception as e:
            return {
                "output": "",
                "error": str(e),
                "return_code": -1,
                "success": False,
                "script_path": script_path
            }
    
    return shell_uf_func
