import os
import sys
import tempfile
import subprocess
import json
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

from pydantic import Field
from core.sdk import uf, UfInput
from core.config import config
from openai import OpenAI
# UF generator will be imported on demand
uf_generator = None

class GenerateTaskScriptInput(UfInput):
    task_description: str = Field(..., description="Description of the task to accomplish.")
    input_data: str = Field(default="", description="Input data or context for the task.")
    constraints: str = Field(default="", description="Constraints or requirements.")
    output_format: str = Field(default="text", description="Expected output format.")

# DISABLED: Redundant tool - LLM can create scripts directly and run with execute_shell
# @uf(name="generate_task_script", version="1.0.0", description="Generates a script using LLM to solve a specific task.")
def generate_task_script(inputs: GenerateTaskScriptInput) -> dict:
    """Generates a script using LLM to solve a specific task."""
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        if not client.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        
        # Create a prompt for script generation
        prompt = f"""You are an expert at writing GENERIC, REUSABLE shell scripts to solve data processing tasks.

TASK: {inputs.task_description}
CONSTRAINTS: {inputs.constraints}
OUTPUT FORMAT: {inputs.output_format}

CRITICAL: Generate a GENERIC script that works with ANY input data of the expected format. Do NOT hardcode specific values or data.

INSTRUCTIONS:
1. Generate a GENERIC bash script that accomplishes the task for ANY input
2. Create a test script that validates the functionality with sample data
3. Include proper input/output schemas in the script headers
4. Return both the working script and the test

    SCRIPT REQUIREMENTS:
    - Use standard Unix tools (wc, grep, sed, awk, sort, uniq, tr, cut, head, tail, cat, echo, printf, etc.)
    - MUST accept input via stdin (primary method) - use `cat` to read from stdin
    - Can optionally accept command line arguments as fallback
    - Include proper error handling
    - Add comments explaining functionality
    - Handle empty inputs, malformed data, and edge cases
    - Use shell arithmetic for calculations (avoid bc when possible)
    - Trim whitespace properly to avoid parsing errors
    - Make the script GENERIC - it should work with different datasets of the same format
    - IMPORTANT: Use system-compatible commands based on the target OS (e.g., on macOS use `grep -E` instead of `grep -P`)

    SCRIPT HEADER REQUIREMENTS:
    Include these metadata comments at the top of the script:
    # UF: [unique_id]
    # Description: [what the script does]
    # Created: [timestamp]
    # Input Schema: [JSON schema describing expected input - MUST include input_data field]
    # Output Schema: [JSON schema describing expected output]
    # Validation: [how to validate the script works]
    # Constraints: [any constraints or requirements]
    
    INPUT SCHEMA REQUIREMENTS:
    The Input Schema MUST be a JSON object with a "properties" field containing:
    - "input_data": {{"type": "string", "description": "Input data to pass to the script via stdin"}}
    - "working_directory": {{"type": "string", "description": "Working directory for script execution", "default": "."}}
    - "timeout": {{"type": "integer", "description": "Timeout in seconds", "default": 60}}
    
    Example Input Schema:
    {{"type": "object", "properties": {{"input_data": {{"type": "string", "description": "Input data to pass to the script via stdin"}}, "working_directory": {{"type": "string", "description": "Working directory for script execution", "default": "."}}, "timeout": {{"type": "integer", "description": "Timeout in seconds", "default": 60}}}}}}

STDIN HANDLING:
- The script will receive input via stdin, so use: `input=$(cat)` or `cat | your_processing`
- Do NOT prompt for user input with `read` or `echo "Please provide input"`
- Process the stdin data directly
- Do NOT hardcode specific values or data

TEST SCRIPT REQUIREMENTS:
- Create a test script with sample data that represents the expected input format
- Validate that the output is correct and complete
- Check that all expected values are present (no missing fields)
- Validate that the output format is exactly as requested
- Test edge cases (empty input, malformed data, etc.)
- Use assertions or validation checks

OUTPUT FORMAT:
Return a JSON object with the following structure:

{{
  "script": "#!/bin/bash\\n# Your working bash script here",
  "test": "#!/bin/bash\\n# Your test script here", 
  "validation": "Brief description of what the test validates"
}}

EXAMPLE:
{{
  "script": "#!/bin/bash\\ninput=$(cat)\\necho $(echo \\"$input\\" | wc -w)",
  "test": "#!/bin/bash\\necho \\"hello world\\" | ./script.sh | grep -q \\"2\\" && echo \\"PASS\\" || echo \\"FAIL\\"",
  "validation": "Tests word counting with sample input 'hello world' expecting output '2'"
}}

CRITICAL: 
- Return ONLY valid JSON, no markdown or explanations
- The script must produce complete, valid output
- The test must validate the script works correctly
- All values must be properly escaped JSON strings"""
        
        response = client.chat.completions.create(
            model=config.get_llm_model("text"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=config.get_max_tokens("text"),
            temperature=config.get_temperature()
        )
        
        response_content = response.choices[0].message.content.strip()
        
        # Parse JSON response
        import json
        json_response = json.loads(response_content)
        script_content = json_response.get("script", "")
        test_content = json_response.get("test", "")
        validation = json_response.get("validation", "")
        
        # Parse constraints if provided
        constraints = {}
        if inputs.constraints:
            try:
                constraints = json.loads(inputs.constraints)
            except json.JSONDecodeError:
                constraints = {"constraints": inputs.constraints}
        
        # Save as reusable UF
        uf_id = None
        try:
            from tools.genufs.uf_generator import uf_generator
            uf_id = uf_generator.create_uf_from_script(
                script_content=script_content,
                task_description=inputs.task_description,
                test_content=test_content,
                validation=validation,
                constraints=constraints
            )
            print(f"✅ Generated script saved as reusable UF: {uf_id}")
        except ImportError:
            print("⚠️  UF generator not available - script not saved as reusable UF")
        except Exception as e:
            print(f"⚠️  Warning: Could not save as UF: {e}")
            uf_id = None
        
        return {
            "script_content": script_content,
            "test_content": test_content,
            "validation": validation,
            "task_description": inputs.task_description,
            "success": True,
            "uf_id": uf_id,  # Include the UF ID for reference
            "full_response": response_content  # For debugging
        }
        
    except Exception as e:
        return {
            "script_content": f"#!/bin/bash\necho 'Error generating script: {str(e)}'",
            "task_description": inputs.task_description,
            "success": False,
            "error": str(e)
        }

class ExecuteTaskScriptInput(UfInput):
    script_content: str = Field(..., description="The script content to execute.")
    input_data: str = Field(default="", description="Input data to pass to the script.")
    working_directory: str = Field(default=".", description="Working directory for script execution.")
    timeout: int = Field(default=60, description="Timeout in seconds.")

# DISABLED: Redundant tool - use execute_shell instead for better transparency
# @uf(name="execute_task_script", version="1.0.0", description="Executes a generated task script. NOTE: For simple single commands, prefer execute_shell for better transparency and direct command visibility.")
def execute_task_script(inputs: ExecuteTaskScriptInput) -> dict:
    """Executes a generated task script."""
    try:
        script_content = inputs.script_content
        
        # Create a temporary file for the script using path manager
        from core.path_manager import get_tmp_file
        import uuid
        script_filename = f"task_script_{uuid.uuid4().hex[:8]}"
        script_path = get_tmp_file(script_filename, "sh")

        with open(script_path, 'w') as f:
            f.write(script_content)
        
        # Make the script executable
        os.chmod(script_path, 0o755)
        
        # Execute the script
        if inputs.input_data:
            # Pass input data via stdin
            result = subprocess.run(
                [script_path],
                input=inputs.input_data,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            # No input data
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=60
            )
        
        # Clean up
        os.unlink(script_path)
        
        return {
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
            "return_code": result.returncode,
            "success": result.returncode == 0,
            "script_content": script_content
        }
        
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "error": "Script execution timed out",
            "success": False
        }
    except Exception as e:
        return {
            "output": "",
            "error": str(e),
            "success": False
        }
