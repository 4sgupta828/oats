"""Dynamic incident window detection tool

This tool automatically detects anomaly windows from raw telemetry data before
the RCA agent starts its investigation.
"""

from typing import Dict, Any, Optional, List, Tuple
from pydantic import Field
import statistics

from core.sdk import uf, UfInput
from core.logging_config import get_logger
from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer import MetricsAnalyzer

logger = get_logger('incident_detection')


class DetectIncidentWindowInput(UfInput):
    """Input for incident window detection"""
    data_dir: str = Field(..., description="Path to telemetry data directory")
    symptom_hint: Optional[str] = Field(None, description="Optional hint about the symptom (e.g., 'product-catalog errors')")
    lookback_seconds: float = Field(default=300, description="How far back to look for anomalies")
    sensitivity: str = Field(default="high", description="Detection sensitivity: high, medium, or low")


@uf(
    name="detect_incident_window",
    version="1.0.0",
    description="Automatically detect incident and baseline windows from telemetry data. This runs BEFORE the RCA investigation to discover when anomalies occurred. Returns incident window, baseline window, and symptom summary."
)
def detect_incident_window(inputs: DetectIncidentWindowInput) -> Dict[str, Any]:
    """Detect incident window dynamically from telemetry data

    This tool:
    1. Scans all metrics for anomalies using statistical methods
    2. Finds the first and last significant anomaly
    3. Calculates baseline window (time before first anomaly)
    4. Returns structured window information for the RCA agent

    Args:
        inputs: Detection parameters

    Returns:
        Dictionary with incident window, baseline window, and symptom summary
    """
    try:
        # Initialize backend
        backend = SimulationBackend(inputs.data_dir)

        # Get available time range
        min_time, max_time = backend.get_time_range()

        logger.info(f"Detecting incidents in time range [{min_time:.2f}, {max_time:.2f}]")

        # Get topology to find all components
        topology = backend.get_topology()
        components = list(topology.get('components', {}).keys())

        if not components:
            logger.warning("No components found in topology, scanning all data")
            components = [None]  # Will query all metrics

        # Set z-score threshold based on sensitivity
        if inputs.sensitivity == "high":
            z_threshold = 3.0
        elif inputs.sensitivity == "medium":
            z_threshold = 3.5
        else:  # low
            z_threshold = 4.0

        # Scan for anomalies across all components
        all_anomalies = []

        for component in components:
            try:
                # Use a rolling window approach to detect anomalies
                # Split time range into windows
                window_size = 60.0  # 60 second windows
                current_time = min_time

                while current_time < max_time:
                    # Baseline: previous window
                    baseline_start = max(min_time, current_time - window_size)
                    baseline_end = current_time

                    # Incident: current window
                    incident_start = current_time
                    incident_end = min(max_time, current_time + window_size)

                    # Need enough baseline data
                    if (baseline_end - baseline_start) < 30:
                        current_time += window_size
                        continue

                    # Query metrics
                    analyzer = MetricsAnalyzer(backend)
                    anomalies = analyzer.detect_anomalies(
                        component=component,
                        baseline_range=(baseline_start, baseline_end),
                        incident_range=(incident_start, incident_end),
                        metric_pattern="*"
                    )

                    # Filter by z-score threshold
                    significant_anomalies = [a for a in anomalies if abs(a.z_score) >= z_threshold]

                    if significant_anomalies:
                        all_anomalies.extend(significant_anomalies)

                    current_time += window_size / 2  # Overlap windows by 50%

            except Exception as e:
                logger.error(f"Error scanning component {component}: {e}")
                continue

        if not all_anomalies:
            return {
                "status": "success",
                "incident_detected": False,
                "message": f"No significant anomalies detected (z > {z_threshold})",
                "data_time_range": {"start": min_time, "end": max_time}
            }

        # Sort anomalies by timestamp
        all_anomalies.sort(key=lambda a: a.timestamp)

        # Find first and last anomaly
        first_anomaly = all_anomalies[0]
        last_anomaly = all_anomalies[-1]

        # Determine incident window
        incident_start = first_anomaly.timestamp

        # Check if incident is still active (anomalies near end of data)
        if (max_time - last_anomaly.timestamp) < 30:
            # Still active
            incident_end = None
            incident_status = "ACTIVE"
        else:
            incident_end = last_anomaly.timestamp + 30  # Add buffer
            incident_status = "RESOLVED"

        # Calculate baseline window (time before first anomaly)
        baseline_duration = min(inputs.lookback_seconds, incident_start - min_time)
        baseline_start = incident_start - baseline_duration
        baseline_end = incident_start

        # Identify primary symptom component (component with most severe anomaly)
        primary_anomaly = max(all_anomalies, key=lambda a: abs(a.z_score))

        # Build symptom description
        symptom_description = f"{primary_anomaly.component}: {primary_anomaly.metric_name} anomaly ({primary_anomaly.pattern})"

        # Get affected components
        affected_components = list(set(a.component for a in all_anomalies))

        # Summarize anomalies
        anomaly_summaries = []
        for anomaly in all_anomalies[:10]:  # Top 10 anomalies
            anomaly_summaries.append({
                "component": anomaly.component,
                "metric": anomaly.metric_name,
                "anomaly_time": anomaly.timestamp,
                "severity": anomaly.severity,
                "z_score": round(anomaly.z_score, 2),
                "pattern": anomaly.pattern
            })

        return {
            "status": "success",
            "incident_detected": True,
            "incident_window": {
                "start_time": incident_start,
                "end_time": incident_end,
                "status": incident_status
            },
            "baseline_window": {
                "start_time": baseline_start,
                "end_time": baseline_end
            },
            "symptom_summary": {
                "primary_symptom_component": primary_anomaly.component,
                "symptom_description": symptom_description,
                "first_anomaly_time": first_anomaly.timestamp,
                "affected_components": affected_components
            },
            "anomalies_detected": anomaly_summaries,
            "detection_params": {
                "z_threshold": z_threshold,
                "sensitivity": inputs.sensitivity,
                "total_anomalies_found": len(all_anomalies)
            }
        }

    except Exception as e:
        logger.error(f"Error detecting incident window: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to detect incident window: {e}"
        }
