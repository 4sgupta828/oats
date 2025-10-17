"""Visualization Generation Tools for OATS Agent

These tools generate visualization specifications that can be rendered by the UI.
They transform observability data (logs, metrics, traces, topology) into rich, interactive
visualizations that help with investigation and root cause analysis.
"""

from pydantic import Field
from typing import Optional, Dict, List, Any
from core.sdk import uf, UfInput
from core.logging_config import get_logger
from pathlib import Path
import json
import time
from datetime import datetime

logger = get_logger('visualization_tools')


def save_visualization_artifact(viz_spec: Dict[str, Any], viz_type: str, name_suffix: str) -> Dict[str, Any]:
    """Save visualization spec as artifact and return metadata"""
    try:
        from core.sdk import get_execution_context

        # Get execution context for artifact tracking
        context = get_execution_context()
        execution_id = context.get('execution_id') if context else None

        if not execution_id:
            logger.warning("No execution_id available, saving to default location")
            execution_id = "default"

        # Create artifacts directory with execution_id
        artifact_dir = Path(f".oats_artifacts/{execution_id}")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = int(time.time())
        artifact_filename = f"{viz_type}_{name_suffix}_{timestamp}.json"
        artifact_path = artifact_dir / artifact_filename

        # Save visualization spec
        with open(artifact_path, 'w') as f:
            json.dump(viz_spec, f, indent=2)

        logger.info(f"Saved visualization artifact: {artifact_path}")

        # Emit artifact marker for observation parsing (required format)
        relative_artifact_path = f".oats_artifacts/{execution_id}/{artifact_filename}"
        print(f"Artifact available: {relative_artifact_path}")

        return {
            "status": "success",
            "artifact_type": "visualization",
            "artifact_path": relative_artifact_path,
            "viz_type": viz_type,
            "metadata": {
                "title": viz_spec.get("title", ""),
                "timestamp": viz_spec.get("timestamp", ""),
                **viz_spec.get("metadata", {})
            }
        }

    except Exception as e:
        logger.error(f"Failed to save visualization artifact: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to save visualization: {str(e)}"
        }


class GenerateMetricsVisualizationInput(UfInput):
    """Generate time-series visualization from metrics data

    IMPORTANT: This tool REQUIRES input_file. DO NOT pass inline data.
    The tool reads all necessary data from the file.
    """
    title: str = Field(..., description="Chart title (e.g., 'Pod Memory Usage - production')")
    input_file: str = Field(..., description="REQUIRED: Path to JSON file containing metrics data. File must have structure: {'series': [...], 'y_axis_label': '...', 'anomalies': [...], 'events': [...], 'metadata': {...}}. The 'series' and 'y_axis_label' fields are required in the file.")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata to merge with file metadata (namespace, cluster, etc.)")


@uf(name="generate_metrics_visualization", version="1.0.0",
   description="Generate interactive time-series chart from metrics data. REQUIRES input_file parameter with path to JSON file. DO NOT pass inline data like series or y_axis_label - they must be in the file.")
