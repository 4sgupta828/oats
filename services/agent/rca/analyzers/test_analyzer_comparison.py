"""
Comparison tests for MetricsAnalyzerV2 vs MetricsAnalyzerV3

This test suite compares the performance and capabilities of v2 and v3 analyzers.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List
import statistics

from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer_v2 import MetricsAnalyzerV2, AnalyzerConfig as ConfigV2
from rca.analyzers.metrics_analyzer_v3 import MetricsAnalyzerV3, AnalyzerConfig as ConfigV3
from core.logging_config import get_logger

logger = get_logger('analyzer_comparison_tests')


class AnalyzerComparison:
    """Compare v2 and v3 analyzers"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.backend = SimulationBackend(data_dir)

    def run_v2_analysis(self, config: ConfigV2 = None) -> Dict[str, Any]:
        """Run v2 analyzer with given config"""
        if config is None:
            config = ConfigV2(
                sensitivity="medium",
                use_mad_for_skewed=True,
                use_adaptive_thresholds=True,
                min_confidence_threshold=0.5,
                validate_baseline_stability=True,
                filter_boundary_anomalies=True
            )

        analyzer = MetricsAnalyzerV2(self.backend, config=config)

        start_time = time.time()
        result = analyzer.detect_incident_and_baseline()
        elapsed_time = time.time() - start_time

        return {
            "version": "v2",
            "result": result,
            "execution_time": elapsed_time,
            "config": {
                "sensitivity": config.sensitivity,
                "use_mad": config.use_mad_for_skewed,
                "adaptive_thresholds": config.use_adaptive_thresholds,
                "baseline_validation": config.validate_baseline_stability
            }
        }

    def run_v3_analysis(self, config: ConfigV3 = None) -> Dict[str, Any]:
        """Run v3 analyzer with given config"""
        if config is None:
            config = ConfigV3(
                sensitivity="medium",
                # V2 features
                use_mad_for_skewed=True,
                use_adaptive_thresholds=True,
                min_confidence_threshold=0.5,
                validate_baseline_stability=True,
                filter_boundary_anomalies=True,
                # V3 features
                detect_seasonality=True,
                use_bayesian_changepoint=False,  # Disable for fair comparison
                analyze_causality=True,
                use_multivariate_detection=True,
                multivariate_contamination=0.1
            )

        analyzer = MetricsAnalyzerV3(self.backend, config=config)

        start_time = time.time()
        result = analyzer.detect_incident_and_baseline()
        elapsed_time = time.time() - start_time

        return {
            "version": "v3",
            "result": result,
            "execution_time": elapsed_time,
            "config": {
                "sensitivity": config.sensitivity,
                "use_mad": config.use_mad_for_skewed,
                "adaptive_thresholds": config.use_adaptive_thresholds,
                "baseline_validation": config.validate_baseline_stability,
                "seasonality": config.detect_seasonality,
                "causality": config.analyze_causality,
                "multivariate": config.use_multivariate_detection
            }
        }

    def compare_results(self, v2_analysis: Dict, v3_analysis: Dict) -> Dict[str, Any]:
        """Compare v2 and v3 results"""
        v2_result = v2_analysis["result"]
        v3_result = v3_analysis["result"]

        comparison = {
            "execution_time": {
                "v2": round(v2_analysis["execution_time"], 3),
                "v3": round(v3_analysis["execution_time"], 3),
                "difference": round(v3_analysis["execution_time"] - v2_analysis["execution_time"], 3),
                "v3_overhead_pct": round((v3_analysis["execution_time"] / v2_analysis["execution_time"] - 1) * 100, 1) if v2_analysis["execution_time"] > 0 else 0
            },
            "incident_detected": {
                "v2": v2_result.get("incident_detected", False),
                "v3": v3_result.get("incident_detected", False),
                "match": v2_result.get("incident_detected") == v3_result.get("incident_detected")
            },
            "anomalies_detected": {
                "v2": len(v2_result.get("anomalies", [])),
                "v3": len(v3_result.get("anomalies", [])),
                "difference": len(v3_result.get("anomalies", [])) - len(v2_result.get("anomalies", []))
            },
            "baseline_quality": {
                "v2": v2_result.get("baseline_window", {}).get("quality", "unknown"),
                "v3": v3_result.get("baseline_window", {}).get("quality", "unknown")
            },
            "baseline_stability": {
                "v2": v2_result.get("baseline_window", {}).get("stability_score", 0),
                "v3": v3_result.get("baseline_window", {}).get("stability_score", 0)
            }
        }

        # Compare primary symptoms
        v2_symptom = v2_result.get("primary_symptom", {})
        v3_symptom = v3_result.get("primary_symptom", {})

        comparison["primary_symptom"] = {
            "v2": f"{v2_symptom.get('component')}:{v2_symptom.get('metric')}",
            "v3": f"{v3_symptom.get('component')}:{v3_symptom.get('metric')}",
            "match": (v2_symptom.get('component') == v3_symptom.get('component') and
                     v2_symptom.get('metric') == v3_symptom.get('metric')),
            "v2_severity": v2_symptom.get('severity'),
            "v3_severity": v3_symptom.get('severity')
        }

        # V3-specific features
        comparison["v3_features"] = {
            "causal_relationships_found": len(v3_result.get("causal_relationships", [])),
            "causal_relationships": v3_result.get("causal_relationships", [])
        }

        # Calculate confidence scores
        v2_confidences = [a.get("confidence", 1.0) for a in v2_result.get("anomalies", [])]
        v3_confidences = [a.get("confidence", 1.0) for a in v3_result.get("anomalies", [])]

        if v2_confidences:
            comparison["confidence_scores"] = {
                "v2_avg": round(statistics.mean(v2_confidences), 2),
                "v2_min": round(min(v2_confidences), 2),
                "v2_max": round(max(v2_confidences), 2)
            }

        if v3_confidences:
            comparison["confidence_scores"]["v3_avg"] = round(statistics.mean(v3_confidences), 2)
            comparison["confidence_scores"]["v3_min"] = round(min(v3_confidences), 2)
            comparison["confidence_scores"]["v3_max"] = round(max(v3_confidences), 2)

        # Detection methods used
        v2_methods = set()
        v3_methods = set()

        for anomaly in v2_result.get("anomalies", []):
            for method in anomaly.get("detection_methods", []):
                v2_methods.add(method)

        for anomaly in v3_result.get("anomalies", []):
            for method in anomaly.get("detection_methods", []):
                v3_methods.add(method)

        comparison["detection_methods"] = {
            "v2": list(v2_methods),
            "v3": list(v3_methods)
        }

        return comparison

    def generate_report(self, comparison: Dict[str, Any]) -> str:
        """Generate a human-readable comparison report"""
        report = []
        report.append("=" * 80)
        report.append("METRICS ANALYZER V2 vs V3 COMPARISON REPORT")
        report.append("=" * 80)
        report.append("")

        # Execution time
        report.append("PERFORMANCE:")
        exec_time = comparison["execution_time"]
        report.append(f"  V2 execution time: {exec_time['v2']}s")
        report.append(f"  V3 execution time: {exec_time['v3']}s")
        report.append(f"  Difference: {exec_time['difference']}s ({exec_time['v3_overhead_pct']:+.1f}%)")
        report.append("")

        # Detection results
        report.append("DETECTION RESULTS:")
        report.append(f"  Incident detected - V2: {comparison['incident_detected']['v2']}, V3: {comparison['incident_detected']['v3']}")
        report.append(f"  Anomalies detected - V2: {comparison['anomalies_detected']['v2']}, V3: {comparison['anomalies_detected']['v3']}")
        report.append(f"  Baseline quality - V2: {comparison['baseline_quality']['v2']}, V3: {comparison['baseline_quality']['v3']}")
        report.append(f"  Baseline stability - V2: {comparison['baseline_stability']['v2']:.2f}, V3: {comparison['baseline_stability']['v3']:.2f}")
        report.append("")

        # Primary symptom
        report.append("PRIMARY SYMPTOM:")
        symptom = comparison["primary_symptom"]
        report.append(f"  V2: {symptom['v2']} (severity: {symptom['v2_severity']})")
        report.append(f"  V3: {symptom['v3']} (severity: {symptom['v3_severity']})")
        report.append(f"  Match: {symptom['match']}")
        report.append("")

        # Confidence scores
        if "confidence_scores" in comparison:
            report.append("CONFIDENCE SCORES:")
            conf = comparison["confidence_scores"]
            if "v2_avg" in conf:
                report.append(f"  V2: avg={conf['v2_avg']}, min={conf['v2_min']}, max={conf['v2_max']}")
            if "v3_avg" in conf:
                report.append(f"  V3: avg={conf['v3_avg']}, min={conf['v3_min']}, max={conf['v3_max']}")
            report.append("")

        # Detection methods
        report.append("DETECTION METHODS:")
        methods = comparison["detection_methods"]
        report.append(f"  V2: {', '.join(methods['v2']) if methods['v2'] else 'none'}")
        report.append(f"  V3: {', '.join(methods['v3']) if methods['v3'] else 'none'}")
        report.append("")

        # V3 specific features
        report.append("V3 ADVANCED FEATURES:")
        v3_features = comparison["v3_features"]
        report.append(f"  Causal relationships found: {v3_features['causal_relationships_found']}")
        if v3_features['causal_relationships']:
            for cr in v3_features['causal_relationships']:
                report.append(f"    - Cluster {cr['cause_cluster_id']} -> Cluster {cr['effect_cluster_id']} (confidence: {cr['confidence']}, p={cr['granger_p_value']})")
        report.append("")

        report.append("=" * 80)

        return "\n".join(report)


