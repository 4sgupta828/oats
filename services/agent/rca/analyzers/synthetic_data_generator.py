"""
Synthetic data generator for stress-testing metrics analyzers.

Creates challenging scenarios:
1. Multiple concurrent anomalies
2. Skewed distributions (log-normal, exponential)
3. High noise levels
4. Noisy baselines
5. Hard false positives (brief spikes, outliers)
6. Seasonal patterns
7. Cascading failures
8. Correlated anomalies
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import time

from core.logging_config import get_logger

logger = get_logger('synthetic_data_generator')


@dataclass
class MetricConfig:
    """Configuration for a synthetic metric"""
    name: str
    component: str
    baseline_mean: float
    baseline_std: float
    distribution: str  # "normal", "log_normal", "exponential", "poisson"
    has_seasonality: bool = False
    seasonal_period: float = 60.0  # seconds
    seasonal_amplitude: float = 0.0
    noise_level: float = 0.1  # 0-1, higher = more noise


@dataclass
class AnomalyInjection:
    """Configuration for injecting an anomaly"""
    metric_name: str
    component: str
    start_time: float
    duration: float
    magnitude: float  # multiplier or additive change
    pattern: str  # "spike", "step", "gradual", "oscillating"
    is_false_positive: bool = False


class SyntheticDataGenerator:
    """Generate synthetic telemetry data with controlled anomalies"""

    def __init__(self, output_dir: str, duration: float = 600.0, interval: float = 5.0):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.duration = duration
        self.interval = interval
        self.num_points = int(duration / interval)
        self.timestamps = np.arange(0, duration, interval)

    def generate_baseline_values(
        self,
        config: MetricConfig,
        num_points: int
    ) -> np.ndarray:
        """Generate baseline time series based on distribution"""

        if config.distribution == "normal":
            values = np.random.normal(config.baseline_mean, config.baseline_std, num_points)

        elif config.distribution == "log_normal":
            # Log-normal: heavy right tail (common for latencies)
            mu = np.log(config.baseline_mean)
            sigma = config.baseline_std / config.baseline_mean
            values = np.random.lognormal(mu, sigma, num_points)

        elif config.distribution == "exponential":
            # Exponential: used for inter-arrival times
            values = np.random.exponential(config.baseline_mean, num_points)

        elif config.distribution == "poisson":
            # Poisson: used for count data (errors, requests)
            values = np.random.poisson(config.baseline_mean, num_points).astype(float)

        else:
            raise ValueError(f"Unknown distribution: {config.distribution}")

        # Add seasonality if configured
        if config.has_seasonality:
            t = self.timestamps[:num_points]
            seasonal_component = config.seasonal_amplitude * np.sin(
                2 * np.pi * t / config.seasonal_period
            )
            values += seasonal_component

        # Add noise
        if config.noise_level > 0:
            noise = np.random.normal(0, config.noise_level * config.baseline_std, num_points)
            values += noise

        # Ensure non-negative for count/latency metrics
        if config.distribution in ["exponential", "poisson", "log_normal"]:
            values = np.maximum(values, 0)

        return values

    def inject_anomaly(
        self,
        values: np.ndarray,
        timestamps: np.ndarray,
        injection: AnomalyInjection
    ) -> np.ndarray:
        """Inject an anomaly into the time series"""

        # Find start and end indices
        start_idx = np.searchsorted(timestamps, injection.start_time)
        end_idx = np.searchsorted(timestamps, injection.start_time + injection.duration)

        if start_idx >= len(values):
            return values

        end_idx = min(end_idx, len(values))
        duration_points = end_idx - start_idx

        if duration_points == 0:
            return values

        modified_values = values.copy()

        if injection.pattern == "spike":
            # Sharp spike that decays
            decay = np.exp(-np.linspace(0, 3, duration_points))
            modified_values[start_idx:end_idx] *= (1 + injection.magnitude * decay)

        elif injection.pattern == "step":
            # Step change (sustained)
            modified_values[start_idx:end_idx] *= (1 + injection.magnitude)

        elif injection.pattern == "gradual":
            # Gradual increase then plateau
            ramp = np.linspace(0, 1, duration_points // 2)
            plateau = np.ones(duration_points - len(ramp))
            change = np.concatenate([ramp, plateau])
            modified_values[start_idx:end_idx] *= (1 + injection.magnitude * change)

        elif injection.pattern == "oscillating":
            # Oscillating anomaly
            t = np.linspace(0, 4 * np.pi, duration_points)
            oscillation = 0.5 * (1 + np.sin(t))
            modified_values[start_idx:end_idx] *= (1 + injection.magnitude * oscillation)

        return modified_values

    def generate_topology(self, components: List[str]) -> Dict:
        """Generate topology JSON"""
        return {
            "components": {
                comp: {
                    "type": "service",
                    "id": comp
                }
                for comp in components
            }
        }

    def generate_scenario(
        self,
        scenario_name: str,
        metrics: List[MetricConfig],
        anomalies: List[AnomalyInjection]
    ) -> Path:
        """Generate a complete test scenario"""

        logger.info(f"Generating scenario: {scenario_name}")
        logger.info(f"  Metrics: {len(metrics)}")
        logger.info(f"  Anomalies: {len(anomalies)}")
        logger.info(f"  Duration: {self.duration}s")

        scenario_dir = self.output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Generate base timestamp
        base_timestamp = time.time()

        # Generate metrics
        all_metrics = []

        for metric_config in metrics:
            # Generate baseline values
            values = self.generate_baseline_values(metric_config, self.num_points)

            # Inject anomalies for this metric
            for injection in anomalies:
                if (injection.metric_name == metric_config.name and
                    injection.component == metric_config.component):
                    values = self.inject_anomaly(values, self.timestamps, injection)

            # Convert to metric data points
            for i, (t, v) in enumerate(zip(self.timestamps, values)):
                all_metrics.append({
                    "timestamp": base_timestamp + t,
                    "value": float(v),
                    "labels": {
                        "__name__": metric_config.name,
                        "component.id": metric_config.component,
                        "sim.time": base_timestamp + t
                    }
                })

        # Write metrics.jsonl
        metrics_file = scenario_dir / "metrics.jsonl"
        with open(metrics_file, 'w') as f:
            for metric in all_metrics:
                f.write(json.dumps(metric) + '\n')

        logger.info(f"  Wrote {len(all_metrics)} metric points to {metrics_file}")

        # Write topology.json
        components = list(set(m.component for m in metrics))
        topology = self.generate_topology(components)
        topology_file = scenario_dir / "topology.json"
        with open(topology_file, 'w') as f:
            json.dump(topology, f, indent=2)

        logger.info(f"  Wrote topology to {topology_file}")

        # Write scenario metadata
        metadata = {
            "name": scenario_name,
            "duration": self.duration,
            "interval": self.interval,
            "num_metrics": len(metrics),
            "num_anomalies": len(anomalies),
            "true_anomalies": [
                {
                    "metric": a.metric_name,
                    "component": a.component,
                    "start_time": a.start_time,
                    "duration": a.duration,
                    "pattern": a.pattern,
                    "magnitude": a.magnitude,
                    "is_false_positive": a.is_false_positive
                }
                for a in anomalies
            ],
            "metrics_config": [
                {
                    "name": m.name,
                    "component": m.component,
                    "distribution": m.distribution,
                    "baseline_mean": m.baseline_mean,
                    "baseline_std": m.baseline_std,
                    "has_seasonality": m.has_seasonality,
                    "noise_level": m.noise_level
                }
                for m in metrics
            ]
        }

        metadata_file = scenario_dir / "scenario_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"  Wrote metadata to {metadata_file}")
        logger.info(f"Scenario complete: {scenario_dir}\n")

        return scenario_dir


def create_challenging_scenarios():
    """Create a suite of challenging test scenarios"""

    base_output = "/Users/sgupta/oats/services/agent/rca/analyzers/test_data"

    # Scenario 1: Multiple Concurrent Anomalies
    logger.info("=" * 80)
    logger.info("SCENARIO 1: Multiple Concurrent Anomalies")
    logger.info("=" * 80)

    gen1 = SyntheticDataGenerator(base_output, duration=300.0, interval=5.0)

    metrics1 = [
        MetricConfig("http.server.request.duration", "frontend", 100, 20, "log_normal", noise_level=0.2),
        MetricConfig("http.server.error.count", "frontend", 5, 2, "poisson", noise_level=0.3),
        MetricConfig("db.query.duration", "database", 50, 15, "log_normal", noise_level=0.15),
        MetricConfig("cpu.usage", "backend", 40, 8, "normal", noise_level=0.1),
        MetricConfig("memory.usage", "backend", 60, 10, "normal", noise_level=0.1),
    ]

    anomalies1 = [
        # Primary: Error spike in frontend (t=120)
        AnomalyInjection("http.server.error.count", "frontend", 120, 60, 5.0, "step"),
        # Cascading: Latency increase (t=125)
        AnomalyInjection("http.server.request.duration", "frontend", 125, 55, 2.0, "gradual"),
        # Cascading: DB slowdown (t=130)
        AnomalyInjection("db.query.duration", "database", 130, 50, 1.5, "step"),
        # Resource saturation (t=135)
        AnomalyInjection("cpu.usage", "backend", 135, 45, 0.8, "gradual"),
    ]

    gen1.generate_scenario("scenario1_multiple_concurrent", metrics1, anomalies1)

    # Scenario 2: Heavily Skewed Distributions + Noise
    logger.info("=" * 80)
    logger.info("SCENARIO 2: Heavily Skewed Distributions + High Noise")
    logger.info("=" * 80)

    gen2 = SyntheticDataGenerator(base_output, duration=500.0, interval=5.0)

    metrics2 = [
        # P99 latency - very skewed
        MetricConfig("http.p99.duration", "api", 500, 200, "log_normal", noise_level=0.3),
        MetricConfig("http.p50.duration", "api", 50, 10, "log_normal", noise_level=0.2),
        # Bursty errors
        MetricConfig("error.rate", "api", 1, 0.5, "poisson", noise_level=0.4),
        # Exponential inter-arrival times
        MetricConfig("request.interarrival", "api", 10, 5, "exponential", noise_level=0.2),
    ]

    anomalies2 = [
        # Subtle p99 increase that affects mean less - starts at 66% through
        AnomalyInjection("http.p99.duration", "api", 330, 60, 3.0, "step"),
        # Brief error bursts (false positive candidates) - well before real anomaly
        AnomalyInjection("error.rate", "api", 180, 10, 2.0, "spike", is_false_positive=True),
        AnomalyInjection("error.rate", "api", 280, 8, 1.5, "spike", is_false_positive=True),
    ]

    gen2.generate_scenario("scenario2_skewed_noisy", metrics2, anomalies2)

    # Scenario 3: Noisy Baseline + Hard False Positives
    logger.info("=" * 80)
    logger.info("SCENARIO 3: Noisy Baseline + Hard False Positives")
    logger.info("=" * 80)

    gen3 = SyntheticDataGenerator(base_output, duration=600.0, interval=5.0)

    metrics3 = [
        # Moderately noisy baseline (reduced from very noisy)
        MetricConfig("queue.depth", "service", 100, 60, "normal", noise_level=0.4),
        MetricConfig("retry.count", "service", 10, 8, "poisson", noise_level=0.5),
        # Stable metric for contrast - this will be the true anomaly signal
        MetricConfig("success.rate", "service", 0.99, 0.005, "normal", noise_level=0.03),
    ]

    anomalies3 = [
        # Real anomaly: success rate drop - starts at 66% through with clear signal
        AnomalyInjection("success.rate", "service", 400, 80, -0.15, "step"),
        # False positives: brief spikes in noisy metrics - well before real anomaly
        AnomalyInjection("queue.depth", "service", 150, 5, 2.0, "spike", is_false_positive=True),
        AnomalyInjection("queue.depth", "service", 250, 5, 1.8, "spike", is_false_positive=True),
        AnomalyInjection("retry.count", "service", 200, 10, 3.0, "spike", is_false_positive=True),
    ]

    gen3.generate_scenario("scenario3_noisy_baseline_fps", metrics3, anomalies3)

    # Scenario 4: Seasonal Pattern + Anomaly
    logger.info("=" * 80)
    logger.info("SCENARIO 4: Seasonal Pattern + Anomaly")
    logger.info("=" * 80)

    # Longer duration to capture full seasonal cycles + clean baseline
    gen4 = SyntheticDataGenerator(base_output, duration=900.0, interval=5.0)

    metrics4 = [
        # Daily pattern (simulated as 2-minute cycle for testing)
        MetricConfig("request.rate", "lb", 1000, 100, "normal",
                    has_seasonality=True, seasonal_period=120.0, seasonal_amplitude=300,
                    noise_level=0.1),
        MetricConfig("latency", "lb", 80, 15, "log_normal",
                    has_seasonality=True, seasonal_period=120.0, seasonal_amplitude=20,
                    noise_level=0.2),
    ]

    anomalies4 = [
        # Anomaly starts at 600s (66% through) to allow clean baseline
        # Anomaly overlapping with seasonal peak (harder to detect)
        AnomalyInjection("latency", "lb", 600, 120, 2.5, "step"),
    ]

    gen4.generate_scenario("scenario4_seasonal", metrics4, anomalies4)

    # Scenario 5: Cascading Failure Chain
    logger.info("=" * 80)
    logger.info("SCENARIO 5: Cascading Failure Chain (Causality Test)")
    logger.info("=" * 80)

    gen5 = SyntheticDataGenerator(base_output, duration=400.0, interval=5.0)

    metrics5 = [
        MetricConfig("db.connection.errors", "database", 0, 0.1, "poisson", noise_level=0.3),
        MetricConfig("service.errors", "backend", 1, 0.5, "poisson", noise_level=0.2),
        MetricConfig("api.errors", "frontend", 2, 1, "poisson", noise_level=0.2),
        MetricConfig("user.errors", "client", 3, 1.5, "poisson", noise_level=0.2),
    ]

    anomalies5 = [
        # Cascading chain with 10-second delays
        AnomalyInjection("db.connection.errors", "database", 150, 100, 10.0, "step"),  # Root cause
        AnomalyInjection("service.errors", "backend", 160, 90, 8.0, "step"),  # t+10s
        AnomalyInjection("api.errors", "frontend", 170, 80, 6.0, "step"),  # t+20s
        AnomalyInjection("user.errors", "client", 180, 70, 4.0, "step"),  # t+30s
    ]

    gen5.generate_scenario("scenario5_cascading_chain", metrics5, anomalies5)

    # Scenario 6: Edge Cases
    logger.info("=" * 80)
    logger.info("SCENARIO 6: Edge Cases (Zero Baseline, Extreme Values)")
    logger.info("=" * 80)

    gen6 = SyntheticDataGenerator(base_output, duration=400.0, interval=5.0)

    metrics6 = [
        # Near-zero baseline (new error type) - increase slightly to avoid division issues
        MetricConfig("rare.error", "service", 0.1, 0.05, "poisson", noise_level=0.2),
        # Very low baseline but detectable
        MetricConfig("critical.error", "service", 0.5, 0.2, "poisson", noise_level=0.2),
        # Normal metric for comparison
        MetricConfig("normal.metric", "service", 100, 10, "normal", noise_level=0.1),
    ]

    anomalies6 = [
        # New error appears - large magnitude, sustained
        AnomalyInjection("rare.error", "service", 220, 80, 50.0, "step"),  # 0.1 -> 5+
        # Critical error spike - clear signal
        AnomalyInjection("critical.error", "service", 225, 75, 30.0, "step"),  # 0.5 -> 15+
        # Brief outlier (false positive candidate)
        AnomalyInjection("normal.metric", "service", 100, 5, 8.0, "spike", is_false_positive=True),
    ]

    gen6.generate_scenario("scenario6_edge_cases", metrics6, anomalies6)

    logger.info("=" * 80)
    logger.info("All scenarios generated successfully!")
    logger.info(f"Output directory: {base_output}")
    logger.info("=" * 80)


if __name__ == "__main__":
    create_challenging_scenarios()
