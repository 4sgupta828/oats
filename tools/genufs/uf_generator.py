#!/usr/bin/env python3
"""
UF Generator - Automatically creates reusable UFs from generated scripts.
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.sdk import uf, UfInput
from core.path_manager import get_tmp_file

class UFGenerator:
    """Generates reusable UFs from script content."""
    
    def __init__(self, genufs_dir: str = None):
        self.genufs_dir = genufs_dir or os.path.join(os.path.dirname(__file__))
        self.gen_dir = os.path.join(self.genufs_dir, 'gen')
        self.tests_dir = os.path.join(self.genufs_dir, 'tests')
        self.ensure_genufs_dir()
    
    def ensure_genufs_dir(self):
        """Ensure the genufs directory, gen subdirectory, and tests subdirectory exist."""
        os.makedirs(self.genufs_dir, exist_ok=True)
        os.makedirs(self.gen_dir, exist_ok=True)
        os.makedirs(self.tests_dir, exist_ok=True)
    
    def generate_uf_id(self, script_content: str, task_description: str) -> str:
        """Generate a unique UF ID based on script content and task."""
        # Create a hash of the script content for uniqueness
        content_hash = hashlib.md5(script_content.encode()).hexdigest()[:8]
        
        # Create a sanitized name from task description
        sanitized_name = "".join(c.lower() if c.isalnum() else "_" for c in task_description[:30])
        sanitized_name = sanitized_name.strip("_")
        
        return f"gen_{sanitized_name}_{content_hash}"
    
    def create_uf_from_script(self, 
                            script_content: str, 
                            task_description: str,
                            test_content: str = "",
                            validation: str = "",
                            constraints: Dict[str, Any] = None) -> str:
        """
        Create a simple shell script UF from generated script content.
        
        Args:
            script_content: The generated script content
            task_description: Description of what the script does
            test_content: Test script content (optional)
            validation: Validation description (optional)
            constraints: Any constraints or parameters (optional)
        
        Returns:
            The UF ID of the created UF
        """
        # Generate unique UF ID
        uf_id = self.generate_uf_id(script_content, task_description)

        # Create script file path using tmp directory
        script_file = get_tmp_file(f"{uf_id}", "sh")
        test_file = get_tmp_file(f"{uf_id}_test", "sh") if test_content else None
        
        # Check if the script already has complete headers (from LLM)
        has_shebang = script_content.startswith('#!/bin/bash')
        has_uf_id = "# UF:" in script_content
        has_input_schema = "# Input Schema:" in script_content
        has_output_schema = "# Output Schema:" in script_content
        
        if has_shebang and has_uf_id and (has_input_schema or has_output_schema):
            # LLM provided a complete script with headers, use as-is
            script_with_metadata = script_content
        else:
            # Generate input/output schemas based on the task
            input_schema = self._generate_input_schema(task_description, constraints)
            output_schema = self._generate_output_schema(task_description, "text")
            
            # Write the script file with UF metadata in comments
            script_with_metadata = f"""#!/bin/bash
# UF: {uf_id}
# Description: {task_description}
# Created: {datetime.now().isoformat()}
# Input Schema: {json.dumps(input_schema)}
# Output Schema: {json.dumps(output_schema)}
# Validation: {validation}
# Constraints: {json.dumps(constraints or {})}

{script_content}
"""
        
        with open(script_file, 'w') as f:
            f.write(script_with_metadata)
        os.chmod(script_file, 0o755)  # Make executable
        
        # Write the test file
        if test_content and test_file:
            test_with_metadata = f"""#!/bin/bash
# Test for UF: {uf_id}
# Description: {task_description}
# Created: {datetime.now().isoformat()}

