"""Universal Artifact Metadata System

This module provides a consistent way to wrap ANY tool output with rich metadata
that enables the UI to automatically detect and visualize data appropriately.

The LLM produces data with metadata hints. The UI uses these hints to offer
visualization options to the user via a dropdown.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from core.logging_config import get_logger

logger = get_logger('artifact_metadata')

# Universal content types
CONTENT_TYPES = {
    # Observability data
    "logs": {
        "visualizations": ["logs_viewer", "timeline", "table"],
        "default": "logs_viewer",
        "supports_search": True,
        "supports_filtering": True
    },
    "metrics": {
        "visualizations": ["timeseries", "heatmap", "table"],
        "default": "timeseries",
        "supports_search": False,
        "supports_filtering": True
    },
    "traces": {
        "visualizations": ["trace_waterfall", "trace_flamegraph", "table"],
        "default": "trace_waterfall",
        "supports_search": True,
        "supports_filtering": True
    },
    "topology": {
        "visualizations": ["graph_hierarchical", "graph_force_directed", "graph_circular", "table"],
        "default": "graph_hierarchical",
        "supports_search": True,
        "supports_filtering": True
    },

    # Code and text
    "code": {
        "visualizations": ["code_viewer", "table"],
        "default": "code_viewer",
        "supports_search": True,
        "supports_filtering": True
    },
    "diff": {
        "visualizations": ["diff_viewer", "side_by_side", "unified"],
        "default": "diff_viewer",
        "supports_search": True,
        "supports_filtering": False
    },
    "commits": {
        "visualizations": ["commit_list", "timeline", "table"],
        "default": "commit_list",
        "supports_search": True,
        "supports_filtering": True
    },

    # Generic formats
    "json": {
        "visualizations": ["json_viewer", "tree_viewer", "table"],
        "default": "json_viewer",
        "supports_search": True,
        "supports_filtering": False
    },
    "yaml": {
        "visualizations": ["yaml_viewer", "tree_viewer", "text_viewer"],
        "default": "yaml_viewer",
        "supports_search": True,
        "supports_filtering": False
    },
    "text": {
        "visualizations": ["text_viewer", "markdown_viewer"],
        "default": "text_viewer",
        "supports_search": True,
        "supports_filtering": False
    },
    "markdown": {
        "visualizations": ["markdown_viewer", "text_viewer"],
        "default": "markdown_viewer",
        "supports_search": True,
        "supports_filtering": False
    },
    "table": {
        "visualizations": ["table", "grid", "csv_export"],
        "default": "table",
        "supports_search": True,
        "supports_filtering": True
    },
    "csv": {
        "visualizations": ["table", "grid", "chart"],
        "default": "table",
        "supports_search": True,
        "supports_filtering": True
    },

    # Flows and timelines
    "timeline": {
        "visualizations": ["timeline", "gantt", "table"],
        "default": "timeline",
        "supports_search": True,
        "supports_filtering": True
    },
    "flows": {
        "visualizations": ["sankey", "graph_force_directed", "timeline"],
        "default": "sankey",
        "supports_search": False,
        "supports_filtering": True
    },

    # Shell output
    "shell_output": {
        "visualizations": ["terminal_viewer", "text_viewer"],
        "default": "terminal_viewer",
        "supports_search": True,
        "supports_filtering": False
    }
}


class ArtifactMetadata:
    """Universal artifact metadata wrapper"""

    def __init__(
        self,
        content_type: str,
        data: Any,
        source_tool: str,
        metadata: Optional[Dict[str, Any]] = None,
        visualization_hints: Optional[Dict[str, Any]] = None
    ):
        self.content_type = content_type
        self.data = data
        self.source_tool = source_tool
        self.metadata = metadata or {}
        self.visualization_hints = visualization_hints or {}
        self.timestamp = datetime.utcnow().isoformat() + "Z"

        # Auto-populate visualization hints from content type
        if content_type in CONTENT_TYPES:
            type_config = CONTENT_TYPES[content_type]
            self.visualization_hints.setdefault("suggested_visualizations", type_config["visualizations"])
            self.visualization_hints.setdefault("default_view", type_config["default"])
            self.visualization_hints.setdefault("supports_search", type_config["supports_search"])
            self.visualization_hints.setdefault("supports_filtering", type_config["supports_filtering"])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "artifact_version": "1.0",
            "content_type": self.content_type,
            "timestamp": self.timestamp,
            "source_tool": self.source_tool,
            "suggested_visualizations": self.visualization_hints.get("suggested_visualizations", []),
            "visualization_hints": self.visualization_hints,
            "metadata": self.metadata,
            "data": self.data
        }


def create_artifact_with_metadata(
    content_type: str,
    data: Any,
    source_tool: str,
    metadata: Optional[Dict[str, Any]] = None,
    visualization_hints: Optional[Dict[str, Any]] = None,
    save_to_file: bool = True,
    file_suffix: str = ""
) -> Dict[str, Any]:
    """
    Create an artifact with universal metadata and optionally save to file.

    Args:
        content_type: Type of content (logs, metrics, traces, etc.)
        data: The actual data
        source_tool: Name of the tool that produced this artifact
        metadata: Additional metadata about the artifact
        visualization_hints: Hints for how to visualize this data
        save_to_file: Whether to save to file
        file_suffix: Suffix for filename

    Returns:
        Dict with artifact info (file_path if saved, or inline data)
    """
    # Create metadata wrapper
    artifact = ArtifactMetadata(
        content_type=content_type,
        data=data,
        source_tool=source_tool,
        metadata=metadata,
        visualization_hints=visualization_hints
    )

    artifact_dict = artifact.to_dict()

    if not save_to_file:
        # Return inline
        return {
            "status": "success",
            "artifact": artifact_dict,
            "inline": True
        }

    # Save to file
    try:
        from core.sdk import get_execution_context

        # Get execution context for artifact tracking
        context = get_execution_context()
        execution_id = context.get('execution_id') if context else None

        if not execution_id:
            execution_id = "default"

        # Create artifacts directory
        artifact_dir = Path(f".oats_artifacts/{execution_id}")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{file_suffix}" if file_suffix else ""
        filename = f"{content_type}{suffix}_{timestamp}.json"
        file_path = artifact_dir / filename

        # Save artifact with metadata
        with open(file_path, 'w') as f:
            json.dump(artifact_dict, f, indent=2)

        logger.info(f"Saved {content_type} artifact with metadata to {file_path}")

        # Emit artifact marker for observation parsing
        relative_path = str(file_path)
        print(f"Artifact available: {relative_path}")

        return {
            "status": "success",
            "artifact_path": relative_path,
            "content_type": content_type,
            "suggested_visualizations": artifact.visualization_hints.get("suggested_visualizations", []),
            "metadata": artifact.metadata,
            "inline": False
        }

    except Exception as e:
        logger.error(f"Failed to save artifact: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to save artifact: {str(e)}"
        }


def should_save_to_file(data: Any, threshold_chars: int = 2000, threshold_items: int = 50) -> bool:
    """Determine if data is large enough to warrant file-based output"""
    if isinstance(data, list):
        return len(data) > threshold_items
    elif isinstance(data, str):
        return len(data) > threshold_chars
    elif isinstance(data, dict):
        data_json = json.dumps(data)
        return len(data_json) > threshold_chars
    return False


def infer_content_type_from_data(data: Any, hint: Optional[str] = None) -> str:
    """
    Infer content type from data structure.

    Args:
        data: The data to analyze
        hint: Optional hint about the data type

    Returns:
        Inferred content type string
    """
    if hint:
        return hint

    if isinstance(data, dict):
        # Check for known structures
        if "logs" in data:
            return "logs"
        elif "series" in data or "metrics" in data:
            return "metrics"
        elif "traces" in data or "spans" in data:
            return "traces"
        elif "nodes" in data and "edges" in data:
            return "topology"
        elif "commits" in data:
            return "commits"
        else:
            return "json"
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            # Inspect first item
            first = data[0]
            if "timestamp" in first and "message" in first:
                return "logs"
            elif "timestamp" in first and "value" in first:
                return "metrics"
            elif "spanId" in first or "traceId" in first:
                return "traces"
            else:
                return "table"
        else:
            return "json"
    elif isinstance(data, str):
        return "text"
    else:
        return "json"
