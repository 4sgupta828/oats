"""
Centralized logging configuration for UF-Flow Framework.
Provides structured logging with consistent formatting across all modules.
"""

import logging
import logging.handlers
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class UFFlowLogger:
    """Centralized logger for UF-Flow framework."""

    _instance: Optional['UFFlowLogger'] = None
    _configured: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._configured:
            self._setup_logging()
            self._configured = True

    def _setup_logging(self):
        """Setup logging configuration."""
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Clear any existing handlers
        root_logger.handlers.clear()

        # Console handler with simple format
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
        )
        console_handler.setFormatter(console_format)

        # File handler with structured format
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "ufflow.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter())

        # Error file handler for errors only
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "ufflow_errors.log",
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter())

        # Add handlers to root logger
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)

        # Set specific logger levels
        logging.getLogger('ufflow').setLevel(logging.DEBUG)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Get a logger with the specified name."""
        # Ensure the singleton is initialized
        UFFlowLogger()
        return logging.getLogger(f"ufflow.{name}")

    @staticmethod
    def log_execution_start(component: str, operation: str, **kwargs):
        """Log the start of a major operation."""
        logger = UFFlowLogger.get_logger(component)
        extra_fields = {"operation": operation, "status": "started"}
        extra_fields.update(kwargs)
        logger.info(f"Starting {operation}", extra={"extra_fields": extra_fields})

    @staticmethod
    def log_execution_end(component: str, operation: str, success: bool, **kwargs):
        """Log the end of a major operation."""
        logger = UFFlowLogger.get_logger(component)
        extra_fields = {"operation": operation, "status": "completed", "success": success}
        extra_fields.update(kwargs)

        if success:
            logger.info(f"Completed {operation}", extra={"extra_fields": extra_fields})
        else:
            logger.error(f"Failed {operation}", extra={"extra_fields": extra_fields})

    @staticmethod
    def log_tool_execution(tool_name: str, inputs: Dict[str, Any], result: Dict[str, Any]):
        """Log tool execution details."""
        logger = UFFlowLogger.get_logger("executor")
        extra_fields = {
            "tool_name": tool_name,
            "inputs": inputs,
            "result": {
                "status": result.get("status"),
                "success": result.get("success"),
                "return_code": result.get("return_code")
            }
        }

        if result.get("success"):
            logger.info(f"Tool execution successful: {tool_name}",
                       extra={"extra_fields": extra_fields})
        else:
            logger.warning(f"Tool execution failed: {tool_name}",
                          extra={"extra_fields": extra_fields})

    @staticmethod
    def log_plan_generation(goal_id: str, plan_id: str, node_count: int, confidence: float):
        """Log plan generation details."""
        logger = UFFlowLogger.get_logger("planner")
        extra_fields = {
            "goal_id": goal_id,
            "plan_id": plan_id,
            "node_count": node_count,
            "confidence_score": confidence
        }
        logger.info(f"Plan generated for goal {goal_id}",
                   extra={"extra_fields": extra_fields})

    @staticmethod
    def log_security_event(event_type: str, details: Dict[str, Any]):
        """Log security-related events."""
        logger = UFFlowLogger.get_logger("security")
        extra_fields = {"event_type": event_type}
        extra_fields.update(details)

        if event_type in ["command_blocked", "suspicious_activity"]:
            logger.warning(f"Security event: {event_type}",
                          extra={"extra_fields": extra_fields})
        else:
            logger.info(f"Security event: {event_type}",
                       extra={"extra_fields": extra_fields})


# Convenience functions
def get_logger(name: str) -> logging.Logger:
    """Get a logger for the specified component."""
    return UFFlowLogger.get_logger(name)


def setup_logging():
    """Initialize the logging system."""
    UFFlowLogger()