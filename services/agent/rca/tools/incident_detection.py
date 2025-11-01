"""Dynamic incident window detection tool v3

This tool automatically detects anomaly windows from raw telemetry data before
the RCA agent starts its investigation.

Version 3 features (builds on v2):
- Automatic baseline detection (no manual lookback required)
- Single-pass anomaly detection (no duplicates)
- Direction-aware patterns (INCREASE vs DECREASE)
- Temporal clustering to deduplicate anomalies
- Proper primary symptom identification
- NEW: Bayesian Online Changepoint Detection (BOCD) for adaptive baseline detection
- NEW: Multivariate anomaly detection using Isolation Forest
- NEW: Granger causality analysis for identifying causal relationships
- NEW: Seasonality detection and detrending (FFT-based)
- NEW: Memory-efficient implementation for large-scale deployments
"""

from typing import Dict, Any, Optional
from pydantic import Field

from core.sdk import uf, UfInput
from core.logging_config import get_logger
from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer_v3 import MetricsAnalyzerV3, AnalyzerConfig

logger = get_logger('incident_detection')


class DetectIncidentWindowInput(UfInput):
    """Input for incident window detection"""
    data_dir: str = Field(..., description="Path to telemetry data directory")
    symptom_hint: Optional[str] = Field(None, description="Optional hint about the symptom (not currently used)")
    sensitivity: str = Field(default="medium", description="Detection sensitivity: high, medium, or low")
    enable_bayesian_changepoint: bool = Field(default=False, description="Enable Bayesian Online Changepoint Detection (BOCD) for adaptive baseline detection")
    enable_multivariate: bool = Field(default=False, description="Enable multivariate anomaly detection using Isolation Forest")
    enable_causality: bool = Field(default=True, description="Enable Granger causality analysis for identifying causal relationships")
    enable_seasonality: bool = Field(default=False, description="Enable seasonality detection and detrending")


@uf(
    name="detect_incident_window",
    version="3.0.0",
    description="Automatically detect incident and baseline windows from telemetry data with advanced v3 features. This runs BEFORE the RCA investigation to discover when anomalies occurred. Uses automatic baseline detection (no manual lookback needed). NEW: Optional Bayesian changepoint detection, multivariate anomaly detection, Granger causality analysis, and seasonality handling. Returns incident window, baseline window, deduplicated symptom summary, and optional causal relationships."
)
def detect_incident_window(inputs: DetectIncidentWindowInput) -> Dict[str, Any]:
    """Detect incident window dynamically from telemetry data (v3)

    This tool:
    1. Auto-detects baseline using changepoint detection (Bayesian optional)
    2. Single-pass anomaly detection across all metrics (univariate + multivariate)
    3. Clusters and deduplicates anomalies
    4. Identifies primary symptom using temporal precedence
    5. Analyzes causal relationships between anomalies (Granger causality)
    6. Handles seasonal patterns if enabled
    7. Returns structured window information for the RCA agent

    Args:
        inputs: Detection parameters including v3 feature flags

    Returns:
        Dictionary with incident window, baseline window, symptom summary, and causal relationships
    """
    try:
        # Initialize backend
        backend = SimulationBackend(inputs.data_dir)

        # Create enhanced config with all v3 features configurable
        config = AnalyzerConfig(
            sensitivity=inputs.sensitivity,

            # V2 robust statistical methods (always enabled)
            use_mad_for_skewed=True,
            use_adaptive_thresholds=True,
            min_confidence_threshold=0.5,

            # Baseline validation (always enabled)
            validate_baseline_stability=True,
            min_baseline_stability=0.6,

            # False positive filtering (always enabled)
            filter_boundary_anomalies=True,
            boundary_buffer=30.0,
            min_baseline_samples=10,

            # V3 NEW: Bayesian Online Changepoint Detection (optional)
            use_bayesian_changepoint=inputs.enable_bayesian_changepoint,
            hazard_lambda=100.0,  # Expected run length = 100 time steps

            # V3 NEW: Multivariate anomaly detection (optional)
            use_multivariate_detection=inputs.enable_multivariate,
            multivariate_contamination=0.1,  # Expected 10% anomalies

            # V3 NEW: Granger causality analysis (default enabled)
            analyze_causality=inputs.enable_causality,
            max_granger_lag=3,

            # V3 NEW: Seasonality detection (optional)
            detect_seasonality=inputs.enable_seasonality,
            min_seasonality_confidence=0.7
        )

        # Initialize v3 analyzer with enhanced config
        analyzer = MetricsAnalyzerV3(backend, config=config)

        # Run detection (all phases including v3 features)
        result = analyzer.detect_incident_and_baseline()

        # Add v3 metadata to result
        if result.get("status") == "success":
            result["analyzer_version"] = "v3"
            result["v3_features"] = {
                "bayesian_changepoint": inputs.enable_bayesian_changepoint,
                "multivariate_detection": inputs.enable_multivariate,
                "causality_analysis": inputs.enable_causality,
                "seasonality_detection": inputs.enable_seasonality
            }

        return result

    except Exception as e:
        logger.error(f"Error detecting incident window: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to detect incident window: {e}",
            "analyzer_version": "v3"
        }
