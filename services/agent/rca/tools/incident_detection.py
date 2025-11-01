"""Dynamic incident window detection tool v2

This tool automatically detects anomaly windows from raw telemetry data before
the RCA agent starts its investigation.

Version 2 features:
- Automatic baseline detection (no manual lookback required)
- Single-pass anomaly detection (no duplicates)
- Direction-aware patterns (INCREASE vs DECREASE)
- Temporal clustering to deduplicate anomalies
- Proper primary symptom identification
"""

from typing import Dict, Any, Optional
from pydantic import Field

from core.sdk import uf, UfInput
from core.logging_config import get_logger
from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer_v2 import MetricsAnalyzerV2, AnalyzerConfig

logger = get_logger('incident_detection')


class DetectIncidentWindowInput(UfInput):
    """Input for incident window detection"""
    data_dir: str = Field(..., description="Path to telemetry data directory")
    symptom_hint: Optional[str] = Field(None, description="Optional hint about the symptom (not currently used)")
    sensitivity: str = Field(default="medium", description="Detection sensitivity: high, medium, or low")


@uf(
    name="detect_incident_window",
    version="2.0.0",
    description="Automatically detect incident and baseline windows from telemetry data. This runs BEFORE the RCA investigation to discover when anomalies occurred. Uses automatic baseline detection (no manual lookback needed). Returns incident window, baseline window, and deduplicated symptom summary."
)
def detect_incident_window(inputs: DetectIncidentWindowInput) -> Dict[str, Any]:
    """Detect incident window dynamically from telemetry data (v2)

    This tool:
    1. Auto-detects baseline using changepoint detection (no manual lookback)
    2. Single-pass anomaly detection across all metrics
    3. Clusters and deduplicates anomalies
    4. Identifies primary symptom using temporal precedence
    5. Returns structured window information for the RCA agent

    Args:
        inputs: Detection parameters

    Returns:
        Dictionary with incident window, baseline window, and symptom summary
    """
    try:
        # Initialize backend
        backend = SimulationBackend(inputs.data_dir)

        # Initialize analyzer
        analyzer = MetricsAnalyzerV2(backend, sensitivity=inputs.sensitivity)

        # Run detection (all phases)
        result = analyzer.detect_incident_and_baseline()

        return result

    except Exception as e:
        logger.error(f"Error detecting incident window: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to detect incident window: {e}"
        }
