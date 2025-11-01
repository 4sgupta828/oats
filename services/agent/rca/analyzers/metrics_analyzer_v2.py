"""
Metrics analyzer v2 with automatic baseline detection and accurate anomaly detection.

This is a complete rewrite that:
1. Auto-detects baseline from data (no manual lookback)
2. Single-pass anomaly detection (no duplicates)
3. Direction-aware patterns (INCREASE vs DECREASE)
4. Temporal clustering to deduplicate anomalies
5. Proper symptom identification
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


@dataclass
class IncidentWindow:
    """Detected incident window"""
    start_time: float
    end_time: Optional[float]  # None if ongoing
    status: str  # ACTIVE, RESOLVED
    duration: float


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

    def is_counter(self) -> bool:
        """Check if this is a counter metric"""
        return self.metric_type == "COUNTER"


class MetricsAnalyzerV2:
    """
    New metrics analyzer with automatic baseline detection and accurate anomaly detection.
    """

    def __init__(self, backend: TelemetryBackend, sensitivity: str = "medium"):
        """Initialize analyzer

        Args:
            backend: Telemetry backend
            sensitivity: Detection sensitivity (high, medium, low)
        """
        self.backend = backend
        self.sensitivity = sensitivity

        # Set z-score threshold based on sensitivity
        self.z_threshold = {
            "high": 3.0,
            "medium": 3.5,
            "low": 4.0
        }.get(sensitivity, 3.5)

        # Configuration
        self.min_baseline_duration = 60.0  # seconds
        self.transition_buffer = 30.0  # seconds before first anomaly
        self.anomaly_gap_threshold = 20.0  # max gap to merge into same cluster
        self.ongoing_threshold = 20.0  # if anomaly within Xs of data end → ACTIVE

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
            max_time
        )

    def _detect_baseline(self, min_time: float, max_time: float) -> BaselineWindow:
        """
        Phase 1: Auto-detect baseline using changepoint detection.

        Strategy: Scan backwards from end of data to find stable region.
        """
        logger.info("Phase 1: Detecting baseline window")

        # Get all components
        topology = self.backend.get_topology()
        components = list(topology.get('components', {}).keys())
        if not components:
            components = [None]  # Query all metrics

        # Sample key metrics across components to find changepoints
        all_changepoints = []

        for component in components[:10]:  # Sample first 10 components for efficiency
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
                for metric_name, metric_list in list(by_metric.items())[:5]:  # Top 5 metrics per component
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

        # Validate baseline quality
        if baseline_duration < self.min_baseline_duration:
            quality = "insufficient"
        elif baseline_duration < 120:
            quality = "fair"
        else:
            quality = "good"

        return BaselineWindow(
            start_time=baseline_start,
            end_time=baseline_end,
            duration=baseline_duration,
            quality=quality,
            samples=int(baseline_duration / 10),  # Estimate
            detection_method="ruptures_pelt" if HAS_RUPTURES else "heuristic"
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

                profile = MetricProfile(
                    metric_key=metric_key,
                    component=first_metric.labels.get('component.id', component or 'unknown'),
                    metric_name=first_metric.labels.get('__name__', 'unknown'),
                    metric_type=metric_type,
                    mean=statistics.mean(values),
                    std=statistics.stdev(values) if count > 1 else 0.0,
                    min_val=min(values),
                    max_val=max(values),
                    p50=self._percentile(sorted_values, 0.5),
                    p95=self._percentile(sorted_values, 0.95),
                    p99=self._percentile(sorted_values, 0.99),
                    count=count
                )

                profiles[metric_key] = profile

        return profiles

    def _create_metric_key(self, metric: MetricDataPoint) -> str:
        """Create unique key for a metric (component + name + label signature)"""
        metric_name = metric.labels.get('__name__', 'unknown')
        component_id = metric.labels.get('component.id', 'unknown')

        # Include discriminating labels (but not timestamp-like labels)
        label_parts = []
        for k, v in sorted(metric.labels.items()):
            if k not in ['__name__', 'component.id', 'sim.time', 'timestamp']:
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
            # For gauges, compare mean of values in bucket
            if profile.std == 0:
                return None

            incident_mean = statistics.mean(m.value for m in metrics)
            z_score = (incident_mean - profile.mean) / profile.std

            # Check threshold
            if abs(z_score) >= self.z_threshold:
                direction = AnomalyDirection.INCREASE if z_score > 0 else AnomalyDirection.DECREASE
                severity = self._calculate_severity(abs(z_score))

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
                    severity=severity
                )

        return None

    def _calculate_severity(self, abs_z_score: float) -> str:
        """Calculate severity from absolute z-score"""
        if abs_z_score > 5.0:
            return "HIGH"
        elif abs_z_score > 3.5:
            return "MEDIUM"
        else:
            return "LOW"

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

                if gap <= self.anomaly_gap_threshold:
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
        if (max_time - end_time) < self.ongoing_threshold:
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
        def symptom_score(cluster: AnomalyCluster) -> float:
            score = 0.0

            # Errors are most likely primary
            if 'error' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.NEW_ERROR:
                    score += 1000  # New error = highest priority
                elif cluster.direction == AnomalyDirection.INCREASE:
                    score += 900  # Error increase = very high priority

                # Add magnitude bonus: count of anomalies in cluster (indicates volume)
                # More anomalies = more error events detected
                magnitude_bonus = min(200, len(cluster.anomalies) * 2)  # Cap at 200
                score += magnitude_bonus

            # Performance degradation (latency/duration INCREASE)
            elif 'duration' in cluster.metric_name.lower() or 'latency' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.INCREASE:
                    score += 500  # Latency increase = medium priority
                else:
                    score -= 500  # Latency decrease = likely secondary, deprioritize

            # Resource metrics
            elif any(x in cluster.metric_name.lower() for x in ['cpu', 'memory', 'disk']):
                if cluster.direction == AnomalyDirection.INCREASE:
                    score += 400  # Resource increase = medium priority
                else:
                    score -= 300  # Resource decrease = likely secondary

            # Throughput decreases (likely secondary to errors)
            elif 'request' in cluster.metric_name.lower():
                if cluster.direction == AnomalyDirection.DECREASE:
                    score -= 400  # Request decrease = likely secondary
                elif cluster.direction == AnomalyDirection.INCREASE:
                    score += 100  # Request increase = possible cause

            # Earlier timestamp = more likely primary
            # (first 5 clusters get bonus)
            time_rank = clusters_by_time.index(cluster)
            if time_rank == 0:
                score += 300
            elif time_rank == 1:
                score += 250
            elif time_rank == 2:
                score += 200
            elif time_rank == 3:
                score += 150
            elif time_rank == 4:
                score += 100

            # Severity bonus
            if cluster.severity == "HIGH":
                score += 50
            elif cluster.severity == "MEDIUM":
                score += 20

            # Z-score magnitude bonus (capped)
            z_bonus = min(50, abs(cluster.peak_z_score) / 10)
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
        incident_start = max(baseline_window.end_time, first_anomaly.start_time - self.transition_buffer)

        # Check if ongoing
        latest_time = max(c.peak_time for c in clusters)
        if (max_time - latest_time) < self.ongoing_threshold:
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
        max_time: float
    ) -> Dict[str, Any]:
        """Build final result dictionary"""

        # Get affected components
        affected_components = list(set(c.component for c in anomaly_clusters))

        # Build anomaly summaries
        anomaly_summaries = []
        for cluster in sorted(anomaly_clusters, key=lambda c: c.start_time):
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
                "relationship": cluster.relationship.value
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
                "detection_method": baseline_window.detection_method
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
            "detection_metadata": {
                "total_anomalies_detected": len(anomaly_clusters),
                "z_threshold": self.z_threshold,
                "sensitivity": self.sensitivity,
                "data_time_range": {"start": min_time, "end": max_time}
            }
        }