def generate_metrics_visualization(inputs: GenerateMetricsVisualizationInput) -> dict:
    """Generate time-series visualization from metrics"""
    try:
        # Read from file
        try:
            with open(inputs.input_file, 'r') as f:
                file_data = json.load(f)

            # Extract data from file
            series = file_data.get('series', [])
            y_axis_label = file_data.get('y_axis_label', file_data.get('yAxisLabel', 'Value'))
            anomalies = file_data.get('anomalies', [])
            events = file_data.get('events', [])
            metadata = {**(file_data.get('metadata', {})), **(inputs.metadata or {})}

            if not series:
                return {
                    "status": "error",
                    "error": f"'series' field is required in input file {inputs.input_file}"
                }

            logger.info(f"Loaded metrics from file: {inputs.input_file} ({len(series)} series, {sum(len(s.get('data', [])) for s in series)} data points)")

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"File not found: '{inputs.input_file}'"
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Invalid JSON in file '{inputs.input_file}': {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to read input_file '{inputs.input_file}': {str(e)}"
            }

        # Build visualization spec
        viz_spec = {
            "type": "timeseries",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": metadata,
            "data": {
                "yAxisLabel": y_axis_label,
                "series": series,
                "anomalies": anomalies,
                "events": events
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "timeseries", name_suffix)

        if result["status"] == "success":
            total_points = sum(len(s.get('data', [])) for s in series)
            return {
                **result,
                "message": f"Created time-series visualization with {len(series)} series ({total_points} data points total)"
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Error generating metrics visualization: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to generate metrics visualization: {str(e)}"
        }


class GenerateTopologyVisualizationInput(UfInput):
    """Generate topology/network graph visualization

    IMPORTANT: This tool REQUIRES input_file. DO NOT pass inline data.
    The tool reads all necessary data from the file.
    """
    title: str = Field(..., description="Graph title (e.g., 'Service Dependencies - prod namespace')")
    input_file: str = Field(..., description="REQUIRED: Path to JSON file containing topology data. File must have structure: {'nodes': [...], 'edges': [...], 'layout': '...', 'highlights': [...], 'annotations': {...}, 'metadata': {...}}. The 'nodes' and 'edges' fields are required in the file.")
    layout: str = Field(default="hierarchical", description="Layout algorithm override: 'hierarchical', 'force', 'circular'. If not specified, uses layout from file.")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata to merge with file metadata")


@uf(name="generate_topology_visualization", version="1.0.0",
   description="Generate interactive topology/dependency graph. REQUIRES input_file parameter with path to JSON file. DO NOT pass inline data like nodes or edges - they must be in the file.")
def generate_topology_visualization(inputs: GenerateTopologyVisualizationInput) -> dict:
    """Generate topology visualization from nodes and edges"""
    try:
        # Read from file
        try:
            with open(inputs.input_file, 'r') as f:
                file_data = json.load(f)

            # Extract data from file
            nodes = file_data.get('nodes', [])
            edges = file_data.get('edges', [])
            layout = file_data.get('layout', inputs.layout)
            highlights = file_data.get('highlights', [])
            annotations = file_data.get('annotations', {})
            metadata = {**(file_data.get('metadata', {})), **(inputs.metadata or {})}

            if not nodes or not edges:
                return {
                    "status": "error",
                    "error": f"'nodes' and 'edges' fields are required in input file {inputs.input_file}"
                }

            logger.info(f"Loaded topology from file: {inputs.input_file} ({len(nodes)} nodes, {len(edges)} edges)")

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"File not found: '{inputs.input_file}'"
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Invalid JSON in file '{inputs.input_file}': {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to read input_file '{inputs.input_file}': {str(e)}"
            }

        # Build visualization spec
        viz_spec = {
            "type": "topology",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **metadata,
                "node_count": len(nodes),
                "edge_count": len(edges)
            },
            "data": {
                "nodes": nodes,
                "edges": edges,
                "highlights": highlights,
                "annotations": annotations,
                "layout": layout
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "topology", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created topology visualization with {len(nodes)} nodes and {len(edges)} edges"
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Error generating topology visualization: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to generate topology visualization: {str(e)}"
        }


class GenerateLogsVisualizationInput(UfInput):
    """Generate advanced log viewer with filtering

    IMPORTANT: This tool REQUIRES input_file. DO NOT pass inline data.
    The tool reads all necessary data from the file.
    """
    title: str = Field(..., description="Log viewer title (e.g., 'Application Logs - pod-abc-123')")
    input_file: str = Field(..., description="REQUIRED: Path to JSON file containing logs data. File must have structure: {'logs': [...], 'summary': {...}, 'highlights': {...}, 'metadata': {...}}. The 'logs' field is required in the file.")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata to merge with file metadata (pod, namespace, container, etc.)")


@uf(name="generate_logs_visualization", version="1.0.0",
   description="Generate advanced log viewer with filtering, search, and level-based highlighting. REQUIRES input_file parameter with path to JSON file. DO NOT pass inline data like logs - they must be in the file.")
def generate_logs_visualization(inputs: GenerateLogsVisualizationInput) -> dict:
    """Generate logs visualization from log entries"""
    try:
        # Read from file
        try:
            with open(inputs.input_file, 'r') as f:
                file_data = json.load(f)

            logs = file_data.get('logs', [])
            summary = file_data.get('summary')
            highlights = file_data.get('highlights', {})
            metadata = {**(file_data.get('metadata', {})), **(inputs.metadata or {})}

            if not logs:
                return {
                    "status": "error",
                    "error": f"'logs' field is required in input file {inputs.input_file}"
                }

            logger.info(f"Loaded logs from file: {inputs.input_file} ({len(logs)} log entries)")

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"File not found: '{inputs.input_file}'"
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Invalid JSON in file '{inputs.input_file}': {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to read input_file '{inputs.input_file}': {str(e)}"
            }

        # Calculate summary if not provided
        if not summary:
            summary = {"error": 0, "warn": 0, "info": 0, "debug": 0}
            for log in logs:
                level = log.get("level", "INFO").lower()
                if level in summary:
                    summary[level] += 1

        # Build visualization spec
        viz_spec = {
            "type": "logs",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **metadata,
                "total_logs": len(logs)
            },
            "data": {
                "logs": logs,
                "summary": summary,
                "highlights": highlights
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "logs", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created log visualization with {len(logs)} log entries ({summary.get('error', 0)} errors)"
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Error generating logs visualization: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to generate logs visualization: {str(e)}"
        }


class GenerateTraceVisualizationInput(UfInput):
    """Generate distributed trace waterfall visualization

    IMPORTANT: This tool REQUIRES input_file. DO NOT pass inline data.
    The tool reads all necessary data from the file.
    """
    title: str = Field(..., description="Trace title (e.g., 'Distributed Trace - Request ID: abc123')")
    input_file: str = Field(..., description="REQUIRED: Path to JSON file containing trace data. File must have structure: {'trace_id': '...', 'duration': ..., 'spans': [...], 'metadata': {...}}. The 'trace_id', 'duration', and 'spans' fields are required in the file.")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata to merge with file metadata (root_service, etc.)")


@uf(name="generate_trace_visualization", version="1.0.0",
   description="Generate waterfall visualization for distributed traces. REQUIRES input_file parameter with path to JSON file. DO NOT pass inline data like trace_id, duration, or spans - they must be in the file.")
def generate_trace_visualization(inputs: GenerateTraceVisualizationInput) -> dict:
    """Generate trace visualization from span data"""
    try:
        # Read from file
        try:
            with open(inputs.input_file, 'r') as f:
                file_data = json.load(f)

            trace_id = file_data.get('trace_id', file_data.get('traceId', 'unknown'))
            duration = file_data.get('duration', 0)
            spans = file_data.get('spans', [])
            metadata = {**(file_data.get('metadata', {})), **(inputs.metadata or {})}

            if not trace_id or not spans or duration is None:
                return {
                    "status": "error",
                    "error": f"'trace_id', 'duration', and 'spans' fields are required in input file {inputs.input_file}"
                }

            logger.info(f"Loaded trace from file: {inputs.input_file} (trace_id: {trace_id}, {len(spans)} spans)")

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"File not found: '{inputs.input_file}'"
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Invalid JSON in file '{inputs.input_file}': {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to read input_file '{inputs.input_file}': {str(e)}"
            }

        # Build visualization spec
        viz_spec = {
            "type": "trace",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **metadata,
                "trace_id": trace_id,
                "span_count": len(spans)
            },
            "data": {
                "traceId": trace_id,
                "duration": duration,
                "spans": spans
            }
        }

        # Save as artifact
        name_suffix = f"trace_{trace_id[:16]}"
        result = save_visualization_artifact(viz_spec, "trace", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created trace visualization with {len(spans)} spans ({duration}ms total)"
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Error generating trace visualization: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to generate trace visualization: {str(e)}"
        }


