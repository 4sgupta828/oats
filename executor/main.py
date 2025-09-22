# uf_flow/executor/main.py

import sys
import os
import time
from typing import Dict, Any
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import UFDescriptor, ToolResult
from core.logging_config import get_logger, UFFlowLogger
from executor.sandbox import run_in_sandbox
from pydantic import create_model, ValidationError, Field

# Initialize logging
logger = get_logger('executor')

class ExecutionError(Exception):
    """Custom exception for execution errors."""
    def __init__(self, message: str, error_type: str = "general"):
        super().__init__(message)
        self.error_type = error_type


def _validate_inputs(uf_descriptor: UFDescriptor, inputs: Dict[str, Any]) -> Any:
    """Validate inputs against UF schema with improved error handling."""
    try:
        # Convert JSON schema types to Python types
        type_mapping = {
            'string': str,
            'integer': int,
            'number': float,
            'boolean': bool,
            'array': list,
            'object': dict
        }

        fields = {}
        schema_properties = uf_descriptor.input_schema.get('properties', {})
        required_fields = uf_descriptor.input_schema.get('required', [])

        # Validate that all required fields are present
        missing_fields = [field for field in required_fields if field not in inputs]
        if missing_fields:
            raise ExecutionError(f"Missing required fields: {missing_fields}", "validation")

        for field_name, field_def in schema_properties.items():
            field_type = field_def.get('type', 'string')
            python_type = type_mapping.get(field_type, str)

            is_required = field_name in required_fields

            if is_required:
                fields[field_name] = (python_type, ...)
            else:
                if field_name in inputs:
                    fields[field_name] = (python_type, Field())
                else:
                    default_value = field_def.get('default', "" if python_type == str else None)
                    fields[field_name] = (python_type, Field(default=default_value))

        InputModel = create_model('InputModel', **fields)
        return InputModel(**inputs)

    except ValidationError as e:
        logger.error(f"Input validation failed for UF '{uf_descriptor.name}': {e}")
        raise ExecutionError(f"Input validation failed: {e}", "validation")
    except Exception as e:
        logger.error(f"Unexpected error during input validation: {e}")
        raise ExecutionError(f"Input validation error: {e}", "validation")


def execute_tool(uf_descriptor: UFDescriptor, inputs: Dict[str, Any]) -> ToolResult:
    """
    Validates inputs and executes a given UF in a sandbox with comprehensive error handling.
    """
    start_time = time.time()
    tool_name = f"{uf_descriptor.name}:{uf_descriptor.version}"

    UFFlowLogger.log_execution_start(
        "executor",
        f"execute_tool:{tool_name}",
        tool_name=tool_name,
        input_keys=list(inputs.keys())
    )

    try:
        # 1. Validate inputs against the UF's input_schema
        logger.info(f"Validating inputs for tool: {tool_name}")
        validated_inputs = _validate_inputs(uf_descriptor, inputs)

        # 2. Check that callable function exists
        if not uf_descriptor.callable_func:
            error_msg = f"No callable function found for UF '{tool_name}'"
            logger.error(error_msg)
            result = ToolResult(
                status="failure",
                output=None,
                error=error_msg,
                duration_ms=int((time.time() - start_time) * 1000)
            )
            UFFlowLogger.log_tool_execution(tool_name, inputs, result.dict())
            return result

        # 3. Execute in sandbox
        logger.info(f"Executing tool '{tool_name}' in sandbox")
        func_to_run = uf_descriptor.callable_func
        result = run_in_sandbox(func_to_run, validated_inputs)

        # Add execution duration if not already present
        if not result.duration_ms:
            result.duration_ms = int((time.time() - start_time) * 1000)

        # Log the execution result
        UFFlowLogger.log_tool_execution(tool_name, inputs, result.dict())

        UFFlowLogger.log_execution_end(
            "executor",
            f"execute_tool:{tool_name}",
            result.status == "success",
            duration_ms=result.duration_ms,
            return_code=getattr(result, 'return_code', None)
        )

        return result

    except ExecutionError as e:
        duration = int((time.time() - start_time) * 1000)
        result = ToolResult(
            status="failure",
            output=None,
            error=str(e),
            duration_ms=duration
        )
        UFFlowLogger.log_tool_execution(tool_name, inputs, result.dict())
        UFFlowLogger.log_execution_end(
            "executor",
            f"execute_tool:{tool_name}",
            False,
            duration_ms=duration,
            error_type=e.error_type
        )
        return result

    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        logger.error(f"Unexpected error executing tool '{tool_name}': {e}")
        result = ToolResult(
            status="failure",
            output=None,
            error=f"Unexpected execution error: {str(e)}",
            duration_ms=duration
        )
        UFFlowLogger.log_tool_execution(tool_name, inputs, result.dict())
        UFFlowLogger.log_execution_end(
            "executor",
            f"execute_tool:{tool_name}",
            False,
            duration_ms=duration,
            error_type="unexpected"
        )
        return result