{test_content}
"""
            with open(test_file, 'w') as f:
                f.write(test_with_metadata)
            os.chmod(test_file, 0o755)  # Make executable
        
        return uf_id
    
    def _generate_input_schema(self, task_description: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
        """Generate input schema based on task description and constraints."""
        # Base schema for all shell UFs
        base_schema = {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "string",
                    "description": "Input data to pass to the script via stdin",
                    "default": ""
                },
                "working_directory": {
                    "type": "string", 
                    "description": "Working directory for script execution",
                    "default": "."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 60
                }
            },
            "required": ["input_data"]
        }
        
        # Add task-specific input fields based on constraints
        if constraints:
            for key, value in constraints.items():
                if key not in base_schema["properties"]:
                    field_type = "string" if isinstance(value, str) else "integer" if isinstance(value, int) else "boolean"
                    base_schema["properties"][key] = {
                        "type": field_type,
                        "description": f"Parameter: {key}",
                        "default": value
                    }
        
        return base_schema
    
    def _generate_output_schema(self, task_description: str, output_format: str) -> Dict[str, Any]:
        """Generate output schema based on task description and output format."""
        # Base schema for all shell UFs
        base_schema = {
            "type": "object",
            "properties": {
                "output": {
                    "type": "string",
                    "description": "Script output"
                },
                "error": {
                    "type": "string", 
                    "description": "Error output if any"
                },
                "return_code": {
                    "type": "integer",
                    "description": "Script return code"
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether script executed successfully"
                },
                "script_path": {
                    "type": "string",
                    "description": "Path to the executed script"
                }
            }
        }
        
        # Add task-specific output fields based on description
        if "csv" in task_description.lower() or "data" in task_description.lower():
            base_schema["properties"]["statistics"] = {
                "type": "object",
                "description": "Computed statistics"
            }
        elif "count" in task_description.lower() or "frequency" in task_description.lower():
            base_schema["properties"]["counts"] = {
                "type": "object", 
                "description": "Count/frequency data"
            }
        
        return base_schema
    
    def list_generated_ufs(self) -> list:
        """List all generated UFs."""
        ufs = []
        for filename in os.listdir(self.gen_dir):
            # Only process main scripts, not test files
            if filename.startswith('gen_') and filename.endswith('.sh') and not filename.endswith('_test.sh'):
                script_file = os.path.join(self.gen_dir, filename)
                try:
                    # Read metadata from script comments
                    with open(script_file, 'r') as f:
                        lines = f.readlines()
                    
                    metadata = {}
                    for line in lines:
                        if line.startswith('# UF: '):
                            # Use the filename-based UF ID instead of the one in the script
                            metadata['uf_id'] = os.path.basename(script_file).replace('.sh', '')
                        elif line.startswith('# Description: '):
                            metadata['task_description'] = line[15:].strip()
                        elif line.startswith('# Created: '):
                            metadata['created_at'] = line[11:].strip()
                        elif line.startswith('# Input Schema: '):
                            try:
                                metadata['input_schema'] = json.loads(line[16:].strip())
                            except:
                                metadata['input_schema'] = line[16:].strip()
                        elif line.startswith('# Output Schema: '):
                            try:
                                metadata['output_schema'] = json.loads(line[17:].strip())
                            except:
                                metadata['output_schema'] = line[17:].strip()
                        elif line.startswith('# Validation: '):
                            metadata['validation'] = line[14:].strip()
                        elif line.startswith('# Constraints: '):
                            try:
                                metadata['constraints'] = json.loads(line[15:].strip())
                            except:
                                metadata['constraints'] = line[15:].strip()
                    
                    # Only add if we found a UF ID (has metadata)
                    if 'uf_id' in metadata:
                        metadata['script_file'] = script_file
                        metadata['test_file'] = os.path.join(self.tests_dir, f"{metadata['uf_id']}_test.sh")
                        ufs.append(metadata)
                except Exception as e:
                    print(f"Error loading UF from {filename}: {e}")
        return ufs
    
    def load_uf(self, uf_id: str) -> Optional[Dict[str, Any]]:
        """Load a specific generated UF."""
        script_file = os.path.join(self.gen_dir, f"{uf_id}.sh")
        if os.path.exists(script_file):
            try:
                # Read metadata from script comments
                with open(script_file, 'r') as f:
                    lines = f.readlines()
                
                metadata = {}
                for line in lines:
                    if line.startswith('# UF: '):
                        # Use the filename-based UF ID instead of the one in the script
                        metadata['uf_id'] = os.path.basename(script_file).replace('.sh', '')
                    elif line.startswith('# Description: '):
                        metadata['task_description'] = line[15:].strip()
                    elif line.startswith('# Created: '):
                        metadata['created_at'] = line[11:].strip()
                    elif line.startswith('# Input Schema: '):
                        try:
                            metadata['input_schema'] = json.loads(line[16:].strip())
                        except:
                            metadata['input_schema'] = line[16:].strip()
                    elif line.startswith('# Output Schema: '):
                        try:
                            metadata['output_schema'] = json.loads(line[17:].strip())
                        except:
                            metadata['output_schema'] = line[17:].strip()
                    elif line.startswith('# Validation: '):
                        metadata['validation'] = line[14:].strip()
                    elif line.startswith('# Constraints: '):
                        try:
                            metadata['constraints'] = json.loads(line[15:].strip())
                        except:
                            metadata['constraints'] = line[15:].strip()
                
                metadata['script_file'] = script_file
                metadata['test_file'] = os.path.join(self.tests_dir, f"{metadata['uf_id']}_test.sh")
                return metadata
            except Exception as e:
                print(f"Error loading UF {uf_id}: {e}")
        return None
    
    def delete_uf(self, uf_id: str) -> bool:
        """Delete a generated UF and its files."""
        try:
            script_file = os.path.join(self.gen_dir, f"{uf_id}.sh")
            test_file = os.path.join(self.tests_dir, f"{uf_id}_test.sh")
            
            # Delete script and test files
            for file_path in [script_file, test_file]:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            
            return True
        except Exception as e:
            print(f"Error deleting UF {uf_id}: {e}")
            return False

# Global instance
uf_generator = UFGenerator()
