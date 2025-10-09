# uf_flow/core/sdk.py

from typing import Callable, Type, Any
from pydantic import BaseModel, create_model
import inspect

from .models import UFDescriptor, InputResolver, Invocation
from .logging_config import get_logger

logger = get_logger('sdk')

# A clear alias for developers to use as a base class for their input schemas.
UfInput = BaseModel

def uf(
    name: str,
    version: str,
    description: str,
) -> Callable:
    """
    A decorator to register a Python function as a Unit of Flow (UF).

    This decorator attaches a '_uf_descriptor' attribute to the decorated
    function, which the registry can later discover.
    """
    def decorator(func: Callable) -> Callable:
        # --- Schema Introspection ---
        sig = inspect.signature(func)
        
        # Input schema is derived from the first argument's type hint.
        # It must be a Pydantic model subclassed from UfInput.
        if not sig.parameters:
            error_msg = f"UF function '{name}' must have at least one argument for inputs."
            logger.error(error_msg)
            raise TypeError(error_msg)

        input_param_name = next(iter(sig.parameters))
        input_schema_type: Type[BaseModel] = sig.parameters[input_param_name].annotation

        if not issubclass(input_schema_type, BaseModel):
            error_msg = f"The first argument of '{name}' must be type-hinted with a Pydantic model."
            logger.error(error_msg)
            raise TypeError(error_msg)

        input_schema = input_schema_type.model_json_schema()

        # Output schema is derived from the return type hint.
        output_schema_type = sig.return_annotation
        if output_schema_type is inspect.Signature.empty:
            error_msg = f"UF function '{name}' must have a return type hint."
            logger.error(error_msg)
            raise TypeError(error_msg)
        
        # Create a temporary Pydantic model to generate the JSON schema for the output.
        from pydantic import RootModel
        output_model = RootModel[output_schema_type]
        output_schema = output_model.model_json_schema()


        # --- Default Resolver Template ---
        # For a Python UF, the resolver is simple: map inputs directly.
        data_mapping = {
            field: {
                "source": "context", # Default assumption, orchestrator will map this.
                "value_selector": f"{{inputs.{field}}}"
            } for field in input_schema.get('properties', {})
        }

        resolver_template = InputResolver(
            data_mapping=data_mapping,
            invocation=Invocation(
                type="python",
                template=f"{func.__module__}.{func.__name__}",
                params={} # For python calls, params are passed directly.
            )
        )

        # --- Attach Descriptor ---
        descriptor = UFDescriptor(
            name=name,
            version=version,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            resolver_template=resolver_template,
        )

        setattr(func, '_uf_descriptor', descriptor)
        logger.debug(f"Registered UF: {name} v{version} from {func.__module__}.{func.__name__}")

        return func
    return decorator