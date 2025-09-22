# core/llm/client.py

import os
import time
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from openai import OpenAI

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
            raise LLMError("OPENAI_API_KEY environment variable not set", "configuration")

        try:
            self.client = OpenAI(
                api_key=self._api_key,
                timeout=config.get_timeout(),
                max_retries=config.get_max_retries()
            )
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise LLMError(f"Failed to initialize OpenAI client: {e}", "client_init")

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
                raise LLMError("Empty response from OpenAI API", "api_response")

            return content

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise LLMError(f"API call failed: {e}", "api_call")

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
                raise LLMError("Empty response from OpenAI API", "api_response")

            return content

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise LLMError(f"API call failed: {e}", "api_call")