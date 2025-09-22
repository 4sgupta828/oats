# uf_flow/planner/main.py

import os
import json
import sys
import subprocess
import time
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

from openai import OpenAI

from core.models import Goal, Plan, UFDescriptor
from core.logging_config import get_logger, UFFlowLogger
from core.config import config
from registry.main import Registry
from planner.prompt_components import PromptBuilder

# Initialize logging
logger = get_logger('planner')

class PlannerError(Exception):
    """Custom exception for planning errors."""
    def __init__(self, message: str, error_type: str = "general"):
        super().__init__(message)
        self.error_type = error_type


class OpenAIClientManager:
    """Manages OpenAI client with connection pooling and error handling."""

    _instance: Optional['OpenAIClientManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.client: Optional[OpenAI] = None
            self._api_key = os.environ.get("OPENAI_API_KEY")
            self._initialize_client()
            self._initialized = True

    def _initialize_client(self):
        """Initialize OpenAI client with error handling."""
        if not self._api_key:
            raise PlannerError("OPENAI_API_KEY environment variable not set", "configuration")

        try:
            self.client = OpenAI(
                api_key=self._api_key,
                timeout=config.get_timeout(),
                max_retries=config.get_max_retries()
            )
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise PlannerError(f"Failed to initialize OpenAI client: {e}", "client_init")

    def get_client(self) -> OpenAI:
        """Get the OpenAI client instance."""
        if not self.client:
            self._initialize_client()
        return self.client

    def create_completion(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """Create a completion with retry logic and error handling."""
        client = self.get_client()
        
        if model is None:
            model = config.get_llm_model("json")

        try:
            logger.info(f"Making OpenAI API call with model: {model}")
            start_time = time.time()

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=config.get_temperature(),
                max_tokens=config.get_max_tokens("json")
            )

            duration = time.time() - start_time
            logger.info(f"OpenAI API call completed in {duration:.2f}s")

            content = response.choices[0].message.content
            if not content:
                raise PlannerError("Empty response from OpenAI API", "api_response")

            return content

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise PlannerError(f"API call failed: {e}", "api_call")

    def create_completion_text(self, messages: List[Dict[str, str]], tools: Optional[List] = None, model: Optional[str] = None) -> str:
        """Create a text completion for ReAct with optional function calling."""
        client = self.get_client()

        if model is None:
            model = config.get_llm_model("text")

        try:
            logger.info(f"Making OpenAI API call with model: {model}")
            start_time = time.time()

            # Use function calling if tools provided, otherwise text
            call_params = {
                "model": model,
                "messages": messages,
                "temperature": config.get_temperature(),
                "max_tokens": config.get_max_tokens("text")
            }

            if tools:
                call_params["tools"] = tools
                call_params["tool_choice"] = "auto"

            response = client.chat.completions.create(**call_params)

            duration = time.time() - start_time
            logger.info(f"OpenAI API call completed in {duration:.2f}s")

            message = response.choices[0].message

            # Handle function calling response
            if message.tool_calls:
                # Return structured function call data
                import json
                tool_call = message.tool_calls[0]
                return json.dumps({
                    "function_name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments),
                    "thought": message.content or "Function call requested"
                })

            # Handle regular text response
            content = message.content
            if not content:
                raise PlannerError("Empty response from OpenAI API", "api_response")

            return content

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise PlannerError(f"API call failed: {e}", "api_call")


# Global client manager instance
_client_manager = OpenAIClientManager()

def _gather_system_context(goal: Goal) -> Dict[str, Any]:
    """Gather system and workspace context for planning."""
    import platform

    context = {
        "system": {
            "os": platform.system(),
            "os_version": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version()
        }
    }

    # Add workspace context
    workspace_path = goal.constraints.get('workspace_path', '.') if goal.constraints else '.'
    try:
        # Get file statistics for context (with timeout)
        result = subprocess.run(
            ['find', workspace_path, '-type', 'f', '-not', '-path', '*/.*'],  # Exclude hidden files
            capture_output=True,
            text=True,
            timeout=5  # Shorter timeout
        )

        if result.returncode == 0:
            files = [f for f in result.stdout.strip().split('\n') if f]
            file_types = {}

            for file in files[:100]:  # Limit to prevent excessive processing
                ext = os.path.splitext(file)[1] or 'no_extension'
                file_types[ext] = file_types.get(ext, 0) + 1

            context["workspace"] = {
                "working_directory": os.path.abspath(workspace_path),
                "total_files": len(files),
                "file_types": file_types,
                "example_files": files[:5]  # Just a few examples
            }
    except Exception as e:
        logger.warning(f"Could not gather workspace context: {e}")
        context["workspace"] = {
            "working_directory": os.path.abspath(workspace_path),
            "note": f"Unable to scan files: {e}"
        }

    return context


def _validate_plan_structure(plan_dict: Dict[str, Any]) -> None:
    """Validate the basic structure of a generated plan."""
    required_fields = ['id', 'status', 'graph', 'nodes', 'confidence_score']

    for field in required_fields:
        if field not in plan_dict:
            raise PlannerError(f"Missing required field in plan: {field}", "validation")

    # Validate graph structure
    graph = plan_dict.get('graph', {})
    nodes = plan_dict.get('nodes', {})

    # Check that all nodes referenced in graph exist
    for node_id, dependencies in graph.items():
        if node_id not in nodes:
            raise PlannerError(f"Graph references non-existent node: {node_id}", "validation")

        for dep in dependencies:
            if dep not in nodes:
                raise PlannerError(f"Graph references non-existent dependency: {dep}", "validation")

    # Validate confidence score
    confidence = plan_dict.get('confidence_score', 0)
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise PlannerError("Invalid confidence_score: must be between 0 and 1", "validation")


def create_plan_for_goal(goal: Goal, registry: Registry) -> Plan:
    """
    Uses an LLM to generate a Plan to achieve a given Goal with improved error handling and logging.
    """
    start_time = time.time()

    UFFlowLogger.log_execution_start(
        "planner",
        "create_plan",
        goal_id=goal.id,
        goal_description=goal.description[:100] + "..." if len(goal.description) > 100 else goal.description
    )

    try:
        logger.info(f"Generating plan for goal: '{goal.description}' (ID: {goal.id})")

        # Gather available tools
        available_tools = registry.list_ufs()
        if not available_tools:
            raise PlannerError("No tools available in registry", "configuration")

        logger.info(f"Found {len(available_tools)} available tools")

        # Gather system context
        system_context = _gather_system_context(goal)

        # Build prompt using modular components
        prompt_builder = PromptBuilder()
        prompt = prompt_builder.build_prompt(goal, available_tools, system_context)

        logger.debug(f"Generated prompt length: {len(prompt)} characters")

        # Generate plan using OpenAI
        messages = [{"role": "system", "content": prompt}]
        response_content = _client_manager.create_completion(messages)

        logger.info("Received response from LLM, parsing plan")

        # Parse and validate response
        try:
            plan_dict = json.loads(response_content)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from LLM: {e}")
            logger.debug(f"Raw response: {response_content[:500]}...")
            raise PlannerError(f"Invalid JSON response: {e}", "parsing")

        # Validate plan structure
        _validate_plan_structure(plan_dict)

        # Hydrate the plan with goal information
        plan_dict['goal_id'] = goal.id
        plan_dict['status'] = 'running'

        # Create Plan object
        plan = Plan(**plan_dict)

        duration = time.time() - start_time

        UFFlowLogger.log_plan_generation(
            goal.id,
            plan.id,
            len(plan.nodes),
            plan.confidence_score
        )

        UFFlowLogger.log_execution_end(
            "planner",
            "create_plan",
            True,
            duration_ms=int(duration * 1000),
            plan_id=plan.id,
            node_count=len(plan.nodes)
        )

        logger.info(f"Plan generated successfully: {plan.id} ({len(plan.nodes)} nodes, confidence: {plan.confidence_score:.2f})")
        return plan

    except PlannerError as e:
        duration = time.time() - start_time
        logger.error(f"Planning failed ({e.error_type}): {e}")

        UFFlowLogger.log_execution_end(
            "planner",
            "create_plan",
            False,
            duration_ms=int(duration * 1000),
            error_type=e.error_type,
            error_message=str(e)
        )
        raise

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Unexpected error during planning: {e}")

        UFFlowLogger.log_execution_end(
            "planner",
            "create_plan",
            False,
            duration_ms=int(duration * 1000),
            error_type="unexpected",
            error_message=str(e)
        )
        raise PlannerError(f"Unexpected planning error: {e}", "unexpected")