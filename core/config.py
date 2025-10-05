# core/config.py
"""
Centralized configuration for the UFFlow system.
This file contains all configurable parameters that can be easily modified.
"""

import os

class UFFlowConfig:
    """Centralized configuration class for UFFlow system."""

    # LLM Provider Selection - Set to "claude" or "openai"
    LLM_PROVIDER = "claude"

    # Model configurations by provider
    CLAUDE_MODELS = {
        "default": "claude-3-5-sonnet-20241022",
        "json": "claude-3-5-sonnet-20241022",
        "text": "claude-3-5-sonnet-20241022"
    }

    OPENAI_MODELS = {
        "default": "gpt-4o",
        "json": "gpt-4o",
        "text": "gpt-4o"
    }

    # Legacy properties for backward compatibility
    @property
    def DEFAULT_LLM_MODEL(self):
        return self.CLAUDE_MODELS["default"] if self.LLM_PROVIDER == "claude" else self.OPENAI_MODELS["default"]

    @property
    def DEFAULT_LLM_MODEL_JSON(self):
        return self.CLAUDE_MODELS["json"] if self.LLM_PROVIDER == "claude" else self.OPENAI_MODELS["json"]

    @property
    def DEFAULT_LLM_MODEL_TEXT(self):
        return self.CLAUDE_MODELS["text"] if self.LLM_PROVIDER == "claude" else self.OPENAI_MODELS["text"]
    
    # Environment variable override
    @classmethod
    def get_llm_model(cls, model_type: str = "default") -> str:
        """
        Get the LLM model name with environment variable override support.

        Args:
            model_type: Type of model ("default", "json", "text")

        Returns:
            Model name string
        """
        # Check for environment variable override
        env_model = os.environ.get("UFFLOW_LLM_MODEL")
        if env_model:
            return env_model

        # Check for provider override
        provider = os.environ.get("UFFLOW_LLM_PROVIDER", cls.LLM_PROVIDER)

        # Select model based on provider and type
        models = cls.CLAUDE_MODELS if provider == "claude" else cls.OPENAI_MODELS
        return models.get(model_type, models["default"])
    
    # Other configurable parameters
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 4000
    DEFAULT_MAX_TOKENS_TEXT = 8000  # Increased for ReAct agent (was 1000)
    DEFAULT_TIMEOUT = 60.0
    DEFAULT_MAX_RETRIES = 2
    
    # ReAct Configuration
    DEFAULT_MAX_TURNS = 10
    
    # Logging Configuration
    LOG_LEVEL = "INFO"
    
    @classmethod
    def get_temperature(cls) -> float:
        """Get temperature setting with environment variable override."""
        return float(os.environ.get("UFFLOW_TEMPERATURE", cls.DEFAULT_TEMPERATURE))
    
    @classmethod
    def get_max_tokens(cls, model_type: str = "default") -> int:
        """Get max tokens setting with environment variable override."""
        if model_type == "text":
            return int(os.environ.get("UFFLOW_MAX_TOKENS_TEXT", cls.DEFAULT_MAX_TOKENS_TEXT))
        return int(os.environ.get("UFFLOW_MAX_TOKENS", cls.DEFAULT_MAX_TOKENS))
    
    @classmethod
    def get_timeout(cls) -> float:
        """Get timeout setting with environment variable override."""
        return float(os.environ.get("UFFLOW_TIMEOUT", cls.DEFAULT_TIMEOUT))
    
    @classmethod
    def get_max_retries(cls) -> int:
        """Get max retries setting with environment variable override."""
        return int(os.environ.get("UFFLOW_MAX_RETRIES", cls.DEFAULT_MAX_RETRIES))
    
    @classmethod
    def get_max_turns(cls) -> int:
        """Get max turns for ReAct with environment variable override."""
        return int(os.environ.get("UFFLOW_MAX_TURNS", cls.DEFAULT_MAX_TURNS))


# Global config instance
config = UFFlowConfig()
