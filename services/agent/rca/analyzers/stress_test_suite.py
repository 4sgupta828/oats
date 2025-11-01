"""
Comprehensive stress test suite for metrics analyzers.

Tests challenging scenarios and identifies bugs/limitations.
"""

import json
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
import statistics

from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer_v2 import MetricsAnalyzerV2, AnalyzerConfig as ConfigV2
from rca.analyzers.metrics_analyzer_v3 import MetricsAnalyzerV3, AnalyzerConfig as ConfigV3
from core.logging_config import get_logger

logger = get_logger('stress_test_suite')


class BugReport:
    """Track bugs and issues found during testing"""

    def __init__(self):
        self.bugs = []
        self.warnings = []
        self.performance_issues = []

    def add_bug(self, severity: str, version: str, scenario: str, description: str, details: Dict = None):
        """Add a bug report"""
        self.bugs.append({
            "severity": severity,  # CRITICAL, HIGH, MEDIUM, LOW
            "version": version,  # v2, v3, both
            "scenario": scenario,
            "description": description,
            "details": details or {},
            "timestamp": time.time()
        })

    def add_warning(self, version: str, scenario: str, description: str, details: Dict = None):
        """Add a warning (not a bug, but concerning behavior)"""
        self.warnings.append({
            "version": version,
            "scenario": scenario,
            "description": description,
            "details": details or {},
            "timestamp": time.time()
        })

    def add_performance_issue(self, version: str, scenario: str, description: str, metrics: Dict):
        """Add a performance issue"""
        self.performance_issues.append({
            "version": version,
            "scenario": scenario,
            "description": description,
            "metrics": metrics,
            "timestamp": time.time()
        })

    def print_summary(self):
        """Print summary of findings"""
        logger.info("\n" + "=" * 100)
        logger.info("BUG REPORT SUMMARY")
        logger.info("=" * 100)

        logger.info(f"\nCRITICAL BUGS: {len([b for b in self.bugs if b['severity'] == 'CRITICAL'])}")
        logger.info(f"HIGH PRIORITY BUGS: {len([b for b in self.bugs if b['severity'] == 'HIGH'])}")
        logger.info(f"MEDIUM PRIORITY BUGS: {len([b for b in self.bugs if b['severity'] == 'MEDIUM'])}")
        logger.info(f"LOW PRIORITY BUGS: {len([b for b in self.bugs if b['severity'] == 'LOW'])}")
        logger.info(f"WARNINGS: {len(self.warnings)}")
        logger.info(f"PERFORMANCE ISSUES: {len(self.performance_issues)}")

        if self.bugs:
            logger.info("\n" + "-" * 100)
            logger.info("BUGS FOUND:")
            logger.info("-" * 100)
            for i, bug in enumerate(self.bugs, 1):
                logger.info(f"\n{i}. [{bug['severity']}] {bug['version'].upper()} - {bug['scenario']}")
                logger.info(f"   {bug['description']}")
                if bug['details']:
                    for key, value in bug['details'].items():
                        logger.info(f"   {key}: {value}")

        if self.warnings:
            logger.info("\n" + "-" * 100)
            logger.info("WARNINGS:")
            logger.info("-" * 100)
            for i, warning in enumerate(self.warnings, 1):
                logger.info(f"\n{i}. {warning['version'].upper()} - {warning['scenario']}")
                logger.info(f"   {warning['description']}")

        if self.performance_issues:
            logger.info("\n" + "-" * 100)
            logger.info("PERFORMANCE ISSUES:")
            logger.info("-" * 100)
            for i, issue in enumerate(self.performance_issues, 1):
                logger.info(f"\n{i}. {issue['version'].upper()} - {issue['scenario']}")
                logger.info(f"   {issue['description']}")
                logger.info(f"   Metrics: {issue['metrics']}")

        logger.info("\n" + "=" * 100)


