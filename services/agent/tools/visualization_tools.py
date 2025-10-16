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
    """Generate time-series visualization from metrics data"""
    title: str = Field(..., description="Chart title (e.g., 'Pod Memory Usage - production')")
    y_axis_label: str = Field(..., description="Y-axis label (e.g., 'Memory (MB)', 'CPU (%)')")
    series: List[Dict[str, Any]] = Field(..., description="List of time-series data: [{'name': 'pod-1', 'data': [[timestamp_ms, value], ...]}]")
    anomalies: Optional[List[Dict[str, Any]]] = Field(None, description="Anomaly regions: [{'start': ts, 'end': ts, 'reason': 'spike detected', 'severity': 'critical'}]")
    events: Optional[List[Dict[str, Any]]] = Field(None, description="Event markers: [{'timestamp': ts, 'label': 'Deployment', 'description': '...'}]")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata (namespace, cluster, etc.)")


@uf(name="generate_metrics_visualization", version="1.0.0",
   description="Generate interactive time-series chart from metrics data. Use this after querying metrics to create visual representation with anomaly highlighting and zoom capabilities.")
def generate_metrics_visualization(inputs: GenerateMetricsVisualizationInput) -> dict:
    """Generate time-series visualization from metrics"""
    try:
        # Build visualization spec
        viz_spec = {
            "type": "timeseries",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": inputs.metadata or {},
            "data": {
                "yAxisLabel": inputs.y_axis_label,
                "series": inputs.series,
                "anomalies": inputs.anomalies or [],
                "events": inputs.events or []
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "timeseries", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created time-series visualization with {len(inputs.series)} series"
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
    """Generate topology/network graph visualization"""
    title: str = Field(..., description="Graph title (e.g., 'Service Dependencies - prod namespace')")
    nodes: List[Dict[str, Any]] = Field(..., description="Nodes: [{'id': 'svc-1', 'label': 'API', 'type': 'service', 'status': 'healthy', 'position': {'x': 0, 'y': 0}, 'metadata': {...}}]")
    edges: List[Dict[str, Any]] = Field(..., description="Edges: [{'id': 'edge-1', 'source': 'svc-1', 'target': 'svc-2', 'label': 'HTTP', 'type': 'http'}]")
    highlights: Optional[List[str]] = Field(None, description="Node IDs to highlight (e.g., unhealthy services)")
    annotations: Optional[Dict[str, str]] = Field(None, description="Annotations for nodes: {'node-id': 'High error rate detected'}")
    layout: str = Field(default="hierarchical", description="Layout algorithm: 'hierarchical', 'force', 'circular'")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata")


@uf(name="generate_topology_visualization", version="1.0.0",
   description="Generate interactive topology/dependency graph. Use this to visualize service mesh, pod relationships, network topology, or any node-edge graph structure.")
def generate_topology_visualization(inputs: GenerateTopologyVisualizationInput) -> dict:
    """Generate topology visualization from nodes and edges"""
    try:
        # Build visualization spec
        viz_spec = {
            "type": "topology",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **(inputs.metadata or {}),
                "node_count": len(inputs.nodes),
                "edge_count": len(inputs.edges)
            },
            "data": {
                "nodes": inputs.nodes,
                "edges": inputs.edges,
                "highlights": inputs.highlights or [],
                "annotations": inputs.annotations or {},
                "layout": inputs.layout
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "topology", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created topology visualization with {len(inputs.nodes)} nodes and {len(inputs.edges)} edges"
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
    """Generate advanced log viewer with filtering"""
    title: str = Field(..., description="Log viewer title (e.g., 'Application Logs - pod-abc-123')")
    logs: List[Dict[str, Any]] = Field(..., description="Log entries: [{'timestamp': '2024-...', 'level': 'ERROR', 'message': '...', 'source': 'app.py:45', 'trace_id': '...'}]")
    summary: Optional[Dict[str, int]] = Field(None, description="Log level summary: {'error': 10, 'warn': 20, 'info': 100, 'debug': 50}")
    highlights: Optional[Dict[str, Any]] = Field(None, description="Time range highlights: {'timeRange': {'start': '...', 'end': '...', 'reason': 'Error spike'}}")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata (pod, namespace, container, etc.)")


@uf(name="generate_logs_visualization", version="1.0.0",
   description="Generate advanced log viewer with filtering, search, and level-based highlighting. Use this after querying logs to provide interactive log analysis.")
def generate_logs_visualization(inputs: GenerateLogsVisualizationInput) -> dict:
    """Generate logs visualization from log entries"""
    try:
        # Calculate summary if not provided
        if not inputs.summary:
            summary = {"error": 0, "warn": 0, "info": 0, "debug": 0}
            for log in inputs.logs:
                level = log.get("level", "INFO").lower()
                if level in summary:
                    summary[level] += 1
        else:
            summary = inputs.summary

        # Build visualization spec
        viz_spec = {
            "type": "logs",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **(inputs.metadata or {}),
                "total_logs": len(inputs.logs)
            },
            "data": {
                "logs": inputs.logs,
                "summary": summary,
                "highlights": inputs.highlights or {}
            }
        }

        # Save as artifact
        name_suffix = inputs.title.replace(" ", "_").replace("/", "_")[:50]
        result = save_visualization_artifact(viz_spec, "logs", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created log visualization with {len(inputs.logs)} log entries ({summary.get('error', 0)} errors)"
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
    """Generate distributed trace waterfall visualization"""
    title: str = Field(..., description="Trace title (e.g., 'Distributed Trace - Request ID: abc123')")
    trace_id: str = Field(..., description="Trace ID")
    duration: int = Field(..., description="Total trace duration in milliseconds")
    spans: List[Dict[str, Any]] = Field(..., description="Spans: [{'spanId': 'span-1', 'parentId': None, 'service': 'api-gateway', 'operation': 'GET /api/users', 'startTime': 0, 'duration': 1250, 'error': False, 'tags': {...}}]")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata (root_service, etc.)")


@uf(name="generate_trace_visualization", version="1.0.0",
   description="Generate waterfall visualization for distributed traces. Use this after querying traces to show request flow through microservices with timing and error information.")
def generate_trace_visualization(inputs: GenerateTraceVisualizationInput) -> dict:
    """Generate trace visualization from span data"""
    try:
        # Build visualization spec
        viz_spec = {
            "type": "trace",
            "title": inputs.title,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                **(inputs.metadata or {}),
                "trace_id": inputs.trace_id,
                "span_count": len(inputs.spans)
            },
            "data": {
                "traceId": inputs.trace_id,
                "duration": inputs.duration,
                "spans": inputs.spans
            }
        }

        # Save as artifact
        name_suffix = f"trace_{inputs.trace_id[:16]}"
        result = save_visualization_artifact(viz_spec, "trace", name_suffix)

        if result["status"] == "success":
            return {
                **result,
                "message": f"Created trace visualization with {len(inputs.spans)} spans ({inputs.duration}ms total)"
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
