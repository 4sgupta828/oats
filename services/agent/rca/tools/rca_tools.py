"""RCA tools for systematic incident investigation

This module implements all the RCA tools described in v6.txt prompt and TOOLS_DESIGN.md
"""

from typing import Dict, Any, Optional, List, Tuple
from pydantic import Field
import json
from pathlib import Path

from core.sdk import uf, UfInput
from core.logging_config import get_logger
from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer import MetricsAnalyzer
from rca.analyzers.logs_analyzer import LogsAnalyzer
from rca.analyzers.traces_analyzer import TracesAnalyzer

logger = get_logger('rca_tools')


# ====================================================================================
# Group 1: Situational Awareness Tools
# ====================================================================================

class AnalyzeBlastRadiusInput(UfInput):
    """Input for blast radius analysis"""
    symptom_component: str = Field(..., description="Component showing the primary symptom")
    incident_window: List[float] = Field(..., description="[start, end] timestamps for incident")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="analyze_blast_radius",
    version="1.0.0",
    description="Identify which components are affected and where the failure is contained. Returns directly affected components, downstream affected, upstream suspects, and isolation boundary."
)
def analyze_blast_radius(inputs: AnalyzeBlastRadiusInput) -> Dict[str, Any]:
    """Analyze blast radius of the incident"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        analyzer = TracesAnalyzer(backend)

        start_time, end_time = inputs.incident_window[0], inputs.incident_window[1] if len(inputs.incident_window) > 1 else None

        # Build dependency graph from traces
        dep_graph = analyzer.build_dependency_graph((start_time, end_time))

        # Query all components' metrics to find error rates
        topology = backend.get_topology()
        components = list(topology.get('components', {}).keys())

        error_statistics = {}
        affected_components = []

        for component in components:
            try:
                # Get error metrics
                metrics_analyzer = MetricsAnalyzer(backend)

                # Query error-related metrics
                errors_metrics = backend.query_metrics(
                    component=component,
                    metric_pattern="*error*",
                    time_range=(start_time, end_time)
                )

                if errors_metrics:
                    error_count = sum(m.value for m in errors_metrics)
                    if error_count > 0:
                        affected_components.append(component)
                        error_statistics[component] = {
                            "error_count": int(error_count),
                            "error_rate": round(error_count / len(errors_metrics), 3)
                        }
            except Exception as e:
                logger.debug(f"Error analyzing component {component}: {e}")

        # Classify components
        directly_affected = [inputs.symptom_component]
        if inputs.symptom_component in affected_components:
            affected_components.remove(inputs.symptom_component)

        # Build simple dependency classification
        if isinstance(dep_graph, dict):
            # Get upstream components (those that call symptom_component)
            upstream_suspects = []
            for src, targets in dep_graph.items():
                if inputs.symptom_component in targets:
                    upstream_suspects.append(src)

            # Get downstream components (those called by symptom_component)
            downstream_affected = dep_graph.get(inputs.symptom_component, [])
        else:
            upstream_suspects = list(set(affected_components) - set(directly_affected))
            downstream_affected = []

        # Isolation boundary is the first component with no errors
        isolation_boundary = inputs.symptom_component

        return {
            "status": "success",
            "directly_affected": directly_affected,
            "downstream_affected": list(downstream_affected),
            "upstream_suspects": upstream_suspects,
            "isolation_boundary": isolation_boundary,
            "error_statistics": error_statistics,
            "dependency_graph": dep_graph if isinstance(dep_graph, dict) else {}
        }

    except Exception as e:
        logger.error(f"Error analyzing blast radius: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class GetTemporalTimelineInput(UfInput):
    """Input for temporal timeline analysis"""
    affected_components: List[str] = Field(..., description="List of affected components to analyze")
    incident_window: List[float] = Field(..., description="[start, end] timestamps for incident")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="get_temporal_timeline",
    version="1.0.0",
    description="Find the first component to fail and sequence of cascading failures. Returns timeline of failure events with timestamps, statistical significance, and likely origin component."
)
def get_temporal_timeline(inputs: GetTemporalTimelineInput) -> Dict[str, Any]:
    """Get temporal timeline of failures"""
    try:
        backend = SimulationBackend(inputs.data_dir)

        start_time, end_time = inputs.incident_window[0], inputs.incident_window[1] if len(inputs.incident_window) > 1 else None

        timeline_events = []

        # For each component, find first anomaly
        for component in inputs.affected_components:
            # Check metrics for first anomaly
            metrics = backend.query_metrics(component, "*", (start_time, end_time))
            if metrics:
                first_metric_time = min(m.timestamp for m in metrics)
                timeline_events.append({
                    "timestamp": first_metric_time,
                    "component": component,
                    "event": f"{component} metrics changed",
                    "signal_type": "metric"
                })

            # Check logs for first error
            logs = backend.query_logs(component, (start_time, end_time), level_filter="ERROR")
            if logs:
                first_log = min(logs, key=lambda l: l.timestamp)
                timeline_events.append({
                    "timestamp": first_log.timestamp,
                    "component": component,
                    "event": f"First ERROR log: '{first_log.message[:100]}'",
                    "signal_type": "log",
                    "log_count": len(logs)
                })

            # Check traces for first error span
            traces = backend.query_traces((start_time, end_time), component)
            error_traces = [t for t in traces if t.error]
            if error_traces:
                first_error_trace = min(error_traces, key=lambda t: t.start_time)
                timeline_events.append({
                    "timestamp": first_error_trace.start_time,
                    "component": component,
                    "event": f"First error span: {first_error_trace.name}",
                    "signal_type": "trace"
                })

        # Sort by timestamp
        timeline_events.sort(key=lambda e: e['timestamp'])

        # Determine likely origin (first failure)
        likely_origin = timeline_events[0]['component'] if timeline_events else None

        return {
            "status": "success",
            "likely_origin_component": likely_origin,
            "timeline": timeline_events,
            "time_delta_analysis": {}  # Could add inter-event timing analysis
        }

    except Exception as e:
        logger.error(f"Error getting temporal timeline: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class GetRecentChangesInput(UfInput):
    """Input for recent changes query"""
    component_name: str = Field(..., description="Component to check for changes")
    reference_time: float = Field(..., description="Incident start time (reference point)")
    lookback_seconds: float = Field(default=300, description="How far back to look for changes")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="get_recent_changes",
    version="1.0.0",
    description="Find deployments, config changes, or infrastructure changes near incident time. Returns changes with correlation likelihood based on time proximity to incident."
)
def get_recent_changes(inputs: GetRecentChangesInput) -> Dict[str, Any]:
    """Get recent changes for a component"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        topology = backend.get_topology()

        # Find component in topology
        components = topology.get('components', {})
        if inputs.component_name not in components:
            return {
                "status": "success",
                "changes_detected": [],
                "message": f"Component {inputs.component_name} not found in topology"
            }

        component = components[inputs.component_name]

        # Extract deployment history
        deployment_history = component.get('deployment_history', [])

        changes_detected = []

        for deployment in deployment_history:
            deploy_time = deployment.get('simulation_time', 0)
            time_before_incident = inputs.reference_time - deploy_time

            # Check if within lookback window
            if 0 < time_before_incident <= inputs.lookback_seconds:
                # Calculate correlation likelihood
                if time_before_incident <= 120:  # 2 minutes
                    correlation = "VERY_HIGH"
                elif time_before_incident <= 300:  # 5 minutes
                    correlation = "HIGH"
                elif time_before_incident <= 600:  # 10 minutes
                    correlation = "MEDIUM"
                else:
                    correlation = "LOW"

                changes_detected.append({
                    "timestamp": deploy_time,
                    "component": inputs.component_name,
                    "change_type": "deployment",
                    "description": f"Deployed {deployment.get('commit_id', 'unknown')}: {deployment.get('message', '')}",
                    "time_before_incident": f"{time_before_incident:.1f}s",
                    "correlation_likelihood": correlation,
                    "details": deployment
                })

        # Sort by time (most recent first)
        changes_detected.sort(key=lambda c: c['timestamp'], reverse=True)

        return {
            "status": "success",
            "changes_detected": changes_detected
        }

    except Exception as e:
        logger.error(f"Error getting recent changes: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


# ====================================================================================
# Group 2: Baseline Comparison Tools
# ====================================================================================

class CompareMetricsInput(UfInput):
    """Input for metrics comparison"""
    component_name: str = Field(..., description="Component to analyze")
    incident_window: List[float] = Field(..., description="[start, end] timestamps for incident")
    baseline_window: List[float] = Field(..., description="[start, end] timestamps for baseline")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="compare_metrics",
    version="1.0.0",
    description="Statistical anomaly detection in metrics between baseline and incident windows. Returns only anomalous metrics with z-scores, p-values, and anomaly patterns (SPIKE, STEP_CHANGE, etc.)"
)
def compare_metrics(inputs: CompareMetricsInput) -> Dict[str, Any]:
    """Compare metrics between baseline and incident periods"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        analyzer = MetricsAnalyzer(backend)

        baseline_range = (inputs.baseline_window[0], inputs.baseline_window[1])
        incident_range = (inputs.incident_window[0], inputs.incident_window[1] if len(inputs.incident_window) > 1 else None)

        result = analyzer.compare_metrics(
            component=inputs.component_name,
            baseline_range=baseline_range,
            incident_range=incident_range
        )

        return result

    except Exception as e:
        logger.error(f"Error comparing metrics: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class CompareLogsInput(UfInput):
    """Input for logs comparison"""
    component_name: str = Field(..., description="Component to analyze")
    incident_window: List[float] = Field(..., description="[start, end] timestamps for incident")
    baseline_window: List[float] = Field(..., description="[start, end] timestamps for baseline")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="compare_logs",
    version="1.0.0",
    description="Detect new log templates and frequency spikes in error messages. Returns new templates that appeared during incident and templates with significant frequency increases."
)
def compare_logs(inputs: CompareLogsInput) -> Dict[str, Any]:
    """Compare logs between baseline and incident periods"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        analyzer = LogsAnalyzer(backend)

        baseline_range = (inputs.baseline_window[0], inputs.baseline_window[1])
        incident_range = (inputs.incident_window[0], inputs.incident_window[1] if len(inputs.incident_window) > 1 else None)

        result = analyzer.compare_logs(
            component=inputs.component_name,
            baseline_range=baseline_range,
            incident_range=incident_range
        )

        return result

    except Exception as e:
        logger.error(f"Error comparing logs: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class CompareTracesInput(UfInput):
    """Input for traces comparison"""
    component_name: str = Field(..., description="Component to analyze")
    incident_window: List[float] = Field(..., description="[start, end] timestamps for incident")
    baseline_window: List[float] = Field(..., description="[start, end] timestamps for baseline")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="compare_traces",
    version="1.0.0",
    description="Identify which service calls degraded during the incident. Returns spans with baseline vs incident P99 latency comparison and degradation factors."
)
def compare_traces(inputs: CompareTracesInput) -> Dict[str, Any]:
    """Compare traces between baseline and incident periods"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        analyzer = TracesAnalyzer(backend)

        baseline_range = (inputs.baseline_window[0], inputs.baseline_window[1])
        incident_range = (inputs.incident_window[0], inputs.incident_window[1] if len(inputs.incident_window) > 1 else None)

        result = analyzer.compare_traces(
            component=inputs.component_name,
            baseline_range=baseline_range,
            incident_range=incident_range
        )

        return result

    except Exception as e:
        logger.error(f"Error comparing traces: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


# ====================================================================================
# Group 3: Active Validation Tools
# ====================================================================================

class GetServiceDependenciesInput(UfInput):
    """Input for service dependencies query"""
    service_name: str = Field(..., description="Service name to get dependencies for")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="get_service_dependencies",
    version="1.0.0",
    description="Return the dependency graph for a service. Shows immediate dependencies and their types (database, cache, service, etc.)"
)
def get_service_dependencies(inputs: GetServiceDependenciesInput) -> Dict[str, Any]:
    """Get service dependencies from topology"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        topology = backend.get_topology()

        components = topology.get('components', {})
        if inputs.service_name not in components:
            return {
                "status": "error",
                "error": f"Service {inputs.service_name} not found in topology"
            }

        component = components[inputs.service_name]

        # Extract dependencies
        dependencies = []
        dep_names = component.get('dependencies', [])

        for dep_name in dep_names:
            dep_info = components.get(dep_name, {})
            dependencies.append({
                "name": dep_name,
                "type": dep_info.get('type', 'unknown'),
                "product": dep_info.get('product', None)
            })

        # Build dependency graph
        dependency_graph = {}
        for dep_name in dep_names:
            dep_component = components.get(dep_name, {})
            dependency_graph[dep_name] = dep_component.get('dependencies', [])

        return {
            "status": "success",
            "service": inputs.service_name,
            "dependencies": dependencies,
            "dependency_graph": dependency_graph
        }

    except Exception as e:
        logger.error(f"Error getting service dependencies: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class CheckInstanceHealthInput(UfInput):
    """Input for instance health check"""
    component_name: str = Field(..., description="Component to check health")
    time_window: List[float] = Field(..., description="[start, end] timestamps")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="check_instance_health",
    version="1.0.0",
    description="Get resource utilization metrics for a component (CPU, memory, disk I/O, network). Returns mean/p95/p99 values and health assessment."
)
def check_instance_health(inputs: CheckInstanceHealthInput) -> Dict[str, Any]:
    """Check instance health metrics"""
    try:
        backend = SimulationBackend(inputs.data_dir)

        time_range = (inputs.time_window[0], inputs.time_window[1] if len(inputs.time_window) > 1 else None)

        # Query resource metrics
        cpu_metrics = backend.query_metrics(inputs.component_name, "*cpu*", time_range)
        mem_metrics = backend.query_metrics(inputs.component_name, "*memory*", time_range)

        # Calculate statistics
        def calc_stats(metrics):
            if not metrics:
                return {"mean": 0, "p95": 0, "p99": 0, "max": 0}
            values = sorted([m.value for m in metrics])
            return {
                "mean": round(sum(values) / len(values), 3),
                "p95": round(values[int(len(values) * 0.95)] if len(values) > 0 else 0, 3),
                "p99": round(values[int(len(values) * 0.99)] if len(values) > 0 else 0, 3),
                "max": round(max(values), 3)
            }

        cpu_stats = calc_stats(cpu_metrics)
        mem_stats = calc_stats(mem_metrics)

        # Assess health
        health = "HEALTHY"
        if cpu_stats["max"] > 0.9 or mem_stats["max"] > 0.9:
            health = "DEGRADED"
        if cpu_stats["max"] > 0.95 or mem_stats["max"] > 0.95:
            health = "UNHEALTHY"

        return {
            "status": "success",
            "component": inputs.component_name,
            "cpu_util": cpu_stats,
            "mem_util": mem_stats,
            "health_assessment": health
        }

    except Exception as e:
        logger.error(f"Error checking instance health: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class GetDatabaseStatsInput(UfInput):
    """Input for database stats query"""
    component_name: str = Field(..., description="Database component name")
    time_window: List[float] = Field(..., description="[start, end] timestamps")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="get_database_stats",
    version="1.0.0",
    description="Get database-specific health metrics: connections, slow queries, lock wait times. Detects saturation and performance issues."
)
def get_database_stats(inputs: GetDatabaseStatsInput) -> Dict[str, Any]:
    """Get database statistics"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        topology = backend.get_topology()

        time_range = (inputs.time_window[0], inputs.time_window[1] if len(inputs.time_window) > 1 else None)

        # Get database config from topology
        components = topology.get('components', {})
        db_component = components.get(inputs.component_name, {})
        max_connections = db_component.get('max_connections', 100)

        # Query database metrics
        conn_metrics = backend.query_metrics(inputs.component_name, "*connection*", time_range)
        query_metrics = backend.query_metrics(inputs.component_name, "*query*", time_range)

        # Calculate connection utilization
        if conn_metrics:
            conn_values = [m.value for m in conn_metrics]
            active_connections = {"mean": int(sum(conn_values) / len(conn_values)), "p95": int(sorted(conn_values)[int(len(conn_values) * 0.95)]), "p99": int(sorted(conn_values)[int(len(conn_values) * 0.99)]), "max": int(max(conn_values))}
            conn_utilization = round(active_connections["max"] / max_connections, 2)
        else:
            active_connections = {"mean": 0, "p95": 0, "p99": 0, "max": 0}
            conn_utilization = 0.0

        # Assess health
        health = "HEALTHY"
        saturation = False
        if conn_utilization > 0.8:
            health = "DEGRADED"
        if conn_utilization > 0.9:
            health = "CRITICAL"
            saturation = True

        return {
            "status": "success",
            "component": inputs.component_name,
            "active_connections": active_connections,
            "max_connections": max_connections,
            "connection_utilization": conn_utilization,
            "health_assessment": health,
            "saturation_detected": saturation
        }

    except Exception as e:
        logger.error(f"Error getting database stats: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class GetCacheStatsInput(UfInput):
    """Input for cache stats query"""
    component_name: str = Field(..., description="Cache component name")
    time_window: List[float] = Field(..., description="[start, end] timestamps")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="get_cache_stats",
    version="1.0.0",
    description="Get cache-specific health metrics: hit ratio, evictions, latency. Detects cache misses and eviction policy issues."
)
def get_cache_stats(inputs: GetCacheStatsInput) -> Dict[str, Any]:
    """Get cache statistics"""
    try:
        backend = SimulationBackend(inputs.data_dir)

        time_range = (inputs.time_window[0], inputs.time_window[1] if len(inputs.time_window) > 1 else None)

        # Query cache metrics
        hit_ratio_metrics = backend.query_metrics(inputs.component_name, "*hit*ratio*", time_range)
        eviction_metrics = backend.query_metrics(inputs.component_name, "*eviction*", time_range)

        # Calculate statistics
        if hit_ratio_metrics:
            hit_values = [m.value for m in hit_ratio_metrics]
            hit_ratio = {"mean": round(sum(hit_values) / len(hit_values), 3), "min": round(min(hit_values), 3), "max": round(max(hit_values), 3)}
        else:
            hit_ratio = {"mean": 0, "min": 0, "max": 0}

        if eviction_metrics:
            total_evictions = int(sum(m.value for m in eviction_metrics))
            eviction_rate = round(total_evictions / (len(eviction_metrics) * 60), 2)  # per second
        else:
            total_evictions = 0
            eviction_rate = 0.0

        # Assess health
        health = "HEALTHY"
        anomaly = None
        if hit_ratio["mean"] < 0.5:
            health = "FAULTY"
            anomaly = f"Hit ratio very low ({hit_ratio['mean']:.2%})"
        elif eviction_rate > 50:
            health = "FAULTY"
            anomaly = f"Eviction rate {eviction_rate:.1f}/s is abnormally high"

        return {
            "status": "success",
            "component": inputs.component_name,
            "hit_ratio": hit_ratio,
            "total_evictions": total_evictions,
            "eviction_rate": eviction_rate,
            "health_assessment": health,
            "anomaly_detected": anomaly
        }

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


class CheckDependencyHealthInput(UfInput):
    """Input for dependency health check"""
    source_component: str = Field(..., description="Source component")
    target_component: str = Field(..., description="Target component")
    time_window: List[float] = Field(..., description="[start, end] timestamps")
    data_dir: str = Field(..., description="Path to telemetry data directory")


@uf(
    name="check_dependency_health",
    version="1.0.0",
    description="Check connectivity and health between two components using trace data. Returns latency, error rate, and health assessment."
)
def check_dependency_health(inputs: CheckDependencyHealthInput) -> Dict[str, Any]:
    """Check health of dependency between components"""
    try:
        backend = SimulationBackend(inputs.data_dir)
        analyzer = TracesAnalyzer(backend)

        time_range = (inputs.time_window[0], inputs.time_window[1] if len(inputs.time_window) > 1 else None)

        result = analyzer.analyze_dependency_health(
            source_component=inputs.source_component,
            target_component=inputs.target_component,
            time_range=time_range
        )

        return result

    except Exception as e:
        logger.error(f"Error checking dependency health: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


# ====================================================================================
# Group 4: Finish Tool
# ====================================================================================

class FinishInput(UfInput):
    """Input for finishing RCA investigation"""
    root_cause_component: str = Field(..., description="Component where root cause originated")
    root_cause_finding: str = Field(..., description="Description of the root cause")
    failure_mode: str = Field(..., description="Type of failure (e.g., eviction_policy_bug, connection_pool_exhaustion)")
    trigger_event: str = Field(..., description="What triggered the failure (e.g., deployment:service:v1.2.3)")
    causal_chain: List[str] = Field(..., description="Step-by-step sequence from root cause to symptom")
    evidence_summary: Dict[str, List[str]] = Field(..., description="Summary of evidence by type (metrics, logs, traces)")
    hypothesis_evolution: List[Dict[str, Any]] = Field(..., description="How hypotheses evolved during investigation")
    recommendations: List[str] = Field(..., description="Recommendations for mitigation and prevention")


@uf(
    name="finish",
    version="1.0.0",
    description="Submit final RCA report with root cause, causal chain, evidence, and recommendations. Call this only after completing Phase 5 (Synthesis) of the RCA investigation."
)
def finish(inputs: FinishInput) -> Dict[str, Any]:
    """Submit final RCA report"""
    try:
        import datetime

        # Generate report ID
        report_id = f"rca_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Build comprehensive report
        report = {
            "report_id": report_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "root_cause": {
                "component": inputs.root_cause_component,
                "finding": inputs.root_cause_finding,
                "failure_mode": inputs.failure_mode,
                "trigger_event": inputs.trigger_event
            },
            "causal_chain": inputs.causal_chain,
            "evidence_summary": inputs.evidence_summary,
            "hypothesis_evolution": inputs.hypothesis_evolution,
            "recommendations": inputs.recommendations
        }

        # Save report to file
        try:
            output_dir = Path(".oats_artifacts/rca_reports")
            output_dir.mkdir(parents=True, exist_ok=True)

            report_file = output_dir / f"{report_id}.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)

            logger.info(f"RCA report saved to {report_file}")
        except Exception as e:
            logger.warning(f"Could not save report to file: {e}")

        return {
            "status": "complete",
            "report_id": report_id,
            "summary": "Root cause identified",
            "report": report
        }

    except Exception as e:
        logger.error(f"Error finishing RCA: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