class StressTestSuite:
    """Comprehensive stress testing for analyzers"""

    def __init__(self, test_data_dir: str):
        self.test_data_dir = Path(test_data_dir)
        self.bug_report = BugReport()

    def load_ground_truth(self, scenario_dir: Path) -> Dict[str, Any]:
        """Load ground truth from scenario metadata"""
        metadata_file = scenario_dir / "scenario_metadata.json"
        with open(metadata_file) as f:
            return json.load(f)

    def run_analyzer(self, version: str, data_dir: str, config=None) -> Dict[str, Any]:
        """Run analyzer and catch errors"""
        try:
            backend = SimulationBackend(data_dir)

            if version == "v2":
                if config is None:
                    config = ConfigV2(
                        sensitivity="medium",
                        use_mad_for_skewed=True,
                        use_adaptive_thresholds=True,
                        min_confidence_threshold=0.5,
                        validate_baseline_stability=True,
                        filter_boundary_anomalies=True
                    )
                analyzer = MetricsAnalyzerV2(backend, config=config)
            else:  # v3
                if config is None:
                    config = ConfigV3(
                        sensitivity="medium",
                        use_mad_for_skewed=True,
                        use_adaptive_thresholds=True,
                        min_confidence_threshold=0.5,
                        validate_baseline_stability=True,
                        filter_boundary_anomalies=True,
                        detect_seasonality=True,
                        analyze_causality=True,
                        use_multivariate_detection=True
                    )
                analyzer = MetricsAnalyzerV3(backend, config=config)

            start_time = time.time()
            result = analyzer.detect_incident_and_baseline()
            elapsed = time.time() - start_time

            return {
                "status": "success",
                "result": result,
                "execution_time": elapsed,
                "error": None
            }

        except Exception as e:
            logger.error(f"CRASH in {version}: {e}", exc_info=True)
            return {
                "status": "crashed",
                "result": None,
                "execution_time": None,
                "error": str(e),
                "traceback": traceback.format_exc()
            }

    def evaluate_detection_quality(
        self,
        result: Dict[str, Any],
        ground_truth: Dict[str, Any],
        version: str,
        scenario_name: str
    ):
        """Evaluate detection quality and log issues"""

        if result["status"] == "crashed":
            self.bug_report.add_bug(
                "CRITICAL", version, scenario_name,
                f"Analyzer crashed: {result['error']}",
                {"traceback": result.get("traceback")}
            )
            return

        analysis = result["result"]

        # Check 1: Did it detect the incident?
        true_anomalies = [a for a in ground_truth["true_anomalies"] if not a.get("is_false_positive", False)]
        incident_detected = analysis.get("incident_detected", False)

        if true_anomalies and not incident_detected:
            self.bug_report.add_bug(
                "HIGH", version, scenario_name,
                "Failed to detect incident (false negative)",
                {
                    "true_anomalies_count": len(true_anomalies),
                    "baseline_quality": analysis.get("baseline_window", {}).get("quality")
                }
            )

        # Check 2: False positive rate
        false_positive_anomalies = [a for a in ground_truth["true_anomalies"] if a.get("is_false_positive", False)]
        detected_anomalies = analysis.get("anomalies", [])

        if len(detected_anomalies) > len(true_anomalies) * 2:
            self.bug_report.add_warning(
                version, scenario_name,
                f"High false positive rate: detected {len(detected_anomalies)} but only {len(true_anomalies)} true",
                {"detected": len(detected_anomalies), "expected": len(true_anomalies)}
            )

        # Check 3: Correct primary symptom identification
        if incident_detected and true_anomalies:
            primary_symptom = analysis.get("primary_symptom", {})
            first_true_anomaly = sorted(true_anomalies, key=lambda x: x["start_time"])[0]

            # Check if primary symptom matches first anomaly
            if (primary_symptom.get("component") != first_true_anomaly["component"] or
                primary_symptom.get("metric") != first_true_anomaly["metric"]):

                self.bug_report.add_warning(
                    version, scenario_name,
                    "Primary symptom mismatch",
                    {
                        "detected": f"{primary_symptom.get('component')}:{primary_symptom.get('metric')}",
                        "expected": f"{first_true_anomaly['component']}:{first_true_anomaly['metric']}"
                    }
                )

        # Check 4: Baseline quality
        baseline_quality = analysis.get("baseline_window", {}).get("quality")
        if baseline_quality == "insufficient":
            self.bug_report.add_warning(
                version, scenario_name,
                "Insufficient baseline quality",
                {"quality": baseline_quality}
            )

        # Check 5: Detection methods used
        detection_methods = set()
        for anomaly in detected_anomalies:
            for method in anomaly.get("detection_methods", []):
                detection_methods.add(method)

        # For skewed distributions, should use MAD or IQR
        metrics_config = ground_truth.get("metrics_config", [])
        has_skewed = any(m["distribution"] in ["log_normal", "exponential"] for m in metrics_config)

        if has_skewed and detection_methods and not any(m in ["mad", "iqr", "percentile"] for m in detection_methods):
            self.bug_report.add_warning(
                version, scenario_name,
                "Not using robust methods for skewed distributions",
                {"methods_used": list(detection_methods), "has_skewed": has_skewed}
            )

        # Check 6: Performance
        exec_time = result["execution_time"]
        if exec_time > 1.0:  # More than 1 second for synthetic data is slow
            self.bug_report.add_performance_issue(
                version, scenario_name,
                "Slow execution time",
                {"execution_time": exec_time, "threshold": 1.0}
            )

        # Check 7: Confidence scores
        if detected_anomalies:
            confidences = [a.get("confidence", 1.0) for a in detected_anomalies]
            avg_confidence = statistics.mean(confidences)

            if avg_confidence < 0.5:
                self.bug_report.add_warning(
                    version, scenario_name,
                    "Low average confidence scores",
                    {"avg_confidence": avg_confidence}
                )

        # Check 8: V3-specific: Causality detection
        if version == "v3":
            causal_relationships = analysis.get("causal_relationships", [])
            expected_causality = "cascading" in scenario_name.lower()

            if expected_causality and len(causal_relationships) == 0:
                self.bug_report.add_warning(
                    "v3", scenario_name,
                    "Failed to detect expected causal relationships",
                    {"expected": expected_causality, "found": len(causal_relationships)}
                )

    def test_scenario(self, scenario_dir: Path):
        """Test a single scenario"""
        scenario_name = scenario_dir.name
        logger.info("\n" + "=" * 100)
        logger.info(f"TESTING SCENARIO: {scenario_name}")
        logger.info("=" * 100)

        # Load ground truth
        ground_truth = self.load_ground_truth(scenario_dir)
        logger.info(f"Ground truth: {len(ground_truth['true_anomalies'])} anomalies")

        # Test V2
        logger.info("\nRunning V2...")
        v2_result = self.run_analyzer("v2", str(scenario_dir))
        logger.info(f"V2 Status: {v2_result['status']}, Time: {v2_result.get('execution_time', 'N/A')}s")

        # Test V3
        logger.info("\nRunning V3...")
        v3_result = self.run_analyzer("v3", str(scenario_dir))
        logger.info(f"V3 Status: {v3_result['status']}, Time: {v3_result.get('execution_time', 'N/A')}s")

        # Evaluate
        logger.info("\nEvaluating V2...")
        self.evaluate_detection_quality(v2_result, ground_truth, "v2", scenario_name)

        logger.info("Evaluating V3...")
        self.evaluate_detection_quality(v3_result, ground_truth, "v3", scenario_name)

        # Compare V2 vs V3
        if v2_result["status"] == "success" and v3_result["status"] == "success":
            v2_detected = v2_result["result"].get("incident_detected", False)
            v3_detected = v3_result["result"].get("incident_detected", False)

            if v2_detected != v3_detected:
                self.bug_report.add_bug(
                    "MEDIUM", "both", scenario_name,
                    "V2 and V3 disagree on incident detection",
                    {"v2_detected": v2_detected, "v3_detected": v3_detected}
                )

        # Detailed comparison
        logger.info("\n" + "-" * 100)
        if v2_result["status"] == "success":
            v2_analysis = v2_result["result"]
            logger.info(f"V2: Detected {len(v2_analysis.get('anomalies', []))} anomalies")
            if v2_analysis.get("incident_detected"):
                primary = v2_analysis.get("primary_symptom", {})
                logger.info(f"    Primary: {primary.get('component')}:{primary.get('metric')} ({primary.get('severity')})")

        if v3_result["status"] == "success":
            v3_analysis = v3_result["result"]
            logger.info(f"V3: Detected {len(v3_analysis.get('anomalies', []))} anomalies")
            if v3_analysis.get("incident_detected"):
                primary = v3_analysis.get("primary_symptom", {})
                logger.info(f"    Primary: {primary.get('component')}:{primary.get('metric')} ({primary.get('severity')})")
                causal = v3_analysis.get("causal_relationships", [])
                if causal:
                    logger.info(f"    Causal relationships: {len(causal)}")

    def run_all_tests(self):
        """Run all stress tests"""
        logger.info("\n" + "=" * 100)
        logger.info("STARTING COMPREHENSIVE STRESS TEST SUITE")
        logger.info("=" * 100)

        # Find all scenario directories
        scenarios = sorted([d for d in self.test_data_dir.iterdir() if d.is_dir()])

        logger.info(f"\nFound {len(scenarios)} test scenarios")

        for scenario_dir in scenarios:
            try:
                self.test_scenario(scenario_dir)
            except Exception as e:
                logger.error(f"Error testing {scenario_dir.name}: {e}", exc_info=True)
                self.bug_report.add_bug(
                    "CRITICAL", "test_framework", scenario_dir.name,
                    f"Test framework error: {e}",
                    {"traceback": traceback.format_exc()}
                )

        # Print final report
        self.bug_report.print_summary()

        # Save bug report
        report_file = self.test_data_dir / "bug_report.json"
        with open(report_file, 'w') as f:
            json.dump({
                "bugs": self.bug_report.bugs,
                "warnings": self.bug_report.warnings,
                "performance_issues": self.bug_report.performance_issues
            }, f, indent=2)

        logger.info(f"\nBug report saved to: {report_file}")


if __name__ == "__main__":
    test_data_dir = "/Users/sgupta/oats/services/agent/rca/analyzers/test_data"
    suite = StressTestSuite(test_data_dir)
    suite.run_all_tests()
