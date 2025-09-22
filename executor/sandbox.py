# uf_flow/executor/sandbox.py

import sys
import os
import time
import signal
import contextlib
from typing import Callable, Any, Union, Dict
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import ToolResult
from core.logging_config import get_logger

logger = get_logger('sandbox')

class TimeoutError(Exception):
    """Raised when function execution times out."""
    pass


@contextlib.contextmanager
def timeout_context(seconds: int):
    """Context manager to enforce execution timeout."""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Execution timed out after {seconds} seconds")

    # Set up signal handler (Unix only)
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)  # Cancel the alarm
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows fallback - no timeout enforcement
        logger.warning("Timeout enforcement not available on this platform")
        yield


def run_in_sandbox(func: Callable, inputs: Union[Dict[str, Any], Any], timeout: int = 60) -> ToolResult:
    """
    Executes a function with basic sandboxing including timeout and error handling.

    Args:
        func: The function to execute
        inputs: Input parameters for the function
        timeout: Maximum execution time in seconds

    Returns:
        ToolResult with execution status and output
    """
    start_time = time.time()

    try:
        logger.debug(f"Starting sandbox execution of {func.__name__}")

        # Execute with timeout protection
        with timeout_context(timeout):
            # Execute the function - it expects a Pydantic model, not a dict
            result = func(inputs)

        execution_time = int((time.time() - start_time) * 1000)
        logger.debug(f"Sandbox execution completed in {execution_time}ms")

        return ToolResult(
            status="success",
            output=result,
            duration_ms=execution_time
        )

    except TimeoutError as e:
        execution_time = int((time.time() - start_time) * 1000)
        logger.error(f"Function execution timed out: {e}")
        return ToolResult(
            status="failure",
            output=None,
            error=str(e),
            duration_ms=execution_time
        )

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        logger.error(f"Function execution failed: {e}")
        return ToolResult(
            status="failure",
            output=None,
            error=f"Execution error: {str(e)}",
            duration_ms=execution_time
        )


def run_isolated_sandbox(func: Callable, inputs: Union[Dict[str, Any], Any], timeout: int = 60) -> ToolResult:
    """
    Future implementation placeholder for process-isolated sandbox execution.
    Currently uses the same implementation as run_in_sandbox.

    This would use multiprocessing for true isolation but requires more complex
    setup for serializing function calls and managing process communication.
    """
    # For now, delegate to the basic sandbox
    # In future versions, this could use multiprocessing.Process
    return run_in_sandbox(func, inputs, timeout)