#!/usr/bin/env python3
"""
Generated UFs package - Auto-discovers and loads generated UFs.
"""

import os
import sys
import glob

# Add UFFLOW to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def load_all_generated_ufs():
    """Load all generated UFs from the genufs directory."""
    try:
        from registry.main import global_registry
        from tools.shell_uf import create_shell_uf
        
        genufs_dir = os.path.dirname(__file__)
        
        # Find all shell script files in gen subdirectory
        gen_dir = os.path.join(genufs_dir, "gen")
        script_files = glob.glob(os.path.join(gen_dir, "gen_*.sh"))
        
        loaded_ufs = []
        for script_file in script_files:
            try:
                # Read metadata from script comments
                with open(script_file, 'r') as f:
                    lines = f.readlines()
                
                # Use filename-based UF ID instead of parsing from script
                uf_id = os.path.basename(script_file).replace('.sh', '')
                description = "Generated shell script"
                input_schema = None
                output_schema = None
                
                for line in lines:
                    if line.startswith('# Description: '):
                        description = line[15:].strip()
                    elif line.startswith('# Input Schema: '):
                        try:
                            input_schema = json.loads(line[16:].strip())
                        except:
                            pass
                    elif line.startswith('# Output Schema: '):
                        try:
                            output_schema = json.loads(line[17:].strip())
                        except:
                            pass
                
                if uf_id:
                    # Create UF function from shell script
                    uf_func = create_shell_uf(script_file, uf_id, description)
                    
                    # Create UF descriptor manually
                    from core.models import UFDescriptor
                    from core.sdk import UfInput
                    from pydantic import create_model
                    
                    # Use parsed schemas or fall back to defaults
                    if not input_schema or not isinstance(input_schema, dict):
                        from pydantic import BaseModel, Field
                        class ShellUFInput(BaseModel):
                            input_data: str = Field(default="", description="Input data to pass to the script via stdin")
                            working_directory: str = Field(default=".", description="Working directory for script execution")
                            timeout: int = Field(default=60, description="Timeout in seconds")
                        input_schema = ShellUFInput.model_json_schema()
                    elif "properties" not in input_schema:
                        # LLM provided a simple schema (e.g., {"type": "string"})
                        # Convert it to a proper input schema with our standard fields
                        from pydantic import BaseModel, Field
                        class ShellUFInput(BaseModel):
                            input_data: str = Field(default="", description="Input data to pass to the script via stdin")
                            working_directory: str = Field(default=".", description="Working directory for script execution")
                            timeout: int = Field(default=60, description="Timeout in seconds")
                        input_schema = ShellUFInput.model_json_schema()
                    
                    if not output_schema or not isinstance(output_schema, dict) or "properties" not in output_schema:
                        output_schema = {
                            "type": "object",
                            "properties": {
                                "output": {"type": "string"},
                                "error": {"type": "string"},
                                "return_code": {"type": "integer"},
                                "success": {"type": "boolean"},
                                "script_path": {"type": "string"}
                            }
                        }
                    else:
                        # LLM provided a proper output schema, but we need to add our standard fields
                        if "output" not in output_schema["properties"]:
                            output_schema["properties"]["output"] = {"type": "string", "description": "Script output"}
                        if "error" not in output_schema["properties"]:
                            output_schema["properties"]["error"] = {"type": "string", "description": "Error output if any"}
                        if "return_code" not in output_schema["properties"]:
                            output_schema["properties"]["return_code"] = {"type": "integer", "description": "Script return code"}
                        if "success" not in output_schema["properties"]:
                            output_schema["properties"]["success"] = {"type": "boolean", "description": "Whether script executed successfully"}
                        if "script_path" not in output_schema["properties"]:
                            output_schema["properties"]["script_path"] = {"type": "string", "description": "Path to the executed script"}
                    
                    # Create resolver template
                    from core.models import InputResolver, InputResolverMapping, Invocation
                    
                    resolver_template = InputResolver(
                        data_mapping={
                            "input_data": InputResolverMapping(source="context", value_selector="{inputs.input_data}", node_id=None),
                            "working_directory": InputResolverMapping(source="context", value_selector="{inputs.working_directory}", node_id=None),
                            "timeout": InputResolverMapping(source="context", value_selector="{inputs.timeout}", node_id=None)
                        },
                        invocation=Invocation(type="python", template=f"tools.genufs.{uf_id}", params={})
                    )
                    
                    descriptor = UFDescriptor(
                        name=uf_id,
                        version="1.0.0",
                        description=description,
                        input_schema=input_schema,
                        output_schema=output_schema,
                        resolver_template=resolver_template,
                        callable_func=uf_func
                    )
                    
                    # Register the UF
                    global_registry.register_uf(descriptor)
                    loaded_ufs.append(uf_id)
                    
            except Exception as e:
                print(f"Error loading UF from {script_file}: {e}")
        
        return loaded_ufs
    except ImportError as e:
        # Registry not available yet, return empty list
        print(f"Could not load generated UFs: {e}")
        return []

# Generated UFs are loaded on demand by the registry
