# UFFlow Configuration Guide

## Centralized Model Configuration

UFFlow now uses a centralized configuration system that allows you to easily change LLM models and other parameters in one place.

## Configuration File

The main configuration is located in `core/config.py`. This file contains all configurable parameters for the UFFlow system.

### Changing the LLM Model

To change the LLM model, edit the following lines in `core/config.py`:

```python
# Current configuration (GPT-4o-mini - cost-effective)
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_LLM_MODEL_JSON = "gpt-4o-mini"  # For JSON responses
DEFAULT_LLM_MODEL_TEXT = "gpt-4o-mini"  # For text responses

# Alternative configurations (uncomment to use):

# For GPT-4o (more capable but expensive)
# DEFAULT_LLM_MODEL = "gpt-4o"
# DEFAULT_LLM_MODEL_JSON = "gpt-4o"
# DEFAULT_LLM_MODEL_TEXT = "gpt-4o"

# For GPT-4-turbo (legacy)
# DEFAULT_LLM_MODEL = "gpt-4-turbo"
# DEFAULT_LLM_MODEL_JSON = "gpt-4-turbo"
# DEFAULT_LLM_MODEL_TEXT = "gpt-4"
```

### Environment Variable Override

You can also override the model using environment variables:

```bash
# Set the model via environment variable
export UFFLOW_LLM_MODEL="gpt-4o"

# Or set other parameters
export UFFLOW_TEMPERATURE="0.2"
export UFFLOW_MAX_TOKENS="2000"
export UFFLOW_MAX_TURNS="50"
```

### Other Configurable Parameters

The configuration file also includes:

- **Temperature**: Controls randomness (0.0-1.0)
- **Max Tokens**: Maximum tokens per response
- **Timeout**: API timeout in seconds
- **Max Retries**: Number of retry attempts
- **Max Turns**: Maximum ReAct execution turns

## Benefits

1. **Single Point of Control**: Change models in one place instead of multiple files
2. **Environment Override**: Easy deployment configuration via environment variables
3. **Type Safety**: All parameters are properly typed and validated
4. **Backward Compatibility**: Existing code continues to work without changes

## Usage in Code

The configuration is automatically used throughout the codebase:

```python
from core.config import config

# Get the current model
model = config.get_llm_model("text")  # or "json" or "default"

# Get other parameters
temperature = config.get_temperature()
max_tokens = config.get_max_tokens("text")
```

## Cost Comparison

| Model | Input Cost (per 1M tokens) | Output Cost (per 1M tokens) | Relative Cost |
|-------|---------------------------|----------------------------|---------------|
| GPT-4o | ~$5-15 | ~$15-60 | 100% |
| GPT-4o-mini | ~$0.15 | ~$0.6 | ~3% |

Using GPT-4o-mini provides approximately **97% cost savings** compared to GPT-4o.
