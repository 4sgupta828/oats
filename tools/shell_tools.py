import os
import sys
import subprocess
import tempfile
import shlex
import logging
from pathlib import Path
from typing import List, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field, field_validator
from core.sdk import uf, UfInput
from core.workspace_security import get_workspace_security

# Configure logging
logger = logging.getLogger(__name__)

class ExecuteShellInput(UfInput):
    command: str = Field(..., description="The shell command to execute.")
    working_directory: str = Field(default=".", description="Working directory for the command.")
    timeout: int = Field(default=30, description="Timeout in seconds for command execution.")
    input_data: str = Field(default="", description="Input data to pass to the command via stdin.")
    input_file: str = Field(default="", description="Path to input file to use instead of stdin.")
    allowed_commands: Optional[List[str]] = Field(
        default=["ls", "cat", "grep", "find", "head", "tail", "wc", "sort", "uniq", "awk", "sed", "cut", "tr", "xargs", "echo", "printf"],
        description="List of allowed base commands for security"
    )

    @field_validator('command')
    @classmethod
    def validate_command(cls, v):
        """Validate command for security using workspace security."""
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")

        try:
            # Use workspace security for validation
            workspace_security = get_workspace_security()
            validated_command = workspace_security.validate_command(v)
            return validated_command
        except Exception as e:
            logger.error(f"Command validation failed: {e}")
            raise ValueError(f"Command validation failed: {e}")

    @field_validator('working_directory')
    @classmethod
    def validate_working_directory(cls, v):
        """Validate working directory using workspace security."""
        if not v:
            return "."

        try:
            # Use workspace security for path validation
            workspace_security = get_workspace_security()
            validated_path = workspace_security.validate_path(v, "working directory")
            return validated_path
        except Exception as e:
            logger.error(f"Working directory validation failed: {e}")
            raise ValueError(f"Working directory validation failed: {e}")

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        """Ensure timeout is reasonable."""
        if v <= 0 or v > 300:  # Max 5 minutes
            raise ValueError("Timeout must be between 1 and 300 seconds")
        return v

class ExecuteScriptInput(UfInput):
    script_content: str = Field(..., description="The script content to execute.")
    script_type: str = Field(default="bash", description="Type of script: bash, python, etc.")
    working_directory: str = Field(default=".", description="Working directory for the script.")
    timeout: int = Field(default=60, description="Timeout in seconds for script execution.")

    @field_validator('working_directory')
    @classmethod
    def validate_working_directory(cls, v):
        """Validate working directory using workspace security."""
        if not v:
            return "."

        try:
            workspace_security = get_workspace_security()
            validated_path = workspace_security.validate_path(v, "script working directory")
            return validated_path
        except Exception as e:
            logger.error(f"Script working directory validation failed: {e}")
            raise ValueError(f"Script working directory validation failed: {e}")

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        """Ensure timeout is reasonable."""
        if v <= 0 or v > 300:  # Max 5 minutes
            raise ValueError("Timeout must be between 1 and 300 seconds")
        return v


def _fix_grep_patterns(command: str) -> str:
    """Fix common grep pattern errors in commands."""
    import re

    # Fix unescaped OR operators in grep patterns
    # Look for grep -Hn 'pattern1|pattern2' and fix to 'pattern1\|pattern2'
    grep_pattern = r"grep\s+(-[^\s]*\s+)?'([^']*\|[^']*)'|grep\s+(-[^\s]*\s+)?\"([^\"]*\|[^\"]*)\"|\bgrep\s+(-[^\s]*\s+)?([^\s]*\|[^\s]*)"

    def fix_or_operator(match):
        # Extract the full match and the pattern part
        full_match = match.group(0)

        # Find the pattern part (inside quotes or unquoted)
        if "'" in full_match:
            # Single quoted pattern
            pattern_match = re.search(r"'([^']*)'", full_match)
            if pattern_match:
                original_pattern = pattern_match.group(1)
                # Fix unescaped | operators
                fixed_pattern = re.sub(r'(?<!\\)\|', r'\\|', original_pattern)
                return full_match.replace(f"'{original_pattern}'", f"'{fixed_pattern}'")
        elif '"' in full_match:
            # Double quoted pattern
            pattern_match = re.search(r'"([^"]*)"', full_match)
            if pattern_match:
                original_pattern = pattern_match.group(1)
                # Fix unescaped | operators
                fixed_pattern = re.sub(r'(?<!\\)\|', r'\\|', original_pattern)
                return full_match.replace(f'"{original_pattern}"', f'"{fixed_pattern}"')
        else:
            # Unquoted pattern - more complex, add quotes and fix
            parts = full_match.split()
            for i, part in enumerate(parts):
                if '|' in part and not part.startswith('-'):
                    # This looks like the pattern
                    fixed_pattern = re.sub(r'(?<!\\)\|', r'\\|', part)
                    parts[i] = f"'{fixed_pattern}'"
                    return ' '.join(parts)

        return full_match

    fixed_command = re.sub(grep_pattern, fix_or_operator, command)

    if fixed_command != command:
        logger.info(f"Fixed grep pattern: {command} -> {fixed_command}")

    return fixed_command

