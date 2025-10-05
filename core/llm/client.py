# core/llm/client.py

import os
import time
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from openai import OpenAI
from anthropic import Anthropic

from core.logging_config import get_logger
from core.config import config

# Initialize logging
logger = get_logger('llm.client')

class LLMError(Exception):
    """Custom exception for LLM client errors."""
    def __init__(self, message: str, error_type: str = "general"):
        super().__init__(message)
        self.error_type = error_type

class OpenAIClientManager:
    """Manages OpenAI and Anthropic clients with connection pooling and error handling."""

    _instance: Optional['OpenAIClientManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.openai_client: Optional[OpenAI] = None
            self.anthropic_client: Optional[Anthropic] = None
            self._openai_api_key = os.environ.get("OPENAI_API_KEY")
            self._anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
            self._initialized = True

    def _initialize_openai_client(self):
        """Initialize OpenAI client with error handling."""
        if not self._openai_api_key:
            raise LLMError("OPENAI_API_KEY environment variable not set", "configuration")

        try:
            self.openai_client = OpenAI(
                api_key=self._openai_api_key,
                timeout=config.get_timeout(),
                max_retries=config.get_max_retries()
            )
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise LLMError(f"Failed to initialize OpenAI client: {e}", "client_init")

    def _initialize_anthropic_client(self):
        """Initialize Anthropic client with error handling."""
        if not self._anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY environment variable not set", "configuration")

        try:
            self.anthropic_client = Anthropic(
                api_key=self._anthropic_api_key,
                timeout=config.get_timeout(),
                max_retries=config.get_max_retries()
            )
            logger.info("Anthropic client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            raise LLMError(f"Failed to initialize Anthropic client: {e}", "client_init")

    def get_client(self, provider: str = None):
        """Get the appropriate client instance based on provider."""
        if provider is None:
            provider = os.environ.get("UFFLOW_LLM_PROVIDER", config.LLM_PROVIDER)

        if provider == "claude":
            if not self.anthropic_client:
                self._initialize_anthropic_client()
            return self.anthropic_client
        else:
            if not self.openai_client:
                self._initialize_openai_client()
            return self.openai_client

    def create_completion(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """Create a completion with retry logic and error handling."""
        if model is None:
            model = config.get_llm_model("json")

        provider = "claude" if model.startswith("claude") else "openai"
        client = self.get_client(provider)

        try:
            logger.info(f"Making {provider.upper()} API call with model: {model}")
            start_time = time.time()

            if provider == "claude":
                # Extract system message if present
                system_msg = None
                claude_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_msg = msg["content"]
                    else:
                        claude_messages.append(msg)

                # If no user messages, add a default one
                if not claude_messages:
                    claude_messages = [{"role": "user", "content": "Please proceed."}]

                # Anthropic API call
                call_params = {
                    "model": model,
                    "max_tokens": config.get_max_tokens("json"),
                    "temperature": config.get_temperature(),
                    "messages": claude_messages
                }

                if system_msg:
                    call_params["system"] = system_msg

                response = client.messages.create(**call_params)
                content = response.content[0].text
            else:
                # OpenAI API call
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=config.get_temperature(),
                    max_tokens=config.get_max_tokens("json")
                )
                content = response.choices[0].message.content

            duration = time.time() - start_time
            logger.info(f"{provider.upper()} API call completed in {duration:.2f}s")

            if not content:
                raise LLMError(f"Empty response from {provider.upper()} API", "api_response")

            return content

        except Exception as e:
            logger.error(f"{provider.upper()} API call failed: {e}")
            raise LLMError(f"API call failed: {e}", "api_call")

    def create_completion_text(self, messages: List[Dict[str, str]], tools: Optional[List] = None, model: Optional[str] = None) -> str:
        """Create a text completion for ReAct with optional function calling."""
        if model is None:
            model = config.get_llm_model("text")

        provider = "claude" if model.startswith("claude") else "openai"
        client = self.get_client(provider)

        try:
            logger.info(f"Making {provider.upper()} API call with model: {model}")
            start_time = time.time()

            if provider == "claude":
                # Extract system message if present
                system_msg = None
                claude_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_msg = msg["content"]
                    else:
                        claude_messages.append(msg)

                # If no user messages, add a default one
                if not claude_messages:
                    claude_messages = [{"role": "user", "content": "Please proceed."}]

                # Anthropic API call
                call_params = {
                    "model": model,
                    "max_tokens": config.get_max_tokens("text"),
                    "temperature": config.get_temperature(),
                    "messages": claude_messages
                }

                if system_msg:
                    call_params["system"] = system_msg

                if tools:
                    call_params["tools"] = tools

                response = client.messages.create(**call_params)

                # Handle tool use response
                if response.stop_reason == "tool_use":
                    import json
                    tool_use_block = next((block for block in response.content if block.type == "tool_use"), None)
                    if tool_use_block:
                        text_content = next((block.text for block in response.content if hasattr(block, "text")), "")
                        return json.dumps({
                            "function_name": tool_use_block.name,
                            "arguments": tool_use_block.input,
                            "thought": text_content or "Function call requested"
                        })

                # Handle regular text response
                content = next((block.text for block in response.content if hasattr(block, "text")), None)
            else:
                # OpenAI API call
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
                message = response.choices[0].message

                # Handle function calling response
                if message.tool_calls:
                    import json
                    tool_call = message.tool_calls[0]
                    return json.dumps({
                        "function_name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments),
                        "thought": message.content or "Function call requested"
                    })

                content = message.content

            duration = time.time() - start_time
            logger.info(f"{provider.upper()} API call completed in {duration:.2f}s")

            if not content:
                raise LLMError(f"Empty response from {provider.upper()} API", "api_response")

            return content

        except Exception as e:
            logger.error(f"{provider.upper()} API call failed: {e}")
            raise LLMError(f"API call failed: {e}", "api_call")