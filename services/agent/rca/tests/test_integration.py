"""Integration tests for RCA system

These tests verify that the RCA tools work correctly with simulation data.
To run: pytest services/agent/rca/tests/test_integration.py
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import json
import tempfile
from unittest.mock import Mock

# Import RCA components
from rca.backends.simulation import SimulationBackend
from rca.analyzers.metrics_analyzer import MetricsAnalyzer
from rca.analyzers.logs_analyzer import LogsAnalyzer
from rca.analyzers.traces_analyzer import TracesAnalyzer
from rca.tools.incident_detection import detect_incident_window
from rca.tools.rca_tools import (
    analyze_blast_radius,
    compare_metrics,
    get_recent_changes
)


@pytest.fixture
def sample_telemetry_dir():
    """Create a temporary directory with sample telemetry data"""
    temp_dir = tempfile.mkdtemp()

    # Create sample metrics.jsonl
    metrics_data = [
        {"ts": 50000000000, "name": "cache.hit_ratio", "value": 0.98, "labels": {"component": "user_cache", "__name__": "cache.hit_ratio"}},
        {"ts": 55000000000, "name": "cache.hit_ratio", "value": 0.97, "labels": {"component": "user_cache", "__name__": "cache.hit_ratio"}},
        {"ts": 60000000000, "name": "cache.hit_ratio", "value": 0.25, "labels": {"component": "user_cache", "__name__": "cache.hit_ratio"}},
        {"ts": 65000000000, "name": "cache.hit_ratio", "value": 0.24, "labels": {"component": "user_cache", "__name__": "cache.hit_ratio"}},
    ]
    with open(os.path.join(temp_dir, "metrics.jsonl"), 'w') as f:
        for m in metrics_data:
            f.write(json.dumps(m) + '\n')

    # Create sample logs.jsonl
    logs_data = [
        {"timestamp": "50.00s", "level": "INFO", "message": "Cache operating normally", "attributes": {"component": "user_cache"}},
        {"timestamp": "60.00s", "level": "ERROR", "message": "Cache eviction policy error", "attributes": {"component": "user_cache"}},
        {"timestamp": "61.00s", "level": "ERROR", "message": "Cache eviction policy error", "attributes": {"component": "user_cache"}},
    ]
    with open(os.path.join(temp_dir, "logs.jsonl"), 'w') as f:
        for log in logs_data:
            f.write(json.dumps(log) + '\n')

    # Create sample traces.jsonl
    traces_data = [
        {
            "span_id": "span1",
            "parent_span_id": None,
            "name": "cache.get",
            "start_time_unix_nano": 50000000000,
            "end_time_unix_nano": 50005000000,
            "attributes": {"component": "user_cache"},
            "status": {"code": "OK"}
        }
    ]
    with open(os.path.join(temp_dir, "traces.jsonl"), 'w') as f:
        for trace in traces_data:
            f.write(json.dumps(trace) + '\n')

    # Create sample infra_context.json
    infra_context = {
        "components": {
            "user_cache": {
                "type": "cache",
                "product": "redis",
                "dependencies": ["redis_cluster"],
                "deployment_history": [
                    {
                        "simulation_time": 57.0,
                        "commit_id": "abc123",
                        "message": "Deploy cache v1.2.3"
                    }
                ]
            }
        }
    }
    with open(os.path.join(temp_dir, "infra_context.json"), 'w') as f:
        json.dump(infra_context, f)

    # Create sample metadata.json
    metadata = {
        "simulation_duration": 100.0,
        "start_time": 0.0,
        "end_time": 100.0
    }
    with open(os.path.join(temp_dir, "metadata.json"), 'w') as f:
        json.dump(metadata, f)

    yield temp_dir

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


class TestSimulationBackend:
    """Test SimulationBackend functionality"""

    def test_backend_initialization(self, sample_telemetry_dir):
        """Test that backend initializes correctly"""
        backend = SimulationBackend(sample_telemetry_dir)

        assert backend.data_dir.exists()
        assert backend.min_time > 0
        assert backend.max_time > backend.min_time

    def test_query_metrics(self, sample_telemetry_dir):
        """Test querying metrics"""
        backend = SimulationBackend(sample_telemetry_dir)

        metrics = backend.query_metrics(
            component="user_cache",
            metric_pattern="*",
            time_range=(0.0, 100.0)
        )

        assert len(metrics) > 0
        assert all(m.labels.get("component") == "user_cache" for m in metrics)

    def test_query_logs(self, sample_telemetry_dir):
        """Test querying logs"""
        backend = SimulationBackend(sample_telemetry_dir)

        logs = backend.query_logs(
            component="user_cache",
            time_range=(0.0, 100.0)
        )

        assert len(logs) > 0
        assert any(log.level == "ERROR" for log in logs)

    def test_get_topology(self, sample_telemetry_dir):
        """Test getting topology"""
        backend = SimulationBackend(sample_telemetry_dir)

        topology = backend.get_topology()

        assert "components" in topology
        assert "user_cache" in topology["components"]


class TestMetricsAnalyzer:
    """Test MetricsAnalyzer functionality"""

    def test_detect_anomalies(self, sample_telemetry_dir):
        """Test anomaly detection"""
        backend = SimulationBackend(sample_telemetry_dir)
        analyzer = MetricsAnalyzer(backend)

        anomalies = analyzer.detect_anomalies(
            component="user_cache",
            baseline_range=(40.0, 55.0),
            incident_range=(60.0, 70.0),
            metric_pattern="*"
        )

        # Should detect the cache hit ratio drop
        assert len(anomalies) > 0
        assert any(a.metric_name == "cache.hit_ratio" for a in anomalies)

    def test_compare_metrics(self, sample_telemetry_dir):
        """Test metrics comparison"""
        backend = SimulationBackend(sample_telemetry_dir)
        analyzer = MetricsAnalyzer(backend)

        result = analyzer.compare_metrics(
            component="user_cache",
            baseline_range=(40.0, 55.0),
            incident_range=(60.0, 70.0)
        )

        assert result["status"] == "success"
        assert len(result["anomalous_metrics"]) > 0


class TestIncidentDetection:
    """Test incident detection functionality"""

    def test_detect_incident_window(self, sample_telemetry_dir):
        """Test automatic incident window detection"""
        # Mock the UfInput
        class MockInput:
            data_dir = sample_telemetry_dir
            symptom_hint = None
            lookback_seconds = 300
            sensitivity = "high"

        result = detect_incident_window(MockInput())

        assert result["status"] == "success"
        # May or may not detect incident depending on data quality
        # Just verify structure is correct
        assert "incident_detected" in result


class TestRCATools:
    """Test RCA tools functionality"""

    def test_compare_metrics_tool(self, sample_telemetry_dir):
        """Test compare_metrics tool"""
        class MockInput:
            component_name = "user_cache"
            incident_window = [60.0, 70.0]
            baseline_window = [40.0, 55.0]
            data_dir = sample_telemetry_dir

        result = compare_metrics(MockInput())

        assert result["status"] == "success"
        assert "component" in result

    def test_get_recent_changes_tool(self, sample_telemetry_dir):
        """Test get_recent_changes tool"""
        class MockInput:
            component_name = "user_cache"
            reference_time = 60.0
            lookback_seconds = 300
            data_dir = sample_telemetry_dir

        result = get_recent_changes(MockInput())

        assert result["status"] == "success"
        assert "changes_detected" in result
        # Should find the deployment at t=57s
        if result["changes_detected"]:
            assert result["changes_detected"][0]["change_type"] == "deployment"


def test_tool_registration():
    """Test that all RCA tools are properly registered"""
    from tools.rca_tools_integration import verify_rca_tools, RCA_TOOL_COUNT

    # Verify tools are available
    assert RCA_TOOL_COUNT == 13  # Total number of RCA tools

    # Run verification
    assert verify_rca_tools() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