class GenerateMermaidDiagramInput(UfInput):
    """Generate Mermaid diagram visualization"""
    title: str = Field(..., description="Diagram title (e.g., 'Pod Lifecycle State Diagram')")
    diagram: str = Field(..., description="Mermaid diagram syntax (e.g., 'stateDiagram-v2\\n    [*] --> Pending\\n    ...')")
    diagram_type: str = Field(..., description="Diagram type: 'stateDiagram', 'flowchart', 'sequence', 'gantt', 'er', 'classDiagram'")
    theme: str = Field(default="dark", description="Theme: 'dark' or 'light'")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata")


@uf(name="generate_mermaid_diagram", version="1.0.0",
   description="Generate Mermaid diagram (flowcharts, sequence diagrams, state machines, etc.). Use this to visualize processes, workflows, state transitions, or system architecture.")
def generate_mermaid_diagram(inputs: GenerateMermaidDiagramInput) -> dict:
    """Generate Mermaid diagram visualization"""
    try:
        # Build visualization spec
        viz_spec = {
            "type": "mermaid",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **(inputs.metadata or {}),
                "diagram_type": inputs.diagram_type,
                "generated_by": "visualization_tool"
            },
            "data": {
                "diagram": inputs.diagram,
                "theme": inputs.theme
            }
        }

        # Save as artifact
        name_suffix = f"{inputs.diagram_type}_{inputs.title.replace(' ', '_')[:30]}"
        result = save_visualization_artifact(viz_spec, "mermaid", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created {inputs.diagram_type} diagram: {inputs.title}"
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Error generating Mermaid diagram: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to generate Mermaid diagram: {str(e)}"
        }
