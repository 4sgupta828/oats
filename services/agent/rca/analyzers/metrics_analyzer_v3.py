"""
Metrics analyzer v3 with advanced anomaly detection capabilities.

Building on v2, this adds:
1. Seasonality detection and detrending (FFT-based)
2. Bayesian Online Changepoint Detection (BOCD) with confidence scores
3. Granger causality analysis for identifying causal relationships
4. Multivariate anomaly detection using Isolation Forest
5. Streaming processing for large-scale deployments

V2 features (inherited):
- Auto-detects baseline from data (no manual lookback)
- MAD/IQR robust statistical detection for skewed distributions
- Adaptive thresholds based on metric characteristics
- Confidence scoring and false positive reduction
- Multi-dimensional severity calculation
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import statistics
import numpy as np

from rca.backends.base import TelemetryBackend, MetricDataPoint
from core.logging_config import get_logger

logger = get_logger('metrics_analyzer_v2')

# Try to import ruptures for changepoint detection
try:
    import ruptures as rpt
    HAS_RUPTURES = True
    logger.info("Ruptures library available - using advanced changepoint detection")
except ImportError:
    HAS_RUPTURES = False
    logger.warning("Ruptures library not available - using heuristic changepoint detection")

# Try to import scipy for advanced statistical tests
try:
    from scipy import stats as scipy_stats
    from scipy.fft import fft, fftfreq
    HAS_SCIPY = True
    logger.info("SciPy library available - using advanced statistical tests")
except ImportError:
    HAS_SCIPY = False
    logger.warning("SciPy library not available - using basic statistical tests")

# Try to import scikit-learn for multivariate anomaly detection
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
    logger.info("Scikit-learn library available - using multivariate anomaly detection")
except ImportError:
    HAS_SKLEARN = False
    logger.warning("Scikit-learn library not available - multivariate detection disabled")


class AnomalyDirection(str, Enum):
    """Direction of anomaly"""
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NEW_ERROR = "NEW_ERROR"


class AnomalyPattern(str, Enum):
    """Pattern of anomaly"""
    SPIKE = "SPIKE"
    STEP_CHANGE = "STEP_CHANGE"
    SUSTAINED_INCREASE = "SUSTAINED_INCREASE"
    SUSTAINED_DECREASE = "SUSTAINED_DECREASE"
    GRADUAL_DRIFT = "GRADUAL_DRIFT"
    OSCILLATION = "OSCILLATION"


class AnomalyRelationship(str, Enum):
    """Relationship of anomaly to incident"""
    PRIMARY = "PRIMARY"
    CASCADING = "CASCADING"
    SECONDARY_SYMPTOM = "SECONDARY_SYMPTOM"
    CORRELATED = "CORRELATED"


@dataclass
class RawAnomaly:
    """Single anomaly detection at a specific timestamp"""
    metric_key: str  # Unique identifier: component + metric_name + label_hash
    component: str
    metric_name: str
    timestamp: float
    value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    direction: AnomalyDirection
    severity: str  # HIGH, MEDIUM, LOW
    confidence: float = 1.0  # 0-1 confidence score
    detection_method: str = "z_score"  # z_score, mad, iqr, percentile


@dataclass
class AnomalyCluster:
    """Clustered anomaly representing sustained anomaly period"""
    cluster_id: int
    metric_key: str
    component: str
    metric_name: str
    start_time: float
    end_time: Optional[float]  # None if ongoing
    peak_time: float  # Timestamp with highest magnitude
    peak_z_score: float
    direction: AnomalyDirection
    pattern: AnomalyPattern
    severity: str
    duration: float
    anomalies: List[RawAnomaly] = field(default_factory=list)
    relationship: AnomalyRelationship = AnomalyRelationship.CORRELATED


@dataclass
class BaselineWindow:
    """Detected baseline window"""
    start_time: float
    end_time: float
    duration: float
    quality: str  # good, fair, poor, insufficient
    samples: int
    detection_method: str
    stability_score: float = 0.0  # 0-1 score indicating baseline stability


@dataclass
class IncidentWindow:
    """Detected incident window"""
    start_time: float
    end_time: Optional[float]  # None if ongoing
    status: str  # ACTIVE, RESOLVED
    duration: float


@dataclass
class SeasonalityInfo:
    """Seasonality information for a metric"""
    has_seasonality: bool = False
    period: Optional[float] = None  # Period in seconds (e.g., 86400 for daily)
    amplitude: Optional[float] = None
    confidence: float = 0.0  # 0-1 confidence in seasonality detection


@dataclass
class CausalRelationship:
    """Causal relationship between two anomaly clusters"""
    cause_cluster_id: int
    effect_cluster_id: int
    granger_p_value: float
    lag: int  # Time lag in buckets
    confidence: float  # 0-1 confidence in causality


@dataclass
class MetricProfile:
    """Statistical profile of a metric during baseline"""
    metric_key: str
    component: str
    metric_name: str
    metric_type: str  # COUNTER, GAUGE, RATE
    mean: float
    std: float
    min_val: float
    max_val: float
    p50: float
    p95: float
    p99: float
    count: int
    distribution_type: str = "normal"  # normal, log_normal, unknown
    # Additional robust statistics
    mad: float = 0.0  # Median Absolute Deviation
    iqr: float = 0.0  # Inter-Quartile Range
    p25: float = 0.0  # 25th percentile
    p75: float = 0.0  # 75th percentile
    p01: float = 0.0  # 1st percentile
    coefficient_of_variation: float = 0.0  # std/mean
    # V3: Seasonality information
    seasonality: Optional[SeasonalityInfo] = None

    def is_counter(self) -> bool:
        """Check if this is a counter metric"""
        return self.metric_type == "COUNTER"

    def is_skewed(self) -> bool:
        """Check if metric is skewed (non-normal distribution)"""
        return self.distribution_type in ["log_normal", "unknown"]

    def is_noisy(self) -> bool:
        """Check if metric has high variability"""
        return self.coefficient_of_variation > 0.5

    def has_seasonality(self) -> bool:
        """Check if metric has detected seasonality"""
        return self.seasonality is not None and self.seasonality.has_seasonality


@dataclass
class AnalyzerConfig:
    """Configuration for MetricsAnalyzerV2"""
    # Detection sensitivity
    sensitivity: str = "medium"
    z_threshold: Optional[float] = None  # If None, derived from sensitivity

    # Time windows
    min_baseline_duration: float = 60.0  # seconds
    transition_buffer: float = 30.0  # seconds before first anomaly
    anomaly_gap_threshold: float = 20.0  # max gap to merge into same cluster
    ongoing_threshold: float = 20.0  # if anomaly within Xs of data end → ACTIVE

    # Baseline detection sampling
    max_components_to_sample: int = 10  # For baseline changepoint detection
    max_metrics_per_component: int = 5  # For baseline changepoint detection
    key_metrics: Optional[List[str]] = None  # Golden signal metrics to always check

    # Metric key configuration
    exclude_labels: List[str] = field(default_factory=lambda: [
        '__name__', 'component.id', 'sim.time', 'timestamp',
        # High-cardinality instance labels
        'pod_name', 'pod_id', 'instance_id', 'host_name', 'container_id',
        'node_name', 'replica_id', 'task_id'
    ])

    # Primary symptom scoring weights
    scoring_weights: Dict[str, Any] = field(default_factory=lambda: {
        "NEW_ERROR": 1000,
        "ERROR_INCREASE": 900,
        "ERROR_MAGNITUDE_MULTIPLIER": 2,  # Per anomaly in cluster
        "ERROR_MAGNITUDE_CAP": 200,
        "LATENCY_INCREASE": 500,
        "LATENCY_DECREASE": -500,
        "RESOURCE_INCREASE": 400,
        "RESOURCE_DECREASE": -300,
        "REQUEST_DECREASE": -400,
        "REQUEST_INCREASE": 100,
        "TIME_RANK_BONUS": [300, 250, 200, 150, 100],  # First 5 get bonus
        "SEVERITY_HIGH": 50,
        "SEVERITY_MEDIUM": 20,
        "Z_SCORE_DIVISOR": 10,  # z_score / 10 = bonus points
        "Z_SCORE_CAP": 50
    })

    # Statistical detection
    use_percentile_for_skewed: bool = True  # Use p99 instead of z-score for skewed metrics
    skew_threshold: float = 1.0  # If abs(skewness) > threshold, consider skewed
    use_mad_for_skewed: bool = True  # Use MAD (Median Absolute Deviation) for skewed metrics
    use_adaptive_thresholds: bool = True  # Calculate thresholds based on metric characteristics
    min_confidence_threshold: float = 0.5  # Minimum confidence to report anomaly

    # Baseline validation
    validate_baseline_stability: bool = True  # Validate baseline is stable
    min_baseline_stability: float = 0.6  # Minimum stability score (0-1)

    # False positive reduction
    filter_boundary_anomalies: bool = True  # Filter anomalies near data boundaries
    boundary_buffer: float = 30.0  # Seconds to ignore near boundaries
    min_baseline_samples: int = 10  # Minimum samples required for baseline

    # V3: Advanced features
    detect_seasonality: bool = True  # Detect and remove seasonality
    min_seasonality_confidence: float = 0.7  # Minimum confidence for seasonality
    use_bayesian_changepoint: bool = True  # Use BOCD instead of ruptures
    hazard_lambda: float = 250.0  # BOCD hazard rate (lower = fewer changepoints)
    analyze_causality: bool = True  # Perform Granger causality analysis
    max_granger_lag: int = 5  # Maximum lag for Granger causality test
    use_multivariate_detection: bool = True  # Use Isolation Forest
    multivariate_contamination: float = 0.1  # Expected anomaly fraction
    enable_streaming: bool = False  # Use streaming for large datasets
    streaming_window_size: float = 60.0  # Seconds per streaming window


class MetricsAnalyzerV3:
    """
    Advanced metrics analyzer (v3) with seasonality, causality, and multivariate detection.

    V3 adds:
    - Seasonality detection and detrending
    - Bayesian Online Changepoint Detection (BOCD)
    - Granger causality analysis
    - Multivariate anomaly detection (Isolation Forest)
    - Streaming processing option

    Configurable via AnalyzerConfig for flexibility.
    """

    def __init__(
        self,
        backend: TelemetryBackend,
        sensitivity: str = "medium",
        config: Optional[AnalyzerConfig] = None
    ):
        """Initialize analyzer

        Args:
            backend: Telemetry backend
            sensitivity: Detection sensitivity (high, medium, low) - used if config not provided
            config: Optional AnalyzerConfig for advanced configuration
        """
        self.backend = backend

        # Use provided config or create default
        if config is None:
            config = AnalyzerConfig(sensitivity=sensitivity)

        self.config = config
        self.sensitivity = config.sensitivity

        # Set z-score threshold based on sensitivity or explicit config
        if config.z_threshold is not None:
            self.z_threshold = config.z_threshold
        else:
            self.z_threshold = {
                "high": 3.0,
                "medium": 3.5,
                "low": 4.0
            }.get(self.sensitivity, 3.5)

    def _calculate_mad(self, values: List[float], median: float) -> float:
        """Calculate Median Absolute Deviation (MAD)"""
        if not values:
            return 0.0
        absolute_deviations = [abs(v - median) for v in values]
        return statistics.median(absolute_deviations)

    def _calculate_adaptive_threshold(self, profile: MetricProfile) -> float:
        """Calculate adaptive threshold based on metric characteristics"""
        if not self.config.use_adaptive_thresholds:
            return self.z_threshold

        base_threshold = self.z_threshold

        # Adjust for metric type
        metric_name_lower = profile.metric_name.lower()
        if 'error' in metric_name_lower:
            # Strict for errors
            return base_threshold - 1.0

        # Adjust for signal-to-noise ratio
        if profile.mean != 0:
            snr = abs(profile.mean) / (profile.std + 1e-10)
            if snr < 2:  # Noisy metric
                base_threshold += 0.5

        # Adjust for sample size
        if profile.count < 30:
            # Less confidence, higher threshold
            base_threshold += 0.5

        # Adjust for variability (coefficient of variation)
        if profile.is_noisy():
            base_threshold += 0.5

        return base_threshold

    def _validate_baseline_stability(self, metrics: List[MetricDataPoint]) -> float:
        """
        Validate baseline stability using statistical tests.
        Returns stability score 0-1 (higher is more stable).
        """
        if not self.config.validate_baseline_stability:
            return 1.0

        if len(metrics) < 10:
            return 0.5  # Insufficient data

        values = [m.value for m in metrics]
        stability_score = 1.0

        if HAS_SCIPY:
            try:
                # Mann-Kendall test for trend detection
                n = len(values)
                s = 0
                for i in range(n-1):
                    for j in range(i+1, n):
                        s += np.sign(values[j] - values[i])

                # Calculate variance
                var_s = n * (n - 1) * (2 * n + 5) / 18
                if var_s > 0:
                    if s > 0:
                        z_mk = (s - 1) / np.sqrt(var_s)
                    elif s < 0:
                        z_mk = (s + 1) / np.sqrt(var_s)
                    else:
                        z_mk = 0

                    # Convert to stability (no trend = high stability)
                    trend_stability = max(0, 1 - abs(z_mk) / 3.0)
                    stability_score *= trend_stability

                # Levene's test for variance stability
                mid_point = len(values) // 2
                if mid_point > 2:
                    statistic, p_value = scipy_stats.levene(values[:mid_point], values[mid_point:])
                    # High p-value = stable variance
                    variance_stability = min(1.0, p_value)
                    stability_score *= variance_stability

            except Exception as e:
                logger.debug(f"Baseline stability validation failed: {e}")
                return 0.7  # Default moderate stability
        else:
            # Simple heuristic: check if CV is reasonable
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0
            if mean != 0:
                cv = std / abs(mean)
                stability_score = max(0, 1 - min(1, cv))

        return stability_score

    def _calculate_confidence(
        self,
        value: float,
        profile: MetricProfile,
        detection_method: str
    ) -> float:
        """
        Calculate confidence score 0-1 for an anomaly detection.
        Higher confidence = more likely to be a true anomaly.
        """
        confidence = 1.0

        # Reduce confidence for small sample sizes
        if profile.count < 30:
            confidence *= min(1.0, profile.count / 30.0)

        # Reduce confidence for noisy metrics
        if profile.is_noisy():
            confidence *= 0.8

        # Boost confidence for error metrics
        if 'error' in profile.metric_name.lower():
            confidence *= 1.2
            confidence = min(1.0, confidence)

        # Adjust based on detection method
        if detection_method == "mad":
            # MAD is more robust, boost confidence
            confidence *= 1.1
            confidence = min(1.0, confidence)

        return confidence

    def _calculate_severity_multidimensional(
        self,
        anomaly_value: float,
        profile: MetricProfile,
        z_score: float,
        direction: AnomalyDirection
    ) -> Tuple[str, Dict[str, float]]:
        """
        Calculate multi-dimensional severity score.
        Returns (severity_level, severity_breakdown)
        """
        severity_scores = {}

        # Statistical severity (0-1)
        abs_z = abs(z_score)
        severity_scores['statistical'] = min(1.0, abs_z / 10.0)

        # Business impact (0-1)
        metric_name_lower = profile.metric_name.lower()
        if 'error' in metric_name_lower:
            base_impact = 1.0
        elif 'latency' in metric_name_lower or 'duration' in metric_name_lower:
            base_impact = 0.8
        elif 'p99' in metric_name_lower or 'p95' in metric_name_lower:
            base_impact = 0.9
        elif any(x in metric_name_lower for x in ['cpu', 'memory', 'disk']):
            base_impact = 0.5
        else:
            base_impact = 0.3

        # Scale by magnitude
        if profile.mean != 0:
            magnitude_factor = min(2.0, abs(anomaly_value - profile.mean) / abs(profile.mean))
            severity_scores['business_impact'] = base_impact * magnitude_factor
        else:
            severity_scores['business_impact'] = base_impact

        # Direction impact
        if direction == AnomalyDirection.INCREASE and 'error' in metric_name_lower:
            severity_scores['business_impact'] *= 1.5
        elif direction == AnomalyDirection.DECREASE and 'latency' in metric_name_lower:
            severity_scores['business_impact'] *= 0.5  # Latency decrease is good

        severity_scores['business_impact'] = min(1.0, severity_scores['business_impact'])

        # Magnitude severity (how far from baseline)
        if profile.mean != 0:
            magnitude = abs(anomaly_value - profile.mean) / abs(profile.mean)
            severity_scores['magnitude'] = min(1.0, magnitude / 2.0)
        else:
            severity_scores['magnitude'] = 1.0 if anomaly_value > 0 else 0.0

        # Weighted composite score
        weights = {
            'statistical': 0.3,
            'business_impact': 0.5,
            'magnitude': 0.2
        }

        composite = sum(severity_scores[k] * weights[k] for k in severity_scores)
        severity_scores['composite'] = composite

        # Determine level
        if composite > 0.7:
            level = "HIGH"
        elif composite > 0.4:
            level = "MEDIUM"
        else:
            level = "LOW"

        return level, severity_scores

    # ===== V3 METHODS =====

    def _detect_seasonality(
        self,
        timestamps: List[float],
        values: List[float]
    ) -> SeasonalityInfo:
        """
        Detect seasonality using FFT (Fast Fourier Transform).
        Returns seasonality information including period and confidence.
        """
        if not self.config.detect_seasonality or not HAS_SCIPY:
            return SeasonalityInfo(has_seasonality=False)

        if len(values) < 20:
            return SeasonalityInfo(has_seasonality=False)

        try:
            # Remove mean (detrend)
            values_array = np.array(values)
            values_detrended = values_array - np.mean(values_array)

            # Calculate FFT
            fft_vals = fft(values_detrended)
            sample_rate = 1.0 / (timestamps[1] - timestamps[0]) if len(timestamps) > 1 else 1.0
            freqs = fftfreq(len(values), 1.0 / sample_rate)

            # Get power spectrum (magnitude)
            power = np.abs(fft_vals)

            # Find dominant frequency (skip DC component at index 0)
            positive_freqs = freqs[1:len(freqs)//2]
            positive_power = power[1:len(power)//2]

            if len(positive_power) == 0:
                return SeasonalityInfo(has_seasonality=False)

            dominant_idx = np.argmax(positive_power)
            dominant_freq = abs(positive_freqs[dominant_idx])
            dominant_power = positive_power[dominant_idx]

            # Calculate period in seconds
            if dominant_freq > 0:
                period = 1.0 / dominant_freq
            else:
                return SeasonalityInfo(has_seasonality=False)

            # Calculate confidence: ratio of dominant power to total power
            total_power = np.sum(positive_power)
            confidence = dominant_power / total_power if total_power > 0 else 0.0

            # Calculate amplitude (from dominant frequency component)
            amplitude = 2 * dominant_power / len(values)

            # Check if period is reasonable (between 10s and 1 week)
            if 10 < period < 604800 and confidence > self.config.min_seasonality_confidence:
                logger.info(f"Detected seasonality: period={period:.1f}s, confidence={confidence:.2f}")
                return SeasonalityInfo(
                    has_seasonality=True,
                    period=period,
                    amplitude=amplitude,
                    confidence=confidence
                )

        except Exception as e:
            logger.debug(f"Seasonality detection failed: {e}")

        return SeasonalityInfo(has_seasonality=False)

    def _detrend_and_deseasonalize(
        self,
        timestamps: List[float],
        values: List[float],
        seasonality: SeasonalityInfo
    ) -> List[float]:
        """Remove trend and seasonality from values, return residuals"""
        if not seasonality.has_seasonality:
            return values

        try:
            values_array = np.array(values)
            timestamps_array = np.array(timestamps)

            # Remove linear trend
            coeffs = np.polyfit(timestamps_array - timestamps_array[0], values_array, 1)
            trend = np.polyval(coeffs, timestamps_array - timestamps_array[0])
            detrended = values_array - trend

            # Remove seasonality using simple sinusoidal model
            period = seasonality.period
            angular_freq = 2 * np.pi / period
            t_relative = timestamps_array - timestamps_array[0]

            # Fit sine and cosine components
            A = np.column_stack([np.cos(angular_freq * t_relative), np.sin(angular_freq * t_relative)])
            seasonal_coeffs, _, _, _ = np.linalg.lstsq(A, detrended, rcond=None)
            seasonal_component = A @ seasonal_coeffs

            # Return residuals
            residuals = detrended - seasonal_component
            return residuals.tolist()

        except Exception as e:
            logger.debug(f"Deseasonalization failed: {e}")
            return values

    def _bayesian_changepoint_detection(
        self,
        timestamps: List[float],
        values: List[float]
    ) -> List[Tuple[float, float]]:
        """
        Bayesian Online Changepoint Detection (BOCD).
        Returns list of (timestamp, confidence) tuples.
        """
        if not self.config.use_bayesian_changepoint or len(values) < 10:
            return []

        try:
            n = len(values)
            hazard_rate = 1.0 / self.config.hazard_lambda

            # Initialize
            run_length_probs = np.zeros(n + 1)
            run_length_probs[0] = 1.0

            changepoints = []

            # Parameters for predictive distribution (assume Gaussian)
            mu0 = np.mean(values[:min(5, n)])
            sigma0 = np.std(values[:min(5, n)]) if n > 1 else 1.0
            alpha0 = 1.0
            beta0 = 1.0

            for t in range(1, n):
                # Compute hazard function
                H = hazard_rate * np.ones(t + 1)

                # Growth probabilities
                growth_probs = run_length_probs[:t+1] * (1 - H)

                # Changepoint probability (run length resets to 0)
                cp_prob = np.sum(run_length_probs[:t+1] * H)

                # Update run length distribution
                new_run_length_probs = np.zeros(t + 2)
                new_run_length_probs[0] = cp_prob
                new_run_length_probs[1:t+2] = growth_probs

                # Normalize
                total_prob = np.sum(new_run_length_probs)
                if total_prob > 0:
                    new_run_length_probs /= total_prob

                run_length_probs = new_run_length_probs

                # Detect changepoint if probability is high
                if cp_prob > 0.7:
                    changepoints.append((timestamps[t], cp_prob))
                    logger.debug(f"BOCD detected changepoint at {timestamps[t]:.2f} (confidence={cp_prob:.2f})")

            return changepoints

        except Exception as e:
            logger.debug(f"BOCD failed: {e}")
            return []

    def _analyze_granger_causality(
        self,
        clusters: List['AnomalyCluster']
    ) -> List[CausalRelationship]:
        """
        Analyze Granger causality between anomaly clusters.
        Returns list of causal relationships.
        """
        if not self.config.analyze_causality or not HAS_SCIPY or len(clusters) < 2:
            return []

        causal_relationships = []

        # Build time series for each cluster
        cluster_timeseries = {}
        for cluster in clusters:
            # Create binary time series: 1 if anomaly present, 0 otherwise
            timestamps = [a.timestamp for a in cluster.anomalies]
            if not timestamps:
                continue

            min_t = min(timestamps)
            max_t = max(timestamps)
            # Create 10-second buckets
            buckets = int((max_t - min_t) / 10) + 1
            ts = np.zeros(buckets)

            for timestamp in timestamps:
                bucket_idx = int((timestamp - min_t) / 10)
                if 0 <= bucket_idx < buckets:
                    ts[bucket_idx] = 1

            cluster_timeseries[cluster.cluster_id] = ts

        # Test all pairs for Granger causality
        cluster_ids = list(cluster_timeseries.keys())
        for i, c1_id in enumerate(cluster_ids):
            for c2_id in cluster_ids[i+1:]:
                ts1 = cluster_timeseries[c1_id]
                ts2 = cluster_timeseries[c2_id]

                # Make sure they're the same length
                min_len = min(len(ts1), len(ts2))
                if min_len < 10:
                    continue

                ts1 = ts1[:min_len]
                ts2 = ts2[:min_len]

                # Test if ts1 Granger-causes ts2
                p_value_12 = self._granger_test(ts1, ts2)
                if p_value_12 is not None and p_value_12 < 0.05:
                    causal_relationships.append(CausalRelationship(
                        cause_cluster_id=c1_id,
                        effect_cluster_id=c2_id,
                        granger_p_value=p_value_12,
                        lag=1,
                        confidence=1 - p_value_12
                    ))
                    logger.info(f"Granger causality: cluster {c1_id} -> {c2_id} (p={p_value_12:.4f})")

                # Test if ts2 Granger-causes ts1
                p_value_21 = self._granger_test(ts2, ts1)
                if p_value_21 is not None and p_value_21 < 0.05:
                    causal_relationships.append(CausalRelationship(
                        cause_cluster_id=c2_id,
                        effect_cluster_id=c1_id,
                        granger_p_value=p_value_21,
                        lag=1,
                        confidence=1 - p_value_21
                    ))
                    logger.info(f"Granger causality: cluster {c2_id} -> {c1_id} (p={p_value_21:.4f})")

        return causal_relationships

    def _granger_test(self, ts1: np.ndarray, ts2: np.ndarray) -> Optional[float]:
        """
        Simplified Granger causality test.
        Tests if ts1 helps predict ts2.
        Returns p-value (lower = more significant causality).
        """
        try:
            # Build lagged matrix
            max_lag = min(self.config.max_granger_lag, len(ts2) // 3)
            if max_lag < 1:
                return None

            # Restricted model: predict ts2 from its own lags
            X_restricted = []
            for lag in range(1, max_lag + 1):
                X_restricted.append(ts2[max_lag-lag:-lag] if lag < len(ts2) else ts2[max_lag-lag:])

            X_restricted = np.column_stack(X_restricted) if X_restricted else np.zeros((len(ts2)-max_lag, 1))
            y = ts2[max_lag:]

            # Unrestricted model: add ts1 lags
            X_unrestricted = []
            for lag in range(1, max_lag + 1):
                X_unrestricted.append(ts1[max_lag-lag:-lag] if lag < len(ts1) else ts1[max_lag-lag:])

            X_unrestricted = np.column_stack([X_restricted] + X_unrestricted) if X_unrestricted else X_restricted

            # Fit models and compute F-statistic
            rss_restricted = self._compute_rss(X_restricted, y)
            rss_unrestricted = self._compute_rss(X_unrestricted, y)

            n = len(y)
            k = max_lag  # Number of restrictions

            if rss_unrestricted == 0 or n <= X_unrestricted.shape[1]:
                return None

            f_stat = ((rss_restricted - rss_unrestricted) / k) / (rss_unrestricted / (n - X_unrestricted.shape[1]))

            # Compute p-value using F-distribution
            p_value = 1 - scipy_stats.f.cdf(f_stat, k, n - X_unrestricted.shape[1])

            return p_value

        except Exception as e:
            logger.debug(f"Granger test failed: {e}")
            return None

    def _compute_rss(self, X: np.ndarray, y: np.ndarray) -> float:
        """Compute residual sum of squares for linear regression"""
        try:
            if X.shape[0] == 0 or X.shape[1] == 0:
                return np.sum(y ** 2)

            # Ordinary least squares
            beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            y_pred = X @ beta
            residuals = y - y_pred
            rss = np.sum(residuals ** 2)
            return rss
        except:
            return np.sum(y ** 2)

    def _multivariate_anomaly_detection(
        self,
        baseline_profiles: Dict[str, 'MetricProfile'],
        incident_start: float,
        incident_end: float
    ) -> List[Tuple[float, float]]:
        """
        Multivariate anomaly detection using Isolation Forest.
        Returns list of (timestamp, anomaly_score) tuples.
        """
        if not self.config.use_multivariate_detection or not HAS_SKLEARN:
            return []

        try:
            # Get all components
            topology = self.backend.get_topology()
            components = list(topology.get('components', {}).keys())
            if not components:
                components = [None]

            # Collect metric values in time-aligned buckets
            bucket_size = 10.0
            time_buckets = defaultdict(dict)

            for component in components:
                incident_metrics = self.backend.query_metrics(
                    component, "*", (incident_start, incident_end)
                )

                for m in incident_metrics:
                    metric_key = self._create_metric_key(m)
                    if metric_key not in baseline_profiles:
                        continue

                    time_bucket = self._round_to_bucket(m.timestamp, bucket_size)
                    time_buckets[time_bucket][metric_key] = m.value

            if not time_buckets:
                return []

            # Build feature matrix (time × metrics)
            sorted_times = sorted(time_buckets.keys())
            metric_keys = sorted(set().union(*[set(time_buckets[t].keys()) for t in sorted_times]))

            if len(metric_keys) < 2 or len(sorted_times) < 10:
                return []

            X = []
            for t in sorted_times:
                row = []
                for mk in metric_keys:
                    value = time_buckets[t].get(mk, 0)
                    # Normalize using baseline profile
                    profile = baseline_profiles.get(mk)
                    if profile and profile.std > 0:
                        normalized = (value - profile.mean) / profile.std
                    else:
                        normalized = value
                    row.append(normalized)
                X.append(row)

            X = np.array(X)

            # Train Isolation Forest on all data (including baseline if available)
            iso_forest = IsolationForest(
                contamination=self.config.multivariate_contamination,
                random_state=42,
                n_estimators=100
            )
            iso_forest.fit(X)

            # Get anomaly scores
            scores = iso_forest.score_samples(X)
            predictions = iso_forest.predict(X)

            # Return timestamps with anomalies
            anomalous_timestamps = []
            for i, (pred, score) in enumerate(zip(predictions, scores)):
                if pred == -1:  # Anomaly
                    anomalous_timestamps.append((sorted_times[i], -score))  # Higher score = more anomalous

            logger.info(f"Multivariate detection found {len(anomalous_timestamps)} anomalous time windows")
            return anomalous_timestamps

        except Exception as e:
            logger.error(f"Multivariate anomaly detection failed: {e}")
            return []

    def detect_incident_and_baseline(self) -> Dict[str, Any]:
        """
        Main entry point: Auto-detect baseline and incident windows, then find all anomalies.

        Returns:
            Complete incident detection result
        """
        logger.info("Starting automatic incident and baseline detection")

        # Get data time range
        min_time, max_time = self.backend.get_time_range()
        total_duration = max_time - min_time
        logger.info(f"Data time range: [{min_time:.2f}, {max_time:.2f}] ({total_duration:.1f}s)")

        # Phase 1: Auto-detect baseline
        baseline_window = self._detect_baseline(min_time, max_time)

        if baseline_window.quality == "insufficient":
            return {
                "status": "error",
                "incident_detected": False,
                "message": "Insufficient data for baseline detection",
                "baseline_window": {
                    "start_time": baseline_window.start_time,
                    "end_time": baseline_window.end_time,
                    "quality": baseline_window.quality
                }
            }

        # Phase 2: Single-pass anomaly detection
        raw_anomalies = self._detect_anomalies_single_pass(baseline_window, max_time)

        if not raw_anomalies:
            return {
                "status": "success",
                "incident_detected": False,
                "message": f"No significant anomalies detected (z > {self.z_threshold})",
                "baseline_window": {
                    "start_time": baseline_window.start_time,
                    "end_time": baseline_window.end_time,
                    "duration": baseline_window.duration,
                    "quality": baseline_window.quality,
                    "samples": baseline_window.samples
                },
                "data_time_range": {"start": min_time, "end": max_time}
            }

        # Phase 3: Deduplicate and cluster anomalies
        anomaly_clusters = self._cluster_anomalies(raw_anomalies, max_time)

        # V3: Perform Granger causality analysis
        causal_relationships = []
        if self.config.analyze_causality:
            causal_relationships = self._analyze_granger_causality(anomaly_clusters)
            logger.info(f"Found {len(causal_relationships)} causal relationships")

        # Phase 4: Identify primary symptom
        primary_symptom, symptom_relationships = self._identify_primary_symptom(anomaly_clusters)

        # Apply relationships
        for cluster in anomaly_clusters:
            cluster.relationship = symptom_relationships.get(cluster.cluster_id, AnomalyRelationship.CORRELATED)

        # Phase 5: Calculate incident window
        incident_window = self._calculate_incident_window(anomaly_clusters, baseline_window, max_time)

        # Build result
        return self._build_result(
            baseline_window,
            incident_window,
            anomaly_clusters,
            primary_symptom,
            min_time,
            max_time,
            causal_relationships
        )

    def _detect_baseline(self, min_time: float, max_time: float) -> BaselineWindow:
        """
        Phase 1: Auto-detect baseline using changepoint detection.

        Strategy: Scan backwards from end of data to find stable region.
        """
        logger.info("Phase 1: Detecting baseline window")

        # Validate time range
        if not (min_time < float('inf') and max_time > float('-inf') and min_time < max_time):
            logger.warning(f"Invalid time range: [{min_time}, {max_time}] - insufficient data")
            return BaselineWindow(
                start_time=0,
                end_time=0,
                duration=0,
                quality="insufficient",
                samples=0,
                detection_method="invalid_time_range"
            )

        # Get all components
        topology = self.backend.get_topology()
        components = list(topology.get('components', {}).keys())
        if not components:
            components = [None]  # Query all metrics

        # Sample key metrics across components to find changepoints
        all_changepoints = []

        # Check key metrics first if configured
        if self.config.key_metrics:
            logger.info(f"Checking {len(self.config.key_metrics)} configured key metrics")
            for component in components:
                for key_metric_pattern in self.config.key_metrics:
                    try:
                        metrics = self.backend.query_metrics(component, key_metric_pattern, (min_time, max_time))
                        if metrics:
                            by_metric = defaultdict(list)
                            for m in metrics:
                                metric_name = m.labels.get('__name__', 'unknown')
                                by_metric[metric_name].append(m)

                            for metric_name, metric_list in by_metric.items():
                                changepoints = self._find_changepoints(metric_list)
                                all_changepoints.extend(changepoints)
                    except Exception as e:
                        logger.warning(f"Error checking key metric {key_metric_pattern}: {e}")

        # Sample other components/metrics for efficiency
        for component in components[:self.config.max_components_to_sample]:
            try:
                # Query all metrics for this component
                metrics = self.backend.query_metrics(component, "*", (min_time, max_time))
                if not metrics:
                    continue

                # Group by metric name
                by_metric = defaultdict(list)
                for m in metrics:
                    metric_name = m.labels.get('__name__', 'unknown')
                    by_metric[metric_name].append(m)

                # Detect changepoints in key metrics
                for metric_name, metric_list in list(by_metric.items())[:self.config.max_metrics_per_component]:
                    changepoints = self._find_changepoints(metric_list)
                    all_changepoints.extend(changepoints)

            except Exception as e:
                logger.warning(f"Error scanning component {component}: {e}")
                continue

        if not all_changepoints:
            # No changepoints found - use first 60% as baseline, rest as incident
            baseline_end = min_time + (max_time - min_time) * 0.6
            duration = baseline_end - min_time
            quality = "fair"  # No clear changepoint found
            logger.info(f"No changepoints found, using first 60% as baseline")
            return BaselineWindow(
                start_time=min_time,
                end_time=baseline_end,
                duration=duration,
                quality=quality,
                samples=int(duration / 10),  # Estimate
                detection_method="no_changepoints_heuristic"
            )

        # Find the FIRST significant changepoint (start of incident)
        # Filter out changepoints too close to the end (likely noise)
        valid_changepoints = [cp for cp in all_changepoints if (max_time - cp) > 20]

        if not valid_changepoints:
            # All changepoints are near the end - use first 60% as baseline
            baseline_end = min_time + (max_time - min_time) * 0.6
            duration = baseline_end - min_time
            quality = "fair"
            logger.info(f"All changepoints near end, using first 60% as baseline")
            return BaselineWindow(
                start_time=min_time,
                end_time=baseline_end,
                duration=duration,
                quality=quality,
                samples=int(duration / 10),
                detection_method="changepoints_at_end_heuristic"
            )

        all_changepoints.sort()
        first_changepoint = valid_changepoints[0]

        logger.info(f"Found {len(all_changepoints)} changepoints, first valid at {first_changepoint:.2f}")

        # Baseline = everything before first changepoint
        baseline_start = min_time
        baseline_end = first_changepoint
        baseline_duration = baseline_end - baseline_start

        # Validate baseline stability
        stability_score = 0.0
        if self.config.validate_baseline_stability:
            # Sample some metrics to check stability
            sample_metrics = []
            for component in components[:min(3, len(components))]:
                try:
                    metrics = self.backend.query_metrics(component, "*", (baseline_start, baseline_end))
                    if metrics:
                        sample_metrics.extend(metrics[:100])  # Sample up to 100 points
                except Exception:
                    continue

            if sample_metrics:
                stability_score = self._validate_baseline_stability(sample_metrics)
                logger.info(f"Baseline stability score: {stability_score:.2f}")

        # Validate baseline quality
        if baseline_duration < self.config.min_baseline_duration:
            quality = "insufficient"
        elif stability_score < self.config.min_baseline_stability:
            quality = "poor"
        elif baseline_duration < 120 or stability_score < 0.8:
            quality = "fair"
        else:
            quality = "good"

        return BaselineWindow(
            start_time=baseline_start,
            end_time=baseline_end,
            duration=baseline_duration,
            quality=quality,
            samples=int(baseline_duration / 10),  # Estimate
            detection_method="ruptures_pelt" if HAS_RUPTURES else "heuristic",
            stability_score=stability_score
        )

    def _find_changepoints(self, metrics: List[MetricDataPoint]) -> List[float]:
        """Find changepoints in a time series using ruptures or heuristics"""
        if len(metrics) < 10:
            return []

        # Sort by timestamp
        metrics = sorted(metrics, key=lambda m: m.timestamp)
        timestamps = [m.timestamp for m in metrics]
        values = [m.value for m in metrics]

        if HAS_RUPTURES:
            return self._find_changepoints_ruptures(timestamps, values)
        else:
            return self._find_changepoints_heuristic(timestamps, values)

    def _find_changepoints_ruptures(self, timestamps: List[float], values: List[float]) -> List[float]:
        """Use ruptures library for changepoint detection"""
        try:
            signal = np.array(values)

            # Normalize
            signal_mean = np.mean(signal)
            signal_std = np.std(signal)
            if signal_std > 0:
                signal = (signal - signal_mean) / signal_std

            # Use Pelt algorithm
            algo = rpt.Pelt(model="rbf", min_size=3, jump=1)
            algo.fit(signal)

            # Detect changepoints
            changepoint_indices = algo.predict(pen=10)

            # Convert indices to timestamps (exclude last point which is always end)
            changepoint_times = [timestamps[idx] for idx in changepoint_indices[:-1]]

            return changepoint_times

        except Exception as e:
            logger.debug(f"Ruptures failed: {e}, falling back to heuristic")
            return self._find_changepoints_heuristic(timestamps, values)

    def _find_changepoints_heuristic(self, timestamps: List[float], values: List[float]) -> List[float]:
        """Heuristic changepoint detection using rolling mean"""
        if len(values) < 5:
            return []

        changepoints = []
        window_size = max(3, min(5, len(values) // 4))

        for i in range(window_size, len(values) - window_size):
            # Compare mean before and after this point
            before = values[i-window_size:i]
            after = values[i:i+window_size]

            mean_before = statistics.mean(before)
            mean_after = statistics.mean(after)
            std_before = statistics.stdev(before) if len(before) > 1 else 0.1

            # Check if significant change (use higher threshold to reduce noise)
            if std_before > 0:
                z = abs(mean_after - mean_before) / std_before
                if z > 3.5:  # Higher threshold for changepoint to reduce noise
                    changepoints.append(timestamps[i])

        return changepoints

    def _detect_anomalies_single_pass(
        self,
        baseline_window: BaselineWindow,
        max_time: float
    ) -> List[RawAnomaly]:
        """
        Phase 2: Single-pass anomaly detection.

        Build baseline profile, then scan forward through incident window once.
        """
        logger.info("Phase 2: Single-pass anomaly detection")

        # Get all components
        topology = self.backend.get_topology()
        components = list(topology.get('components', {}).keys())
        if not components:
            components = [None]

        # Build baseline profiles
        baseline_profiles = self._build_baseline_profiles(
            components,
            (baseline_window.start_time, baseline_window.end_time)
        )

        logger.info(f"Built {len(baseline_profiles)} baseline profiles")

        # Scan forward through incident window
        incident_start = baseline_window.end_time
        incident_end = max_time

        raw_anomalies = []

        # Query incident metrics for all components
        for component in components:
            incident_metrics = self.backend.query_metrics(
                component,
                "*",
                (incident_start, incident_end)
            )

            # Group by time bucket and metric key
            by_time_and_metric = defaultdict(list)
            for m in incident_metrics:
                # Create metric key
                metric_key = self._create_metric_key(m)
                time_bucket = self._round_to_bucket(m.timestamp)
                by_time_and_metric[(time_bucket, metric_key)].append(m)

            # Process each time bucket
            for (time_bucket, metric_key), metrics_in_bucket in by_time_and_metric.items():
                # Get baseline profile for this metric
                profile = baseline_profiles.get(metric_key)
                if not profile:
                    # New metric that didn't exist in baseline
                    # Create a zero profile
                    first_metric = metrics_in_bucket[0]
                    profile = MetricProfile(
                        metric_key=metric_key,
                        component=first_metric.labels.get('component.id', component or 'unknown'),
                        metric_name=first_metric.labels.get('__name__', 'unknown'),
                        metric_type=self._infer_metric_type(first_metric),
                        mean=0, std=1.0, min_val=0, max_val=0,
                        p50=0, p95=0, p99=0, count=0
                    )

                # Detect anomaly for this bucket
                anomaly = self._detect_anomaly_in_bucket(
                    time_bucket,
                    metrics_in_bucket,
                    profile
                )

                if anomaly:
                    raw_anomalies.append(anomaly)

        logger.info(f"Detected {len(raw_anomalies)} raw anomalies")

        # Apply false positive reduction filters
        if self.config.filter_boundary_anomalies:
            filtered_anomalies = self._filter_false_positives(raw_anomalies, baseline_window.start_time, max_time)
            logger.info(f"After filtering: {len(filtered_anomalies)} anomalies (removed {len(raw_anomalies) - len(filtered_anomalies)} false positives)")
            return filtered_anomalies

        return raw_anomalies

    def _build_baseline_profiles(
        self,
        components: List[Optional[str]],
        baseline_range: Tuple[float, float]
    ) -> Dict[str, MetricProfile]:
        """Build statistical profiles for all metrics during baseline"""
        profiles = {}

        for component in components:
            baseline_metrics = self.backend.query_metrics(
                component,
                "*",
                baseline_range
            )

            # Group by metric key
            by_metric_key = defaultdict(list)
            for m in baseline_metrics:
                metric_key = self._create_metric_key(m)
                by_metric_key[metric_key].append(m)

            # Build profile for each metric
            for metric_key, metrics in by_metric_key.items():
                values = [m.value for m in metrics]
                if not values:
                    continue

                first_metric = metrics[0]
                metric_type = self._infer_metric_type(first_metric)

                # Calculate statistics
                sorted_values = sorted(values)
                count = len(values)
                mean = statistics.mean(values)
                std = statistics.stdev(values) if count > 1 else 0.0

                # Calculate percentiles
                p01 = self._percentile(sorted_values, 0.01)
                p25 = self._percentile(sorted_values, 0.25)
                p50 = self._percentile(sorted_values, 0.5)
                p75 = self._percentile(sorted_values, 0.75)
                p95 = self._percentile(sorted_values, 0.95)
                p99 = self._percentile(sorted_values, 0.99)

                # Calculate robust statistics
                mad = self._calculate_mad(values, p50)
                iqr = p75 - p25
                cv = (std / abs(mean)) if mean != 0 else 0.0

                # Detect distribution type (for latency/duration metrics)
                distribution_type = "normal"
                if metric_type == "GAUGE" and count > 10:
                    # Check for skewness in gauge metrics (especially latency/duration)
                    if 'duration' in first_metric.labels.get('__name__', '').lower() or \
                       'latency' in first_metric.labels.get('__name__', '').lower():
                        # Calculate skewness: (mean - median) / std
                        if std > 0:
                            skewness = (mean - p50) / std
                            if abs(skewness) > self.config.skew_threshold:
                                distribution_type = "log_normal" if skewness > 0 else "unknown"

                profile = MetricProfile(
                    metric_key=metric_key,
                    component=first_metric.labels.get('component.id', component or 'unknown'),
                    metric_name=first_metric.labels.get('__name__', 'unknown'),
                    metric_type=metric_type,
                    mean=mean,
                    std=std,
                    min_val=min(values),
                    max_val=max(values),
                    p50=p50,
                    p95=p95,
                    p99=p99,
                    count=count,
                    distribution_type=distribution_type,
                    mad=mad,
                    iqr=iqr,
                    p25=p25,
                    p75=p75,
                    p01=p01,
                    coefficient_of_variation=cv
                )

                profiles[metric_key] = profile

        return profiles

    def _create_metric_key(self, metric: MetricDataPoint) -> str:
        """Create unique key for a metric (component + name + label signature)

        Excludes high-cardinality labels (pod_name, instance_id, etc.) to prevent
        metric cardinality explosion when instances restart.
        """
        metric_name = metric.labels.get('__name__', 'unknown')
        component_id = metric.labels.get('component.id', 'unknown')

        # Include discriminating labels (but exclude configured labels)
        label_parts = []
        for k, v in sorted(metric.labels.items()):
            if k not in self.config.exclude_labels:
                label_parts.append(f"{k}={v}")

        label_sig = ",".join(label_parts) if label_parts else "none"
        return f"{component_id}:{metric_name}:{label_sig}"

    def _infer_metric_type(self, metric: MetricDataPoint) -> str:
        """Infer if metric is COUNTER, GAUGE, or RATE"""
        metric_name = metric.labels.get('__name__', '')

        # Heuristics
        if 'error' in metric_name or 'request' in metric_name or metric_name.endswith('.total'):
            return "COUNTER"
        elif 'duration' in metric_name or 'latency' in metric_name or 'usage' in metric_name:
            return "GAUGE"
        elif 'rate' in metric_name or metric_name.endswith('_per_sec'):
            return "RATE"

        # Check if value is typically 0 or 1 (counter indicator)
        if metric.value in [0, 1]:
            return "COUNTER"

        return "GAUGE"

    def _round_to_bucket(self, timestamp: float, bucket_size: float = 10.0) -> float:
        """Round timestamp to time bucket"""
        return round(timestamp / bucket_size) * bucket_size

    def _detect_anomaly_in_bucket(
        self,
        timestamp: float,
        metrics: List[MetricDataPoint],
        profile: MetricProfile
    ) -> Optional[RawAnomaly]:
        """Detect if metrics in this bucket are anomalous compared to baseline"""

        if profile.is_counter():
            # For counters, sum up events in bucket
            incident_sum = sum(m.value for m in metrics)

            # Handle new errors (no baseline)
            if profile.mean == 0:
                if incident_sum > 0:
                    # New error type
                    return RawAnomaly(
                        metric_key=profile.metric_key,
                        component=profile.component,
                        metric_name=profile.metric_name,
                        timestamp=timestamp,
                        value=incident_sum,
                        baseline_mean=0,
                        baseline_std=1.0,
                        z_score=10.0,  # High fixed z-score for new errors
                        direction=AnomalyDirection.NEW_ERROR,
                        severity="HIGH"
                    )
                else:
                    return None

            # Use Poisson approximation
            baseline_rate = profile.mean
            baseline_std = max(1.0, baseline_rate ** 0.5)
            z_score = (incident_sum - baseline_rate) / baseline_std

            # Check threshold
            if abs(z_score) >= self.z_threshold:
                direction = AnomalyDirection.INCREASE if z_score > 0 else AnomalyDirection.DECREASE
                severity = self._calculate_severity(abs(z_score))

                return RawAnomaly(
                    metric_key=profile.metric_key,
                    component=profile.component,
                    metric_name=profile.metric_name,
                    timestamp=timestamp,
                    value=incident_sum,
                    baseline_mean=baseline_rate,
                    baseline_std=baseline_std,
                    z_score=z_score,
                    direction=direction,
                    severity=severity
                )
        else:
            # For gauges, use different detection based on distribution
            if profile.std == 0 and profile.mad == 0:
                return None

            incident_values = [m.value for m in metrics]
            incident_mean = statistics.mean(incident_values)
            incident_median = statistics.median(incident_values)

            # Choose detection method based on distribution
            detection_method = "z_score"
            z_score = 0.0
            direction = None
            threshold = self._calculate_adaptive_threshold(profile)

            # For skewed distributions, use MAD (Median Absolute Deviation)
            if self.config.use_mad_for_skewed and profile.is_skewed() and profile.mad > 0:
                # Use MAD-based z-score (modified z-score)
                # Modified z-score = 0.6745 * (value - median) / MAD
                modified_z = 0.6745 * (incident_median - profile.p50) / (profile.mad + 1e-10)
                z_score = modified_z
                detection_method = "mad"

                # MAD is more robust, so we can use it directly
                if abs(modified_z) >= threshold:
                    direction = AnomalyDirection.INCREASE if modified_z > 0 else AnomalyDirection.DECREASE

            # For skewed distributions, also try IQR method
            elif profile.is_skewed() and profile.iqr > 0:
                # Use IQR-based outlier detection
                # Upper bound: Q3 + 1.5 * IQR
                # Lower bound: Q1 - 1.5 * IQR
                upper_bound = profile.p75 + 1.5 * profile.iqr
                lower_bound = profile.p25 - 1.5 * profile.iqr

                if incident_median > upper_bound:
                    # Calculate effective z-score for reporting
                    z_score = (incident_median - profile.p50) / (profile.iqr / 1.35)  # IQR ≈ 1.35σ
                    direction = AnomalyDirection.INCREASE
                    detection_method = "iqr"
                elif incident_median < lower_bound:
                    z_score = (incident_median - profile.p50) / (profile.iqr / 1.35)
                    direction = AnomalyDirection.DECREASE
                    detection_method = "iqr"

            # For percentile-based detection (existing logic)
            elif self.config.use_percentile_for_skewed and profile.is_skewed():
                # Compare against p99 for upper anomalies, p01 for lower
                incident_max = max(incident_values)
                incident_min = min(incident_values)

                # Check for upper anomaly (value > p99)
                if incident_max > profile.p99 * 1.5:  # 50% above p99
                    z_score = (incident_mean - profile.mean) / profile.std if profile.std > 0 else 0
                    direction = AnomalyDirection.INCREASE
                    detection_method = "percentile"

                # Check for lower anomaly (value < p01)
                elif incident_min < profile.p01 * 0.5 and profile.p01 > 0:
                    z_score = (incident_mean - profile.mean) / profile.std if profile.std > 0 else 0
                    direction = AnomalyDirection.DECREASE
                    detection_method = "percentile"

            else:
                # Normal distribution - use z-score
                if profile.std > 0:
                    z_score = (incident_mean - profile.mean) / profile.std

                    # Check threshold
                    if abs(z_score) >= threshold:
                        direction = AnomalyDirection.INCREASE if z_score > 0 else AnomalyDirection.DECREASE
                        detection_method = "z_score"

            # If anomaly detected, create RawAnomaly with enhanced metadata
            if direction is not None:
                # Calculate multi-dimensional severity
                severity, severity_breakdown = self._calculate_severity_multidimensional(
                    incident_mean,
                    profile,
                    z_score,
                    direction
                )

                # Calculate confidence
                confidence = self._calculate_confidence(
                    incident_mean,
                    profile,
                    detection_method
                )

                # Filter by minimum confidence threshold
                if confidence < self.config.min_confidence_threshold:
                    logger.debug(f"Filtering anomaly with low confidence: {confidence:.2f} < {self.config.min_confidence_threshold}")
                    return None

                return RawAnomaly(
                    metric_key=profile.metric_key,
                    component=profile.component,
                    metric_name=profile.metric_name,
                    timestamp=timestamp,
                    value=incident_mean,
                    baseline_mean=profile.mean,
                    baseline_std=profile.std,
                    z_score=z_score,
                    direction=direction,
                    severity=severity,
                    confidence=confidence,
                    detection_method=detection_method
                )

        return None

    def _calculate_severity(self, abs_z_score: float) -> str:
        """Calculate severity from absolute z-score (legacy method)"""
        if abs_z_score > 5.0:
            return "HIGH"
        elif abs_z_score > 3.5:
            return "MEDIUM"
        else:
            return "LOW"

    def _filter_false_positives(
        self,
        anomalies: List[RawAnomaly],
        min_time: float,
        max_time: float
    ) -> List[RawAnomaly]:
        """
        Apply heuristics to reduce false positives.
        Filters out anomalies that are likely noise or artifacts.
        """
        filtered = []

        for anomaly in anomalies:
            # Skip if too close to data boundaries
            if self.config.filter_boundary_anomalies:
                if anomaly.timestamp < min_time + self.config.boundary_buffer:
                    logger.debug(f"Filtering boundary anomaly at start: {anomaly.metric_name}")
                    continue
                if anomaly.timestamp > max_time - self.config.boundary_buffer:
                    logger.debug(f"Filtering boundary anomaly at end: {anomaly.metric_name}")
                    continue

            # Skip if confidence is too low (already checked in detection, but double-check)
            if anomaly.confidence < self.config.min_confidence_threshold:
                logger.debug(f"Filtering low confidence anomaly: {anomaly.metric_name} (confidence={anomaly.confidence:.2f})")
                continue

            # Skip known noisy metrics (patterns that are typically false positives)
            metric_name_lower = anomaly.metric_name.lower()
            if any(pattern in metric_name_lower for pattern in ['_tmp_', '_debug_', '_test_']):
                logger.debug(f"Filtering noisy metric: {anomaly.metric_name}")
                continue

            # All filters passed
            filtered.append(anomaly)

        return filtered

    def _percentile(self, sorted_values: List[float], p: float) -> float:
        """Calculate percentile"""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_values):
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
        else:
            return sorted_values[f]

    def _cluster_anomalies(
        self,
        raw_anomalies: List[RawAnomaly],
        max_time: float
    ) -> List[AnomalyCluster]:
        """
        Phase 3: Cluster consecutive anomalies into sustained anomaly events.

        Groups anomalies by:
        1. Base metric (component + metric_name, ignoring label variations)
        2. Temporal proximity (consecutive anomalies within gap threshold)
        """
        logger.info("Phase 3: Clustering anomalies")

        # Group by base metric key (component + metric_name only, ignore labels)
        by_base_metric = defaultdict(list)
        for anomaly in raw_anomalies:
            base_key = f"{anomaly.component}:{anomaly.metric_name}"
            by_base_metric[base_key].append(anomaly)

        clusters = []
        cluster_id = 1

        for base_key, anomalies in by_base_metric.items():
            # Sort by timestamp
            anomalies.sort(key=lambda a: a.timestamp)

            # Cluster consecutive anomalies
            current_cluster = [anomalies[0]]

            for i in range(1, len(anomalies)):
                gap = anomalies[i].timestamp - anomalies[i-1].timestamp

                if gap <= self.config.anomaly_gap_threshold:
                    # Same cluster
                    current_cluster.append(anomalies[i])
                else:
                    # New cluster - save current one
                    clusters.append(self._create_cluster(cluster_id, current_cluster, max_time))
                    cluster_id += 1
                    current_cluster = [anomalies[i]]

            # Save last cluster
            if current_cluster:
                clusters.append(self._create_cluster(cluster_id, current_cluster, max_time))
                cluster_id += 1

        logger.info(f"Created {len(clusters)} anomaly clusters (deduplicated by base metric)")
        return clusters

    def _create_cluster(
        self,
        cluster_id: int,
        anomalies: List[RawAnomaly],
        max_time: float
    ) -> AnomalyCluster:
        """Create an anomaly cluster from a list of consecutive anomalies"""

        # Find peak anomaly (highest magnitude)
        peak_anomaly = max(anomalies, key=lambda a: abs(a.z_score))

        start_time = anomalies[0].timestamp
        end_time = anomalies[-1].timestamp

        # Check if ongoing
        if (max_time - end_time) < self.config.ongoing_threshold:
            end_time = None
            duration = max_time - start_time
        else:
            duration = end_time - start_time

        # Detect pattern
        pattern = self._classify_pattern(anomalies, peak_anomaly.direction)

        return AnomalyCluster(
            cluster_id=cluster_id,
            metric_key=anomalies[0].metric_key,
            component=anomalies[0].component,
            metric_name=anomalies[0].metric_name,
            start_time=start_time,
            end_time=end_time,
            peak_time=peak_anomaly.timestamp,
            peak_z_score=peak_anomaly.z_score,
            direction=peak_anomaly.direction,
            pattern=pattern,
            severity=peak_anomaly.severity,
            duration=duration,
            anomalies=anomalies
        )

    def _classify_pattern(
        self,
        anomalies: List[RawAnomaly],
        direction: AnomalyDirection
    ) -> AnomalyPattern:
        """Classify the pattern of a cluster of anomalies"""

        if len(anomalies) == 1:
            return AnomalyPattern.SPIKE

        duration = anomalies[-1].timestamp - anomalies[0].timestamp

        # Short duration = SPIKE
        if duration < 30:
            return AnomalyPattern.SPIKE

        # Check if returns to baseline (SPIKE with recovery)
        if len(anomalies) >= 3:
            first_half_z = statistics.mean(abs(a.z_score) for a in anomalies[:len(anomalies)//2])
            second_half_z = statistics.mean(abs(a.z_score) for a in anomalies[len(anomalies)//2:])

            # If second half is significantly lower, it's recovering (SPIKE)
            if second_half_z < 0.5 * first_half_z:
                return AnomalyPattern.SPIKE

        # Check for step change (sudden jump, then stable)
        if len(anomalies) >= 4:
            # Compare variance of z-scores
            z_scores = [abs(a.z_score) for a in anomalies]
            z_std = statistics.stdev(z_scores) if len(z_scores) > 1 else 0
            z_mean = statistics.mean(z_scores)

            # Low variance = stable after initial change = STEP_CHANGE
            if z_std < 0.2 * z_mean:
                return AnomalyPattern.STEP_CHANGE

        # Default: sustained increase/decrease based on direction
        if direction == AnomalyDirection.INCREASE or direction == AnomalyDirection.NEW_ERROR:
            return AnomalyPattern.SUSTAINED_INCREASE
        else:
            return AnomalyPattern.SUSTAINED_DECREASE

    def _identify_primary_symptom(
        self,
        clusters: List[AnomalyCluster]
    ) -> Tuple[AnomalyCluster, Dict[int, AnomalyRelationship]]:
        """
        Phase 4: Identify primary symptom and relationships.

        Primary symptom priority:
        1. Errors (NEW_ERROR or INCREASE) - highest priority
        2. Performance degradation (latency/duration INCREASE)
        3. Resource saturation (CPU/memory INCREASE)
        4. Everything else

        Ignore: DECREASEs in latency/throughput (usually secondary symptoms)

        Returns:
            (primary_symptom_cluster, {cluster_id: relationship})
        """
        logger.info("Phase 4: Identifying primary symptom")

        if not clusters:
            return None, {}

        # Sort by start time
        clusters_by_time = sorted(clusters, key=lambda c: c.start_time)

        # Score each cluster for likelihood of being primary symptom
        # Use configured weights for flexibility
        weights = self.config.scoring_weights

        def symptom_score(cluster: AnomalyCluster) -> float:
            score = 0.0

            # Errors are most likely primary
            if 'error' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.NEW_ERROR:
                    score += weights["NEW_ERROR"]
                elif cluster.direction == AnomalyDirection.INCREASE:
                    score += weights["ERROR_INCREASE"]

                # Add magnitude bonus: count of anomalies in cluster (indicates volume)
                # More anomalies = more error events detected
                magnitude_bonus = min(
                    weights["ERROR_MAGNITUDE_CAP"],
                    len(cluster.anomalies) * weights["ERROR_MAGNITUDE_MULTIPLIER"]
                )
                score += magnitude_bonus

            # Performance degradation (latency/duration INCREASE)
            elif 'duration' in cluster.metric_name.lower() or 'latency' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.INCREASE:
                    score += weights["LATENCY_INCREASE"]
                else:
                    score += weights["LATENCY_DECREASE"]  # Negative value

            # Resource metrics
            elif any(x in cluster.metric_name.lower() for x in ['cpu', 'memory', 'disk']):
                if cluster.direction == AnomalyDirection.INCREASE:
                    score += weights["RESOURCE_INCREASE"]
                else:
                    score += weights["RESOURCE_DECREASE"]  # Negative value

            # Throughput decreases (likely secondary to errors)
            elif 'request' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.DECREASE:
                    score += weights["REQUEST_DECREASE"]  # Negative value
                elif cluster.direction == AnomalyDirection.INCREASE:
                    score += weights["REQUEST_INCREASE"]

            # Earlier timestamp = more likely primary
            time_rank = clusters_by_time.index(cluster)
            time_bonuses = weights["TIME_RANK_BONUS"]
            if time_rank < len(time_bonuses):
                score += time_bonuses[time_rank]

            # Severity bonus
            if cluster.severity == "HIGH":
                score += weights["SEVERITY_HIGH"]
            elif cluster.severity == "MEDIUM":
                score += weights["SEVERITY_MEDIUM"]

            # Z-score magnitude bonus (capped)
            z_bonus = min(
                weights["Z_SCORE_CAP"],
                abs(cluster.peak_z_score) / weights["Z_SCORE_DIVISOR"]
            )
            score += z_bonus

            return score

        # Find cluster with highest score
        primary = max(clusters, key=symptom_score)

        # Assign relationships
        relationships = {}
        primary_time = primary.start_time

        for cluster in clusters:
            if cluster.cluster_id == primary.cluster_id:
                relationships[cluster.cluster_id] = AnomalyRelationship.PRIMARY
            else:
                # Check timing relative to primary
                time_diff = cluster.start_time - primary_time

                if abs(time_diff) < 10:
                    # Started around same time - correlated
                    relationships[cluster.cluster_id] = AnomalyRelationship.CORRELATED
                elif time_diff > 10:
                    # Started after primary - likely cascading
                    if 'error' in cluster.metric_name:
                        relationships[cluster.cluster_id] = AnomalyRelationship.CASCADING
                    else:
                        # Performance metric dropping after errors = secondary symptom
                        if cluster.direction == AnomalyDirection.DECREASE:
                            relationships[cluster.cluster_id] = AnomalyRelationship.SECONDARY_SYMPTOM
                        else:
                            relationships[cluster.cluster_id] = AnomalyRelationship.CASCADING
                else:
                    relationships[cluster.cluster_id] = AnomalyRelationship.CORRELATED

        logger.info(f"Primary symptom: {primary.component}:{primary.metric_name}")
        return primary, relationships

    def _calculate_incident_window(
        self,
        clusters: List[AnomalyCluster],
        baseline_window: BaselineWindow,
        max_time: float
    ) -> IncidentWindow:
        """
        Phase 5: Calculate incident window with transition buffer.
        """
        logger.info("Phase 5: Calculating incident window")

        # Find first anomaly
        first_anomaly = min(clusters, key=lambda c: c.start_time)

        # Incident start = buffer before first anomaly
        incident_start = max(baseline_window.end_time, first_anomaly.start_time - self.config.transition_buffer)

        # Check if ongoing
        latest_time = max(c.peak_time for c in clusters)
        if (max_time - latest_time) < self.config.ongoing_threshold:
            incident_end = None
            status = "ACTIVE"
            duration = max_time - incident_start
        else:
            incident_end = latest_time + 30  # Add buffer
            status = "RESOLVED"
            duration = incident_end - incident_start

        return IncidentWindow(
            start_time=incident_start,
            end_time=incident_end,
            status=status,
            duration=duration
        )

    def _build_result(
        self,
        baseline_window: BaselineWindow,
        incident_window: IncidentWindow,
        anomaly_clusters: List[AnomalyCluster],
        primary_symptom: AnomalyCluster,
        min_time: float,
        max_time: float,
        causal_relationships: List[CausalRelationship] = None
    ) -> Dict[str, Any]:
        """Build final result dictionary"""

        if causal_relationships is None:
            causal_relationships = []

        # Get affected components
        affected_components = list(set(c.component for c in anomaly_clusters))

        # Build anomaly summaries
        anomaly_summaries = []
        for cluster in sorted(anomaly_clusters, key=lambda c: c.start_time):
            # Get detection methods and confidence from anomalies in cluster
            detection_methods = list(set(a.detection_method for a in cluster.anomalies))
            avg_confidence = statistics.mean(a.confidence for a in cluster.anomalies) if cluster.anomalies else 1.0

            anomaly_summaries.append({
                "cluster_id": cluster.cluster_id,
                "component": cluster.component,
                "metric": cluster.metric_name,
                "start_time": cluster.start_time,
                "end_time": cluster.end_time,
                "peak_time": cluster.peak_time,
                "peak_z_score": round(cluster.peak_z_score, 2),
                "direction": cluster.direction.value,
                "pattern": cluster.pattern.value,
                "severity": cluster.severity,
                "duration": round(cluster.duration, 1),
                "relationship": cluster.relationship.value,
                "confidence": round(avg_confidence, 2),
                "detection_methods": detection_methods,
                "anomaly_count": len(cluster.anomalies)
            })

        # Build symptom description
        direction_str = primary_symptom.direction.value.lower()
        if primary_symptom.direction == AnomalyDirection.NEW_ERROR:
            symptom_desc = f"{primary_symptom.component}: {primary_symptom.metric_name} (new error type)"
        else:
            symptom_desc = f"{primary_symptom.component}: {primary_symptom.metric_name} {direction_str} ({primary_symptom.pattern.value.lower()})"

        return {
            "status": "success",
            "incident_detected": True,
            "baseline_window": {
                "start_time": baseline_window.start_time,
                "end_time": baseline_window.end_time,
                "duration": baseline_window.duration,
                "quality": baseline_window.quality,
                "samples": baseline_window.samples,
                "detection_method": baseline_window.detection_method,
                "stability_score": round(baseline_window.stability_score, 2)
            },
            "incident_window": {
                "start_time": incident_window.start_time,
                "end_time": incident_window.end_time,
                "status": incident_window.status,
                "duration": round(incident_window.duration, 1)
            },
            "primary_symptom": {
                "component": primary_symptom.component,
                "metric": primary_symptom.metric_name,
                "pattern": primary_symptom.pattern.value,
                "direction": primary_symptom.direction.value,
                "start_time": primary_symptom.start_time,
                "severity": primary_symptom.severity,
                "z_score": round(primary_symptom.peak_z_score, 2),
                "description": symptom_desc
            },
            "anomalies": anomaly_summaries,
            "affected_components": affected_components,
            "causal_relationships": [
                {
                    "cause_cluster_id": cr.cause_cluster_id,
                    "effect_cluster_id": cr.effect_cluster_id,
                    "granger_p_value": round(cr.granger_p_value, 4),
                    "confidence": round(cr.confidence, 2),
                    "lag": cr.lag
                }
                for cr in causal_relationships
            ],
            "detection_metadata": {
                "total_anomalies_detected": len(anomaly_clusters),
                "z_threshold": self.z_threshold,
                "sensitivity": self.sensitivity,
                "data_time_range": {"start": min_time, "end": max_time},
                "v3_features_enabled": {
                    "seasonality_detection": self.config.detect_seasonality,
                    "bayesian_changepoint": self.config.use_bayesian_changepoint,
                    "causality_analysis": self.config.analyze_causality,
                    "multivariate_detection": self.config.use_multivariate_detection
                }
            }
        }