def run_comparison_suite(data_dirs: List[str]):
    """Run comparison tests on multiple datasets"""
    logger.info("Starting analyzer comparison suite")

    all_comparisons = []

    for i, data_dir in enumerate(data_dirs, 1):
        logger.info(f"[{i}/{len(data_dirs)}] Testing dataset: {data_dir}")

        try:
            comparison_test = AnalyzerComparison(data_dir)

            # Run both analyzers
            v2_analysis = comparison_test.run_v2_analysis()
            v3_analysis = comparison_test.run_v3_analysis()

            # Compare results
            comparison = comparison_test.compare_results(v2_analysis, v3_analysis)

            # Generate report
            report = comparison_test.generate_report(comparison)
            logger.info(f"\n{report}")

            all_comparisons.append({
                "data_dir": data_dir,
                "comparison": comparison,
                "v2_analysis": v2_analysis,
                "v3_analysis": v3_analysis
            })

        except Exception as e:
            logger.error(f"Error testing {data_dir}: {e}", exc_info=True)
            continue

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY ACROSS ALL DATASETS")
    logger.info("=" * 80)

    if all_comparisons:
        avg_v2_time = statistics.mean([c["comparison"]["execution_time"]["v2"] for c in all_comparisons])
        avg_v3_time = statistics.mean([c["comparison"]["execution_time"]["v3"] for c in all_comparisons])
        avg_overhead = ((avg_v3_time / avg_v2_time) - 1) * 100 if avg_v2_time > 0 else 0

        logger.info(f"Datasets tested: {len(all_comparisons)}")
        logger.info(f"Average execution time - V2: {avg_v2_time:.3f}s, V3: {avg_v3_time:.3f}s")
        logger.info(f"Average V3 overhead: {avg_overhead:+.1f}%")

        v2_anomaly_counts = [c["comparison"]["anomalies_detected"]["v2"] for c in all_comparisons]
        v3_anomaly_counts = [c["comparison"]["anomalies_detected"]["v3"] for c in all_comparisons]

        logger.info(f"Average anomalies detected - V2: {statistics.mean(v2_anomaly_counts):.1f}, V3: {statistics.mean(v3_anomaly_counts):.1f}")

        causality_counts = [c["comparison"]["v3_features"]["causal_relationships_found"] for c in all_comparisons]
        logger.info(f"Average causal relationships found (V3 only): {statistics.mean(causality_counts):.1f}")

        # Save detailed results to file
        output_file = Path("/Users/sgupta/oats/services/agent/rca/analyzers/comparison_results.json")
        with open(output_file, 'w') as f:
            # Convert to serializable format
            serializable = []
            for comp in all_comparisons:
                serializable.append({
                    "data_dir": comp["data_dir"],
                    "comparison": comp["comparison"],
                    "execution_times": {
                        "v2": comp["v2_analysis"]["execution_time"],
                        "v3": comp["v3_analysis"]["execution_time"]
                    }
                })
            json.dump(serializable, f, indent=2)

        logger.info(f"\nDetailed results saved to: {output_file}")

    return all_comparisons


if __name__ == "__main__":
    # Find available test data directories
    import glob
    data_pattern = "/Users/sgupta/sim/output/data_*"
    data_dirs = sorted(glob.glob(data_pattern))[:5]  # Test first 5 datasets

    if not data_dirs:
        logger.error("No test data directories found matching pattern: " + data_pattern)
        logger.info("Please update the data_pattern variable or create test data")
    else:
        logger.info(f"Found {len(data_dirs)} test datasets")
        run_comparison_suite(data_dirs)
