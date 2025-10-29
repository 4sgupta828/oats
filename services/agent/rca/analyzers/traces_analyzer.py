"""Traces analyzer for latency degradation and dependency analysis"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import statistics

from rca.backends.base import TelemetryBackend, TraceSpan
from core.logging_config import get_logger

logger = get_logger('traces_analyzer')

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.warning("networkx not available, dependency graph features will be limited")


@dataclass
class DegradedSpan:
    """Information about a degraded span"""
    span_name: str
    baseline_p50_ms: float
    baseline_p99_ms: float
    incident_p50_ms: float
    incident_p99_ms: float
    degradation_factor: float
    span_count_baseline: int
    span_count_incident: int
    throughput_change: float
    severity: str


class TracesAnalyzer:
    """Analyzer for detecting trace latency degradation and building dependency graphs"""

    def __init__(self, backend: TelemetryBackend):
        """Initialize traces analyzer

        Args:
            backend: Telemetry backend for querying traces
        """
        self.backend = backend

    def compare_traces(
        self,
        component: str,
        baseline_range: Tuple[float, float],
        incident_range: Tuple[float, Optional[float]]
    ) -> Dict[str, Any]:
        """Compare traces between baseline and incident periods

        Args:
            component: Component name to analyze
            baseline_range: (start, end) for baseline period
            incident_range: (start, end) for incident period

        Returns:
            Dictionary with degraded spans and error analysis
        """
        # Query traces for both periods
        baseline_traces = self.backend.query_traces(baseline_range, component)
        incident_traces = self.backend.query_traces(incident_range, component)

        # Group spans by name
        baseline_by_span = self._group_by_span_name(baseline_traces)
        incident_by_span = self._group_by_span_name(incident_traces)

        # Analyze each span type
        degraded_spans = []
        for span_name in incident_by_span.keys():
            if span_name not in baseline_by_span:
                logger.debug(f"Skipping {span_name} - no baseline data")
                continue

            baseline_spans = baseline_by_span[span_name]
            incident_spans = incident_by_span[span_name]

            # Calculate latency percentiles
            baseline_latencies = [s.duration_ms for s in baseline_spans]
            incident_latencies = [s.duration_ms for s in incident_spans]

            baseline_p50 = self._percentile(sorted(baseline_latencies), 0.50)
            baseline_p99 = self._percentile(sorted(baseline_latencies), 0.99)
            incident_p50 = self._percentile(sorted(incident_latencies), 0.50)
            incident_p99 = self._percentile(sorted(incident_latencies), 0.99)

            # Calculate degradation factor
            if baseline_p99 > 0:
                degradation_factor = incident_p99 / baseline_p99
            else:
                degradation_factor = 1.0

            # Only report significant degradations (>2x)
            if degradation_factor > 2.0:
                # Calculate throughput change
                throughput_change = (len(incident_spans) - len(baseline_spans)) / len(baseline_spans) * 100

                # Determine severity
                if degradation_factor > 10:
                    severity = "HIGH"
                elif degradation_factor > 5:
                    severity = "MEDIUM"
                else:
                    severity = "LOW"

                degraded_spans.append({
                    "span_name": span_name,
                    "baseline_p50_ms": round(baseline_p50, 2),
                    "baseline_p99_ms": round(baseline_p99, 2),
                    "incident_p50_ms": round(incident_p50, 2),
                    "incident_p99_ms": round(incident_p99, 2),
                    "degradation_factor": round(degradation_factor, 1),
                    "span_count_baseline": len(baseline_spans),
                    "span_count_incident": len(incident_spans),
                    "throughput_change": round(throughput_change, 1),
                    "severity": severity
                })

        # Analyze errors
        baseline_errors = sum(1 for s in baseline_traces if s.error)
        incident_errors = sum(1 for s in incident_traces if s.error)

        # Count error types
        error_types = defaultdict(int)
        for span in incident_traces:
            if span.error:
                error_type = span.attributes.get('error.type', 'unknown')
                error_types[error_type] += 1

        return {
            "status": "success",
            "component": component,
            "degraded_spans": sorted(degraded_spans, key=lambda x: x['degradation_factor'], reverse=True),
            "error_span_analysis": {
                "total_error_spans": incident_errors,
                "baseline_error_spans": baseline_errors,
                "error_types": dict(error_types)
            },
            "baseline_range": baseline_range,
            "incident_range": incident_range
        }

    def build_dependency_graph(self, time_range: Tuple[float, Optional[float]]) -> Any:
        """Build dependency graph from trace spans

        Args:
            time_range: Time range to analyze

        Returns:
            NetworkX DiGraph if available, otherwise dict representation
        """
        spans = self.backend.query_traces(time_range)

        if HAS_NETWORKX:
            graph = nx.DiGraph()

            for span in spans:
                # Add node for this span's component
                graph.add_node(span.component)

                # If span has a parent, find parent's component and add edge
                if span.parent_id:
                    # Find parent span
                    parent_span = next((s for s in spans if s.span_id == span.parent_id), None)
                    if parent_span:
                        graph.add_edge(parent_span.component, span.component)

            return graph
        else:
            # Build simple adjacency list representation
            edges = defaultdict(set)

            for span in spans:
                if span.parent_id:
                    parent_span = next((s for s in spans if s.span_id == span.parent_id), None)
                    if parent_span:
                        edges[parent_span.component].add(span.component)

            return {component: list(deps) for component, deps in edges.items()}

    def analyze_dependency_health(
        self,
        source_component: str,
        target_component: str,
        time_range: Tuple[float, Optional[float]]
    ) -> Dict[str, Any]:
        """Analyze health of connection between two components

        Args:
            source_component: Source component name
            target_component: Target component name
            time_range: Time range to analyze

        Returns:
            Dictionary with connectivity metrics
        """
        # Query traces for source component
        spans = self.backend.query_traces(time_range, source_component)

        # Find spans where source calls target
        call_spans = []
        for span in spans:
            # Check if this span represents a call to target
            if target_component in span.name or span.attributes.get('target', '') == target_component:
                call_spans.append(span)

        if not call_spans:
            return {
                "status": "success",
                "source": source_component,
                "target": target_component,
                "connectivity": "UNKNOWN",
                "message": "No calls detected between components"
            }

        # Calculate metrics
        latencies = [s.duration_ms for s in call_spans]
        errors = [s for s in call_spans if s.error]

        error_rate = len(errors) / len(call_spans) if call_spans else 0.0

        # Determine health
        if error_rate > 0.1:
            connectivity = "UNHEALTHY"
        elif error_rate > 0.01:
            connectivity = "DEGRADED"
        else:
            connectivity = "HEALTHY"

        return {
            "status": "success",
            "source": source_component,
            "target": target_component,
            "connectivity": connectivity,
            "latency_ms": {
                "p50": round(self._percentile(sorted(latencies), 0.50), 2),
                "p95": round(self._percentile(sorted(latencies), 0.95), 2),
                "p99": round(self._percentile(sorted(latencies), 0.99), 2)
            },
            "error_rate": round(error_rate, 4),
            "total_calls": len(call_spans),
            "failed_calls": len(errors),
            "health_assessment": connectivity
        }

    def _group_by_span_name(self, spans: List[TraceSpan]) -> Dict[str, List[TraceSpan]]:
        """Group spans by name"""
        grouped = defaultdict(list)
        for span in spans:
            grouped[span.name].append(span)
        return dict(grouped)

    def _percentile(self, sorted_values: List[float], p: float) -> float:
        """Calculate percentile from sorted values"""
        if not sorted_values:
            return 0.0

        k = (len(sorted_values) - 1) * p
        f = int(k)
        c = k - f

        if f + 1 < len(sorted_values):
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
        else:
            return sorted_values[f]