def _parse_command_safely(command: str) -> List[str]:
    """Parse command safely, handling pipes, redirections, and complex cases."""
    try:
        # Fix common grep pattern issues before parsing
        command = _fix_grep_patterns(command)

        # Check for shell operators that require shell=True
        shell_operators = ['|', '&&', '||', '>', '>>', '<', '<<', '&', ';']
        needs_shell = any(op in command for op in shell_operators)

        if not needs_shell:
            # Simple command without shell operators
            return shlex.split(command)
        else:
            # For pipes, redirections, and complex commands, we need shell=True
            return [command]  # Return as single string for shell execution
    except ValueError as e:
        logger.error(f"Command parsing failed: {e}")
        raise ValueError(f"Invalid command syntax: {e}")

@uf(name="execute_shell", version="2.1.0", description="Executes a shell command with enhanced security and optional stdin input. PREFER this tool over execute_script for transparency - it shows the exact command being executed.")
def execute_shell(inputs: ExecuteShellInput) -> dict:
    """Executes a shell command with enhanced security and optional stdin input."""
    logger.info(f"Executing command: {inputs.command[:100]}...")

    try:
        # Validate working directory exists
        work_dir = Path(inputs.working_directory)
        if not work_dir.exists():
            return {
                "stdout": "",
                "stderr": f"Working directory does not exist: {inputs.working_directory}",
                "return_code": -1,
                "success": False
            }

        # Prepare input for the command
        input_text = None
        if inputs.input_data:
            input_text = inputs.input_data
        elif inputs.input_file:
            try:
                from core.workspace_security import secure_read_text
                input_text = secure_read_text(inputs.input_file)
            except (IOError, UnicodeDecodeError) as e:
                return {
                    "stdout": "",
                    "stderr": f"Error reading input file: {e}",
                    "return_code": -1,
                    "success": False
                }

        # Parse command safely
        parsed_command = _parse_command_safely(inputs.command)
        use_shell = len(parsed_command) == 1 and parsed_command[0] == inputs.command

        # Execute the command with enhanced security
        try:
            if use_shell:
                # Complex command requiring shell
                result = subprocess.run(
                    inputs.command,
                    shell=True,
                    cwd=str(work_dir),
                    input=input_text,
                    capture_output=True,
                    text=True,
                    timeout=inputs.timeout,
                    env=dict(os.environ, PATH=os.environ.get('PATH', ''))  # Controlled env
                )
            else:
                # Simple command without shell
                result = subprocess.run(
                    parsed_command,
                    cwd=str(work_dir),
                    input=input_text,
                    capture_output=True,
                    text=True,
                    timeout=inputs.timeout
                )
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"Command not found: {inputs.command.split()[0]}",
                "return_code": 127,
                "success": False
            }

        logger.info(f"Command completed with return code: {result.returncode}")

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"Command timed out after {inputs.timeout} seconds")
        return {
            "stdout": "",
            "stderr": f"Command timed out after {inputs.timeout} seconds",
            "return_code": -1,
            "success": False
        }
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {
            "stdout": "",
            "stderr": f"Execution error: {str(e)}",
            "return_code": -1,
            "success": False
        }

# DISABLED: Redundant tool - use execute_shell instead for better transparency
# @uf(name="execute_script", version="1.0.0", description="Executes a script and returns the output. NOTE: For simple shell commands, prefer execute_shell tool for better transparency and direct command visibility.")
def execute_script(inputs: ExecuteScriptInput) -> dict:
    """Executes a script and returns the result."""
    try:
        # Create a temporary file for the script using path manager
        from core.path_manager import get_tmp_file
        import uuid
        script_filename = f"script_{uuid.uuid4().hex[:8]}"
        temp_script_path = get_tmp_file(script_filename, inputs.script_type)

        with open(temp_script_path, 'w') as f:
            # Add shebang for shell scripts if not already present
            script_content = inputs.script_content
            if inputs.script_type in ['bash', 'sh']:
                if not script_content.startswith('#!'):
                    shebang = '#!/bin/bash\n' if inputs.script_type == 'bash' else '#!/bin/sh\n'
                    script_content = shebang + script_content
            f.write(script_content)

        # Use the temporary script path
        script_path = temp_script_path

        # Make the script executable if it's a shell script
        if inputs.script_type in ['bash', 'sh']:
            os.chmod(script_path, 0o755)

        # Execute the script
        if inputs.script_type == 'python':
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=inputs.working_directory,
                capture_output=True,
                text=True,
                timeout=inputs.timeout
            )
        elif inputs.script_type in ['bash', 'sh']:
            # Use the interpreter explicitly to avoid exec format errors
            interpreter = '/bin/bash' if inputs.script_type == 'bash' else '/bin/sh'
            result = subprocess.run(
                [interpreter, script_path],
                cwd=inputs.working_directory,
                capture_output=True,
                text=True,
                timeout=inputs.timeout
            )
        else:
            result = subprocess.run(
                [script_path],
                cwd=inputs.working_directory,
                capture_output=True,
                text=True,
                timeout=inputs.timeout
            )
        
        # Clean up
        os.unlink(script_path)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Script timed out after {inputs.timeout} seconds",
            "return_code": -1,
            "success": False
        }
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        # Ensure cleanup even on exception
        try:
            if 'script_path' in locals():
                os.unlink(script_path)
        except Exception:
            pass  # Best effort cleanup

        return {
            "stdout": "",
            "stderr": f"Script execution error: {str(e)}",
            "return_code": -1,
            "success": False
        }