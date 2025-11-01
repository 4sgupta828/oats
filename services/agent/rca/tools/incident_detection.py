"""Dynamic incident window detection tool v3

This tool automatically detects anomaly windows from raw telemetry data before
the RCA agent starts its investigation.

Version 3 features (builds on v2):
- Automatic baseline detection (no manual lookback required)
- Single-pass anomaly detection (no duplicates)
- Direction-aware patterns (INCREASE vs DECREASE)
- Temporal clustering to deduplicate anomalies
- Proper primary symptom identification

V3 Advanced Features (ALL ENABLED BY DEFAULT):
- Bayesian Online Changepoint Detection (BOCD) for adaptive baseline detection
- Multivariate anomaly detection using Isolation Forest
- Granger causality analysis for identifying causal relationships
- Seasonality detection and detrending (FFT-based)
- Optional: Streaming processing for large-scale deployments
- Memory-efficient implementation with on-demand time series construction
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
    enable_bayesian_changepoint: bool = Field(default=True, description="Enable Bayesian Online Changepoint Detection (BOCD) for adaptive baseline detection")
    enable_multivariate: bool = Field(default=True, description="Enable multivariate anomaly detection using Isolation Forest")
    enable_causality: bool = Field(default=True, description="Enable Granger causality analysis for identifying causal relationships")
    enable_seasonality: bool = Field(default=True, description="Enable seasonality detection and detrending")
    enable_streaming: bool = Field(default=False, description="Enable streaming processing for large-scale deployments")
    streaming_window_size: float = Field(default=60.0, description="Streaming window size in seconds (only used if enable_streaming=True)")


@uf(
    name="detect_incident_window",
    version="3.0.0",
    description="Automatically detect incident and baseline windows from telemetry data with ALL advanced v3 features enabled by default. This runs BEFORE the RCA investigation to discover when anomalies occurred. Includes: Bayesian changepoint detection for adaptive baselines, multivariate anomaly detection via Isolation Forest, Granger causality analysis for causal relationships, and seasonality detection/detrending. Returns incident window, baseline window, deduplicated symptom summary with confidence scores, and causal relationship graph."
)
def detect_incident_window(inputs: DetectIncidentWindowInput) -> Dict[str, Any]:
    """Detect incident window dynamically from telemetry data (v3 - all features enabled)

    This tool leverages ALL advanced v3 features:
    1. Auto-detects baseline using Bayesian Online Changepoint Detection (BOCD)
    2. Single-pass anomaly detection with multivariate Isolation Forest integration
    3. Seasonality detection and detrending (FFT-based) for periodic patterns
    4. Clusters and deduplicates anomalies using temporal proximity
    5. Identifies primary symptom using sophisticated scoring (errors, latency, resources)
    6. Analyzes Granger causality to identify causal relationships between anomalies
    7. Provides confidence scores and detection methods for each anomaly
    8. Returns comprehensive structured data for the RCA agent

    Args:
        inputs: Detection parameters with v3 feature flags (all enabled by default)

    Returns:
        Dictionary with:
        - incident_window: start/end times, status (ACTIVE/RESOLVED)
        - baseline_window: quality, stability score, detection method
        - primary_symptom: highest-priority anomaly with pattern classification
        - anomalies: deduplicated clusters with confidence and causality
        - causal_relationships: Granger causality graph between anomaly clusters
        - v3_features_enabled: which advanced features were active
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

            # V3: Bayesian Online Changepoint Detection (enabled by default)
            use_bayesian_changepoint=inputs.enable_bayesian_changepoint,
            hazard_lambda=250.0,  # Expected run length = 250 time steps (more conservative)

            # V3: Multivariate anomaly detection (enabled by default)
            use_multivariate_detection=inputs.enable_multivariate,
            multivariate_contamination=0.1,  # Expected 10% anomalies

            # V3: Granger causality analysis (enabled by default)
            analyze_causality=inputs.enable_causality,
            max_granger_lag=5,  # Increased lag for better causality detection

            # V3: Seasonality detection (enabled by default)
            detect_seasonality=inputs.enable_seasonality,
            min_seasonality_confidence=0.7,

            # V3: Streaming processing (disabled by default)
            enable_streaming=inputs.enable_streaming,
            streaming_window_size=inputs.streaming_window_size
        )

        # Initialize v3 analyzer with enhanced config
        analyzer = MetricsAnalyzerV3(backend, config=config)

        # Run detection (all phases including v3 features)
        result = analyzer.detect_incident_and_baseline()

        # Add v3 metadata to result
        if result.get("status") == "success":
            result["analyzer_version"] = "v3"
            result["v3_features_enabled"] = {
                "bayesian_changepoint": inputs.enable_bayesian_changepoint,
                "multivariate_detection": inputs.enable_multivariate,
                "causality_analysis": inputs.enable_causality,
                "seasonality_detection": inputs.enable_seasonality,
                "streaming_processing": inputs.enable_streaming
            }

            # Log enabled features
            enabled_features = [k for k, v in result["v3_features_enabled"].items() if v]
            logger.info(f"V3 features enabled: {', '.join(enabled_features)}")

        return result

    except Exception as e:
        logger.error(f"Error detecting incident window: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to detect incident window: {e}",
            "analyzer_version": "v3"
        }
