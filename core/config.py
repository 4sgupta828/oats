# core/config.py
"""
Centralized configuration for the UFFlow system.
This file contains all configurable parameters that can be easily modified.
"""

import os
from typing import Optional

class UFFlowConfig:
    """Centralized configuration class for UFFlow system."""
    
    # LLM Configuration
    DEFAULT_LLM_MODEL = "gpt-4o"
    DEFAULT_LLM_MODEL_JSON = "gpt-4o"  # For JSON responses
    DEFAULT_LLM_MODEL_TEXT = "gpt-4o"  # For text responses

    # Alternative models (uncomment to use)
    # DEFAULT_LLM_MODEL = "gpt-4o-mini"
    # DEFAULT_LLM_MODEL_JSON = "gpt-4o-mini"
    # DEFAULT_LLM_MODEL_TEXT = "gpt-4o-mini"
    
    # DEFAULT_LLM_MODEL = "gpt-4-turbo"
    # DEFAULT_LLM_MODEL_JSON = "gpt-4-turbo"
    # DEFAULT_LLM_MODEL_TEXT = "gpt-4"
    
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
            
        # Return model based on type
        if model_type == "json":
            return cls.DEFAULT_LLM_MODEL_JSON
        elif model_type == "text":
            return cls.DEFAULT_LLM_MODEL_TEXT
        else:
            return cls.DEFAULT_LLM_MODEL
    
    # Other configurable parameters
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 4000
    DEFAULT_MAX_TOKENS_TEXT = 1000
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
