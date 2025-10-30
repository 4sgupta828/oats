"""Metrics analyzer with statistical anomaly detection and changepoint analysis"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import statistics
import numpy as np

from rca.backends.base import TelemetryBackend, MetricDataPoint
from core.logging_config import get_logger

logger = get_logger('metrics_analyzer')

# Try to import ruptures for advanced changepoint detection
try:
    import ruptures as rpt
    HAS_RUPTURES = True
    logger.info("Ruptures library available - using advanced changepoint detection")
except ImportError:
    HAS_RUPTURES = False
    logger.info("Ruptures library not available - using heuristic changepoint detection")


@dataclass
class Anomaly:
    """Detected anomaly in a metric"""
    metric_name: str
    component: str
    timestamp: float
    value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    pattern: str  # SPIKE, STEP_CHANGE, SUSTAINED_INCREASE, GRADUAL_DRIFT, NORMAL
    severity: str  # HIGH, MEDIUM, LOW
    delta_percent: float


@dataclass
class MetricStats:
    """Statistical summary of a metric"""
    mean: float
    std: float
    min: float
    max: float
    p50: float
    p95: float
    p99: float
    count: int


class MetricsAnalyzer:
    """Analyzer for detecting anomalies in metrics"""

    def __init__(self, backend: TelemetryBackend):
        """Initialize metrics analyzer

        Args:
            backend: Telemetry backend for querying metrics
        """
        self.backend = backend

    def detect_anomalies(
        self,
        component: str,
        baseline_range: Tuple[float, float],
        incident_range: Tuple[float, Optional[float]],
        metric_pattern: str = "*"
    ) -> List[Anomaly]:
        """Detect anomalies by comparing incident metrics to baseline

        Args:
            component: Component name to analyze
            baseline_range: (start, end) for baseline period
            incident_range: (start, end) for incident period (end can be None)
            metric_pattern: Metric name pattern to match

        Returns:
            List of detected anomalies
        """
        anomalies = []

        # Query metrics for both periods
        baseline_metrics = self.backend.query_metrics(component, metric_pattern, baseline_range)
        incident_metrics = self.backend.query_metrics(component, metric_pattern, incident_range)

        # Group by metric name
        baseline_by_metric = self._group_by_metric_name(baseline_metrics)
        incident_by_metric = self._group_by_metric_name(incident_metrics)

        # Analyze each metric
        for metric_name in incident_by_metric.keys():
            # Get baseline and incident values (baseline might be empty for new error types)
            baseline_values = [m.value for m in baseline_by_metric.get(metric_name, [])]
            incident_values = [m.value for m in incident_by_metric[metric_name]]

            # Calculate baseline statistics (will be zeros if no baseline data)
            baseline_stats = self._calculate_stats(baseline_values)

            # Check if this is a counter-type metric (all values are the same, typically 1)
            # For counters, compare aggregated sums instead of individual values
            is_counter_metric = (baseline_stats.std == 0 or
                                (baseline_stats.std < 0.01 * abs(baseline_stats.mean)) and
                                baseline_stats.mean <= 1.0)


            if is_counter_metric:
                # For counter metrics, compare the SUM (total events) in each window
                baseline_sum = sum(baseline_values)
                incident_sum = sum(incident_values)

                # Handle new errors that didn't exist in baseline
                if baseline_sum == 0:
                    # If there are incident events but no baseline, this is a new error type
                    # Assign very high z-score to flag as critical anomaly
                    if incident_sum > 0:
                        z_score = 10.0  # Arbitrarily high z-score for new error types
                        baseline_mean_rate = 0
                        baseline_std_rate = 1.0
                    else:
                        # Both zero, skip
                        logger.debug(f"  SKIPPED: both baseline and incident are zero")
                        continue
                else:
                    # Use Poisson approximation for z-score
                    # For count data, variance ≈ mean (Poisson distribution)
                    baseline_mean_rate = baseline_sum
                    baseline_std_rate = max(1.0, baseline_sum ** 0.5)  # sqrt(count) for Poisson

                    z_score = (incident_sum - baseline_mean_rate) / baseline_std_rate

                # Store aggregated values for reporting
                baseline_stats = MetricStats(
                    mean=baseline_sum,
                    std=baseline_std_rate,
                    min=baseline_sum,
                    max=baseline_sum,
                    p50=baseline_sum,
                    p95=baseline_sum,
                    p99=baseline_sum,
                    count=len(baseline_values)
                )
                incident_stats = MetricStats(
                    mean=incident_sum,
                    std=0,
                    min=incident_sum,
                    max=incident_sum,
                    p50=incident_sum,
                    p95=incident_sum,
                    p99=incident_sum,
                    count=len(incident_values)
                )
            else:
                # For gauge metrics, compare means
                if baseline_stats.std == 0:
                    # No variation in baseline, skip
                    continue

                # Calculate incident statistics
                incident_stats = self._calculate_stats(incident_values)

                # Calculate z-score for incident mean
                z_score = (incident_stats.mean - baseline_stats.mean) / baseline_stats.std

            # Only flag significant anomalies (|z| > 3.0)
            if abs(z_score) > 3.0:
                # Calculate percentage change
                if baseline_stats.mean != 0:
                    delta_percent = ((incident_stats.mean - baseline_stats.mean) / abs(baseline_stats.mean)) * 100
                else:
                    delta_percent = float('inf') if incident_stats.mean > 0 else 0.0

                # Detect pattern
                pattern = self._detect_pattern(
                    baseline_by_metric.get(metric_name, []),
                    incident_by_metric[metric_name]
                )

                # Determine severity
                severity = self._determine_severity(abs(z_score))

                # Get first incident timestamp
                first_incident_time = min(m.timestamp for m in incident_by_metric[metric_name])

                anomalies.append(Anomaly(
                    metric_name=metric_name,
                    component=component,
                    timestamp=first_incident_time,
                    value=incident_stats.mean,
                    baseline_mean=baseline_stats.mean,
                    baseline_std=baseline_stats.std,
                    z_score=z_score,
                    pattern=pattern,
                    severity=severity,
                    delta_percent=delta_percent
                ))

        logger.info(f"Detected {len(anomalies)} anomalies for component {component}")
        return anomalies

    def _group_by_metric_name(self, metrics: List[MetricDataPoint]) -> Dict[str, List[MetricDataPoint]]:
        """Group metrics by name"""
        grouped = defaultdict(list)
        for m in metrics:
            metric_name = m.labels.get('__name__', m.labels.get('name', 'unknown'))
            grouped[metric_name].append(m)
        return dict(grouped)

    def _calculate_stats(self, values: List[float]) -> MetricStats:
        """Calculate statistical summary of values"""
        if not values:
            return MetricStats(0, 0, 0, 0, 0, 0, 0, 0)

        sorted_values = sorted(values)
        count = len(values)

        return MetricStats(
            mean=statistics.mean(values),
            std=statistics.stdev(values) if count > 1 else 0.0,
            min=min(values),
            max=max(values),
            p50=self._percentile(sorted_values, 0.50),
            p95=self._percentile(sorted_values, 0.95),
            p99=self._percentile(sorted_values, 0.99),
            count=count
        )

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

    def _detect_pattern(
        self,
        baseline_metrics: List[MetricDataPoint],
        incident_metrics: List[MetricDataPoint]
    ) -> str:
        """Detect anomaly pattern using ruptures changepoint detection or heuristics

        Uses ruptures library if available for accurate changepoint detection,
        otherwise falls back to heuristic-based pattern detection.
        """
        if not incident_metrics:
            return "NORMAL"

        # Sort by timestamp
        incident_metrics = sorted(incident_metrics, key=lambda m: m.timestamp)

        # Calculate duration of incident
        duration = incident_metrics[-1].timestamp - incident_metrics[0].timestamp

        # Calculate values
        incident_values = [m.value for m in incident_metrics]

        # Short duration (<30s) = SPIKE
        if duration < 30:
            return "SPIKE"

        # Use ruptures if available
        if HAS_RUPTURES and len(incident_values) >= 10:
            return self._detect_pattern_ruptures(baseline_metrics, incident_metrics)
        else:
            return self._detect_pattern_heuristic(incident_values)

    def _detect_pattern_ruptures(
        self,
        baseline_metrics: List[MetricDataPoint],
        incident_metrics: List[MetricDataPoint]
    ) -> str:
        """Detect pattern using ruptures changepoint detection library"""
        try:
            # Combine baseline and incident for better detection
            all_metrics = sorted(baseline_metrics + incident_metrics, key=lambda m: m.timestamp)
            signal = np.array([m.value for m in all_metrics])

            # Normalize signal for better detection
            signal_mean = np.mean(signal)
            signal_std = np.std(signal)
            if signal_std > 0:
                signal = (signal - signal_mean) / signal_std

            # Use Pelt algorithm with RBF kernel (detects mean shifts)
            algo = rpt.Pelt(model="rbf", min_size=3, jump=1)
            algo.fit(signal)

            # Detect changepoints with penalty tuning
            # Lower penalty = more sensitive to changes
            changepoints = algo.predict(pen=10)

            # Analyze changepoint pattern
            n_changepoints = len(changepoints) - 1  # Last point is always end of signal

            baseline_len = len(baseline_metrics)
            incident_len = len(incident_metrics)

            if n_changepoints == 0:
                # No changepoints detected in combined signal
                return "SUSTAINED_INCREASE"

            elif n_changepoints == 1:
                # Single changepoint - likely STEP_CHANGE
                cp_idx = changepoints[0]
                # Check if changepoint is near baseline/incident boundary
                if abs(cp_idx - baseline_len) < 5:  # Within 5 samples of boundary
                    return "STEP_CHANGE"
                else:
                    return "SUSTAINED_INCREASE"

            elif n_changepoints == 2:
                # Two changepoints - could be SPIKE or SUSTAINED_INCREASE
                cp1, cp2 = changepoints[0], changepoints[1]
                # If both in incident window and close together = SPIKE
                if cp1 >= baseline_len and cp2 >= baseline_len and (cp2 - cp1) < 10:
                    return "SPIKE"
                else:
                    return "SUSTAINED_INCREASE"

            else:  # n_changepoints > 2
                # Multiple changepoints = GRADUAL_DRIFT
                return "GRADUAL_DRIFT"

        except Exception as e:
            logger.debug(f"Ruptures changepoint detection failed: {e}, falling back to heuristics")
            return self._detect_pattern_heuristic([m.value for m in incident_metrics])

    def _detect_pattern_heuristic(self, incident_values: List[float]) -> str:
        """Fallback heuristic-based pattern detection"""
        if len(incident_values) < 2:
            return "NORMAL"

        first_half = incident_values[:len(incident_values)//2]
        second_half = incident_values[len(incident_values)//2:]

        # Check if values are stable in second half (STEP_CHANGE)
        if len(second_half) > 2:
            second_half_std = statistics.stdev(second_half)
            second_half_mean = statistics.mean(second_half)

            # If stable in second half
            if second_half_std < 0.1 * abs(second_half_mean):
                # Check if first half transitioned
                if len(first_half) > 2:
                    first_half_mean = statistics.mean(first_half)
                    # If means are different = STEP_CHANGE
                    if abs(second_half_mean - first_half_mean) > second_half_std:
                        return "STEP_CHANGE"

                return "SUSTAINED_INCREASE"

        # Check for gradual trend
        if len(incident_values) > 5:
            # Simple linear trend detection
            mid_point = len(incident_values) // 2
            first_quarter_mean = statistics.mean(incident_values[:mid_point//2])
            last_quarter_mean = statistics.mean(incident_values[-mid_point//2:])

            if abs(last_quarter_mean - first_quarter_mean) > 0.5 * statistics.stdev(incident_values):
                return "GRADUAL_DRIFT"

        return "SUSTAINED_INCREASE"

    def _determine_severity(self, z_score: float) -> str:
        """Determine severity based on z-score"""
        if z_score > 5.0:
            return "HIGH"
        elif z_score > 3.5:
            return "MEDIUM"
        else:
            return "LOW"

    def compare_metrics(
        self,
        component: str,
        baseline_range: Tuple[float, float],
        incident_range: Tuple[float, Optional[float]],
        metric_pattern: str = "*"
    ) -> Dict[str, Any]:
        """Compare metrics between baseline and incident periods

        This is the main entry point for the compare_metrics RCA tool.

        Returns:
            Dictionary with anomalous metrics and statistics
        """
        anomalies = self.detect_anomalies(component, baseline_range, incident_range, metric_pattern)

        # Sort by z-score (most anomalous first)
        anomalies.sort(key=lambda a: abs(a.z_score), reverse=True)

        # Format results
        anomalous_metrics = []
        for anomaly in anomalies:
            anomalous_metrics.append({
                "metric_name": anomaly.metric_name,
                "baseline_mean": round(anomaly.baseline_mean, 3),
                "baseline_std": round(anomaly.baseline_std, 3),
                "incident_mean": round(anomaly.value, 3),
                "delta_percent": round(anomaly.delta_percent, 1),
                "z_score": round(anomaly.z_score, 2),
                "p_value": self._z_to_p_value(anomaly.z_score),
                "anomaly_pattern": anomaly.pattern,
                "changepoint_time": anomaly.timestamp,
                "severity": anomaly.severity,
                "statistical_significance": self._format_significance(anomaly.z_score)
            })

        return {
            "status": "success",
            "component": component,
            "anomalous_metrics": anomalous_metrics,
            "total_metrics_analyzed": len(anomalies),
            "baseline_range": baseline_range,
            "incident_range": incident_range
        }

    def _z_to_p_value(self, z_score: float) -> float:
        """Convert z-score to approximate p-value"""
        # For |z| > 3, p-value is very small
        if abs(z_score) > 4:
            return 0.0001
        elif abs(z_score) > 3:
            return 0.001
        elif abs(z_score) > 2:
            return 0.05
        else:
            return 0.1

    def _format_significance(self, z_score: float) -> str:
        """Format statistical significance"""
        if abs(z_score) > 4:
            return "p<0.0001"
        elif abs(z_score) > 3:
            return "p<0.001"
        elif abs(z_score) > 2:
            return "p<0.05"
        else:
            return "p<0.1"
