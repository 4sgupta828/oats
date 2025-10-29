# RCA Tools Design: Implementation Plan for v6 Prompt

## Overview

This document maps the tools required by the v6 RCA prompt to concrete implementations that leverage:
- **Existing telemetry**: JSONL files (metrics, logs, traces) from simulation or production
- **Statistical analysis**: Z-scores, p-values, anomaly detection
- **Topology/ontology**: System knowledge loaded from configuration
- **Shell as uber-tool**: LLM can use shell commands for cloud/k8s/psql queries when needed

## Architecture Principles

1. **Read-only by default**: All tools are read-only statistical/analytical tools
2. **File-based analysis**: Tools query JSONL telemetry files (simulated or real)
3. **SOTA statistical methods**: Changepoint detection, Bayesian inference, anomaly classification
4. **LLM-friendly output**: Structured JSON with clear statistical evidence
5. **Shell guidance**: Tools provide hints when LLM should use shell for dynamic queries
6. **Fast execution**: Target <5s per tool call for 300s of telemetry data

---

## Tool Group 1: Situational Awareness & Change

### 1.1 `analyze_blast_radius`

**Purpose**: Identify which components are affected and where the failure is contained.

**Input**:
```python
{
  "symptom_component": "api-service",
  "incident_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"  # metrics.jsonl, traces.jsonl, logs.jsonl
}
```

**Implementation Strategy**:
1. Parse `traces.jsonl` to build dependency graph (caller → callee relationships)
2. Find all traces with errors during incident window
3. Analyze error propagation:
   - **Directly affected**: Components with errors originating in them
   - **Downstream affected**: Components that receive errors from upstream
   - **Upstream suspects**: Components that directly call the affected ones
   - **Isolation boundary**: First component in dep chain with no upstream errors
4. Use statistical analysis: components with >3σ error rate increase

**Output**:
```json
{
  "status": "success",
  "directly_affected": ["api-service"],
  "downstream_affected": ["frontend-service", "mobile-app"],
  "upstream_suspects": ["database-1", "user-cache", "auth-service"],
  "isolation_boundary": "user-cache",
  "error_statistics": {
    "api-service": {"error_count": 342, "error_rate": 0.45, "z_score": 12.3},
    "user-cache": {"error_count": 450, "error_rate": 0.89, "z_score": 15.8}
  },
  "dependency_graph": {
    "api-service": ["database-1", "user-cache"],
    "user-cache": ["redis-cluster"]
  }
}
```

**Files**: `rca/tools/situational_awareness.py`, uses `TracesAnalyzer`

---

### 1.2 `get_temporal_timeline`

**Purpose**: Find the first component to fail and sequence of cascading failures.

**Input**:
```python
{
  "affected_components": ["api-service", "user-cache", "database-1"],
  "incident_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Parse all three data sources: metrics, logs, traces
2. For each component, find **first anomaly timestamp**:
   - Metrics: First point where z-score > 3.0 (using changepoint detection)
   - Logs: First ERROR log
   - Traces: First error span
3. Rank by timestamp (earliest = likely origin)
4. Calculate statistical significance of each anomaly

**Output**:
```json
{
  "status": "success",
  "likely_origin_component": "user-cache",
  "timeline": [
    {
      "timestamp": 1698123459.2,
      "component": "user-cache",
      "event": "cache.hit_ratio STEP_CHANGE: 0.98 → 0.25",
      "signal_type": "metric",
      "z_score": 12.3,
      "statistical_significance": "p<0.001"
    },
    {
      "timestamp": 1698123459.8,
      "component": "user-cache",
      "event": "First ERROR log: 'EvictionPolicy: invalid TTL calculation'",
      "signal_type": "log",
      "log_count": 42
    },
    {
      "timestamp": 1698123460.5,
      "component": "database-1",
      "event": "db.query.latency_p99: 5ms → 200ms",
      "signal_type": "metric",
      "z_score": 8.5,
      "statistical_significance": "p<0.001"
    },
    {
      "timestamp": 1698123461.0,
      "component": "api-service",
      "event": "http.latency_p99: 120ms → 2800ms",
      "signal_type": "metric",
      "z_score": 15.2,
      "statistical_significance": "p<0.001"
    }
  ],
  "time_delta_analysis": {
    "user-cache_to_database-1": "1.3s (suggests direct causation)",
    "database-1_to_api-service": "0.5s (rapid cascade)"
  }
}
```

**Files**: `rca/tools/situational_awareness.py`, uses all analyzers

---

### 1.3 `get_recent_changes`

**Purpose**: Find deployments, config changes, or infrastructure changes near incident time.

**Input**:
```python
{
  "component_name": "user-cache",
  "lookback_window": [1698123300.0, 1698123456.0],  # T-5min to incident_start
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Parse `logs.jsonl` for change-related keywords:
   - "deployed", "deployment", "rollout", "version"
   - "config", "configuration", "updated"
   - "scaled", "restarted", "terminated"
2. Calculate time correlation: |change_time - incident_start|
3. Classify correlation likelihood based on proximity:
   - ≤2 min: VERY_HIGH
   - 2-5 min: HIGH
   - 5-10 min: MEDIUM
   - >10 min: LOW

**Output**:
```json
{
  "status": "success",
  "changes_detected": [
    {
      "timestamp": 1698123276.0,
      "component": "user-cache",
      "change_type": "deployment",
      "description": "Deployed user-cache v1.2.3",
      "time_before_incident": "180s",
      "correlation_likelihood": "VERY_HIGH",
      "evidence": {
        "log_entry": "INFO: Deployment user-cache v1.2.3 completed successfully",
        "source": "logs.jsonl:line_4523"
      }
    },
    {
      "timestamp": 1698123200.0,
      "component": "redis-cluster",
      "change_type": "configuration",
      "description": "Updated maxmemory-policy to allkeys-lru",
      "time_before_incident": "256s",
      "correlation_likelihood": "HIGH"
    }
  ],
  "shell_suggestion": "For live systems, use: kubectl get events --sort-by='.lastTimestamp' or aws cloudtrail lookup-events"
}
```

**Files**: `rca/tools/situational_awareness.py`, uses `LogsAnalyzer`

---

## Tool Group 2: Baseline Comparison (Statistical)

### 2.1 `compare_metrics`

**Purpose**: Statistical anomaly detection in metrics between baseline and incident.

**Input**:
```python
{
  "component_name": "user-cache",
  "incident_window": [1698123456.0, 1698123756.0],
  "baseline_window": [1698120000.0, 1698122000.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Use existing `MetricsAnalyzer` with enhanced anomaly classification
2. Calculate baseline statistics (mean, std, p50, p95, p99)
3. For each metric in incident window:
   - Calculate z-score: `(incident_mean - baseline_mean) / baseline_std`
   - Calculate percentage change
   - Classify anomaly pattern using **changepoint detection** (ruptures library):
     - **SPIKE**: Short-lived deviation (<30s)
     - **STEP_CHANGE**: Instantaneous jump (single changepoint)
     - **SUSTAINED_INCREASE**: Jump + plateau
     - **GRADUAL_DRIFT**: Linear trend (multiple changepoints)
4. Return **only anomalous metrics** (z > 3.0 or change > 100%)

**Output**:
```json
{
  "status": "success",
  "component": "user-cache",
  "anomalous_metrics": [
    {
      "metric_name": "cache.hit_ratio",
      "baseline_mean": 0.98,
      "baseline_std": 0.005,
      "incident_mean": 0.25,
      "delta_percent": -74.5,
      "z_score": 12.3,
      "p_value": 0.0,
      "anomaly_pattern": "STEP_CHANGE",
      "changepoint_time": 1698123459.2,
      "severity": "HIGH",
      "statistical_significance": "p<0.001"
    },
    {
      "metric_name": "cache.eviction_rate",
      "baseline_mean": 10.5,
      "baseline_std": 2.1,
      "incident_mean": 785.3,
      "delta_percent": 7380.0,
      "z_score": 369.0,
      "p_value": 0.0,
      "anomaly_pattern": "SUSTAINED_INCREASE",
      "severity": "HIGH"
    }
  ],
  "normal_metrics": [
    "cache.memory_utilization",
    "cache.connection_count"
  ],
  "total_metrics_analyzed": 15,
  "analysis_duration_ms": 234
}
```

**Files**: `rca/analyzers/metrics_analyzer.py` (enhance existing)

---

### 2.2 `compare_logs`

**Purpose**: Detect new log templates and frequency spikes in error messages.

**Input**:
```python
{
  "component_name": "user-cache",
  "incident_window": [1698123456.0, 1698123756.0],
  "baseline_window": [1698120000.0, 1698122000.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Use **Drain3** algorithm for log template mining
2. Parse baseline logs → extract templates
3. Parse incident logs → extract templates
4. Compare:
   - **New templates**: Templates in incident but not in baseline
   - **Frequency spikes**: Templates with >3σ frequency increase
5. Rank by severity and frequency

**Output**:
```json
{
  "status": "success",
  "component": "user-cache",
  "new_templates": [
    {
      "template_id": "T42",
      "template": "EvictionPolicy: invalid TTL calculation for key <*>",
      "first_seen": 1698123459.8,
      "frequency": 450,
      "severity": "ERROR",
      "example_message": "EvictionPolicy: invalid TTL calculation for key user:session:abc123"
    },
    {
      "template_id": "T43",
      "template": "Cache eviction triggered: policy=<*> reason=<*>",
      "first_seen": 1698123460.0,
      "frequency": 380,
      "severity": "WARN"
    }
  ],
  "frequency_spikes": [
    {
      "template_id": "T12",
      "template": "Redis connection timeout after <*>ms",
      "baseline_frequency": 5,
      "incident_frequency": 120,
      "frequency_increase": 2400.0,
      "z_score": 15.3,
      "severity": "ERROR"
    }
  ],
  "total_error_logs": 712,
  "baseline_error_logs": 45,
  "error_log_increase": 1482.0
}
```

**Files**: `rca/analyzers/logs_analyzer.py` (implement full version)

---

### 2.3 `compare_traces`

**Purpose**: Identify which service calls degraded during the incident.

**Input**:
```python
{
  "component_name": "api-service",
  "incident_window": [1698123456.0, 1698123756.0],
  "baseline_window": [1698120000.0, 1698122000.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Parse `traces.jsonl` for both windows
2. Group spans by `name` (e.g., "db.query", "cache.get", "HTTP POST /api/order")
3. For each span type, calculate:
   - Baseline: p50, p95, p99 latency
   - Incident: p50, p95, p99 latency
   - Degradation factor: incident_p99 / baseline_p99
4. Return spans with degradation factor > 2.0

**Output**:
```json
{
  "status": "success",
  "component": "api-service",
  "degraded_spans": [
    {
      "span_name": "db.query:SELECT",
      "baseline_p50_ms": 3.2,
      "baseline_p99_ms": 8.5,
      "incident_p50_ms": 120.5,
      "incident_p99_ms": 350.2,
      "degradation_factor": 41.2,
      "span_count_baseline": 1250,
      "span_count_incident": 15000,
      "throughput_increase": 12.0,
      "severity": "HIGH"
    },
    {
      "span_name": "cache.get",
      "baseline_p50_ms": 0.8,
      "baseline_p99_ms": 2.1,
      "incident_p50_ms": 1.2,
      "incident_p99_ms": 4.5,
      "degradation_factor": 2.1,
      "severity": "MEDIUM"
    }
  ],
  "error_span_analysis": {
    "total_error_spans": 450,
    "baseline_error_spans": 5,
    "error_types": {
      "no_compute_available": 380,
      "connection_timeout": 70
    }
  }
}
```

**Files**: `rca/analyzers/traces_analyzer.py` (implement full version)

---

## Tool Group 3: Active Validation & Topology

### 3.1 `get_service_dependencies`

**Purpose**: Return the dependency graph for a service.

**Input**:
```python
{
  "service_name": "api-service",
  "topology_file": "/path/to/topology.json"  # or auto-discover from traces
}
```

**Implementation Strategy**:
1. **Option A**: Load from topology config file (if available)
2. **Option B**: Auto-discover from traces (analyze caller→callee relationships)
3. Return immediate dependencies

**Output**:
```json
{
  "status": "success",
  "service": "api-service",
  "dependencies": [
    {
      "name": "database-1",
      "type": "database",
      "product": "postgresql"
    },
    {
      "name": "user-cache",
      "type": "cache",
      "product": "redis"
    },
    {
      "name": "auth-service",
      "type": "service"
    }
  ],
  "dependency_graph": {
    "database-1": [],
    "user-cache": ["redis-cluster"],
    "auth-service": ["auth-db"]
  }
}
```

**Files**: `rca/tools/topology.py`

---

### 3.2 `check_instance_health`

**Purpose**: Get resource utilization metrics for a component.

**Input**:
```python
{
  "component_name": "user-cache",
  "time_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Query metrics.jsonl for infrastructure metrics:
   - `component.cpu_utilization`
   - `component.memory_utilization`
   - `component.disk_io_wait`
   - `component.network_io`
2. Calculate mean/p95/p99 for the window

**Output**:
```json
{
  "status": "success",
  "component": "user-cache",
  "cpu_util": {"mean": 0.45, "p95": 0.67, "p99": 0.78, "max": 0.85},
  "mem_util": {"mean": 0.82, "p95": 0.88, "p99": 0.92, "max": 0.95},
  "disk_io_wait_ms": {"mean": 2.3, "p95": 5.1, "p99": 8.2},
  "network_io_mbps": {"mean": 150.2, "p95": 230.5, "p99": 280.1},
  "process_status": "running",
  "health_assessment": "HEALTHY",
  "shell_suggestion": "For live checks: kubectl top pods | grep user-cache or top -p <pid>"
}
```

**Files**: `rca/tools/health_checks.py`

---

### 3.3 `get_database_stats`

**Purpose**: Database-specific health metrics.

**Input**:
```python
{
  "component_name": "database-1",
  "time_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Query metrics for DB-specific metrics:
   - `db.connections.active`
   - `db.connections.max`
   - `db.queries.slow_count`
   - `db.locks.wait_time`
2. Calculate statistics

**Output**:
```json
{
  "status": "success",
  "component": "database-1",
  "active_connections": {"mean": 45, "p95": 78, "p99": 92, "max": 95},
  "max_connections": 100,
  "connection_utilization": 0.95,
  "slow_query_count": 12,
  "slow_query_rate": 0.04,
  "lock_wait_time_ms": {"mean": 5.2, "p95": 50.1, "p99": 120.5},
  "health_assessment": "DEGRADED",
  "saturation_detected": true,
  "shell_suggestion": "For live DB stats: psql -c 'SELECT * FROM pg_stat_activity' or SHOW PROCESSLIST"
}
```

**Files**: `rca/tools/health_checks.py`

---

### 3.4 `get_cache_stats`

**Purpose**: Cache-specific health metrics.

**Input**:
```python
{
  "component_name": "user-cache",
  "time_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Query cache-specific metrics:
   - `cache.hit_ratio`
   - `cache.p99_latency_ms`
   - `cache.evictions.total`
   - `cache.memory_utilization`

**Output**:
```json
{
  "status": "success",
  "component": "user-cache",
  "hit_ratio": {"mean": 0.25, "min": 0.18, "max": 0.32},
  "p99_latency_ms": {"mean": 2.5, "p95": 3.2, "p99": 4.1},
  "total_evictions": 15200,
  "eviction_rate": 50.7,
  "memory_utilization": 0.78,
  "health_assessment": "FAULTY",
  "anomaly_detected": "Eviction rate 75× normal",
  "shell_suggestion": "For live cache stats: redis-cli INFO stats or kubectl exec <pod> -- redis-cli"
}
```

**Files**: `rca/tools/health_checks.py`

---

### 3.5 `check_dependency_health`

**Purpose**: Check connectivity and health between two components.

**Input**:
```python
{
  "source_component": "api-service",
  "target_component": "database-1",
  "time_window": [1698123456.0, 1698123756.0],
  "data_dir": "/path/to/telemetry"
}
```

**Implementation Strategy**:
1. Parse traces to find spans where source calls target
2. Calculate:
   - Connection success rate
   - Latency (p50, p99)
   - Error rate
3. Check for circuit breaker patterns in logs

**Output**:
```json
{
  "status": "success",
  "source": "api-service",
  "target": "database-1",
  "connectivity": "HEALTHY",
  "latency_ms": {"p50": 3.2, "p95": 8.1, "p99": 15.2},
  "error_rate": 0.002,
  "total_calls": 12500,
  "failed_calls": 25,
  "circuit_breaker_state": "CLOSED",
  "health_assessment": "HEALTHY"
}
```

**Files**: `rca/tools/health_checks.py`

---

## Tool Group 4: Dynamic Analysis (Shell Guidance)

The prompt already defines `shell()`, `create_file()`, and `python()` as generic tools. Our RCA tools should **provide hints** when the LLM should use these:

### Shell Guidance Strategy

When tools return results, include `shell_suggestion` field:

```json
{
  "status": "success",
  ...
  "shell_suggestion": "For live data, use: kubectl logs <pod> | grep ERROR"
}
```

### Examples:
- **K8s**: `kubectl get pods`, `kubectl describe pod`, `kubectl logs`
- **Docker**: `docker ps`, `docker stats`, `docker logs`
- **DB**: `psql -c "QUERY"`, `mysql -e "QUERY"`
- **Cache**: `redis-cli INFO`, `memcached-tool`
- **Logs**: `rg "pattern" /var/log/`, `journalctl -u service`

---

## Tool Group 5: Finish Tool

### 5.1 `finish`

**Purpose**: Submit final RCA report.

**Input**:
```python
{
  "root_cause_component": "user-cache",
  "root_cause_finding": "Deployment v1.2.3 introduced TTL calculation bug causing premature cache evictions",
  "failure_mode": "eviction_policy_bug",
  "trigger_event": "deployment:user-cache:v1.2.3",
  "causal_chain": [
    "user-cache v1.2.3 deployed at T-3min",
    "Bug in TTL logic caused 90% of valid entries to be evicted",
    "Cache hit ratio dropped from 98% to 25%",
    "api-service DB queries increased 20×",
    "database-1 latency increased from 5ms to 200ms",
    "api-service P99 latency spiked from 120ms to 2800ms"
  ],
  "evidence_summary": {
    "metrics": ["cache.hit_ratio z=12.3", "db.latency z=8.5"],
    "logs": ["42 ERROR logs: EvictionPolicy bug"],
    "traces": ["450 error spans in user-cache"]
  },
  "hypothesis_evolution": [...],
  "recommendations": [
    "Immediate: Rollback user-cache to v1.2.2",
    "Short-term: Add unit tests for TTL calculation",
    "Long-term: Implement cache eviction monitoring"
  ]
}
```

**Output**:
```json
{
  "status": "complete",
  "report_id": "rca_20251028_123456",
  "summary": "Root cause identified with HIGH confidence"
}
```

---

## Knowledge Base: Topology & Ontology

### Topology File Format

`topology.json`:
```json
{
  "components": {
    "api-service": {
      "type": "service",
      "dependencies": ["database-1", "user-cache", "auth-service"]
    },
    "database-1": {
      "type": "database",
      "product": "postgresql",
      "max_connections": 100
    },
    "user-cache": {
      "type": "cache",
      "product": "redis",
      "max_memory_mb": 4096
    }
  }
}
```

### Ontology File Format

`ontology.json`:
```json
{
  "database": {
    "postgresql": {
      "key_metrics": [
        {"name": "connections.active", "saturation_formula": "active/max > 0.9"}
      ],
      "common_failure_modes": [
        {
          "name": "connection_pool_exhaustion",
          "prior_probability": 0.15,
          "diagnostic_pattern": "connections.active ≈ max_connections"
        }
      ]
    }
  },
  "cache": {
    "redis": {
      "key_metrics": [
        {"name": "hit_ratio", "healthy_range": [0.8, 1.0]}
      ],
      "common_failure_modes": [
        {
          "name": "eviction_policy_bug",
          "prior_probability": 0.05,
          "diagnostic_pattern": "eviction_rate >> baseline"
        }
      ]
    }
  }
}
```

---

## Implementation Plan

### Phase 1: Core Tools (Priority 1)
1. ✅ Enhance `MetricsAnalyzer` with changepoint detection
2. ✅ Implement `compare_metrics` tool
3. ✅ Implement `get_temporal_timeline` tool
4. ✅ Implement `analyze_blast_radius` tool

### Phase 2: Baseline Comparison (Priority 2)
5. ✅ Implement full `LogsAnalyzer` with Drain3
6. ✅ Implement `compare_logs` tool
7. ✅ Implement full `TracesAnalyzer`
8. ✅ Implement `compare_traces` tool

### Phase 3: Validation Tools (Priority 3)
9. ✅ Implement `get_service_dependencies`
10. ✅ Implement `check_instance_health`
11. ✅ Implement `get_database_stats`
12. ✅ Implement `get_cache_stats`
13. ✅ Implement `check_dependency_health`

### Phase 4: Integration (Priority 4)
14. ✅ Add UF decorators for all tools
15. ✅ Create tool registry
16. ✅ Add `finish` tool
17. ✅ Update `get_recent_changes` tool

---

## Tool Registration (UF Framework)

All tools will be registered using the `@uf` decorator:

```python
from agent.core.sdk import uf, UfInput
from pydantic import Field

class CompareMetricsInput(UfInput):
    component_name: str = Field(..., description="Component to analyze")
    incident_window: List[float] = Field(..., description="[start, end] timestamps")
    baseline_window: List[float] = Field(..., description="[start, end] timestamps")
    data_dir: str = Field(..., description="Path to telemetry data")

@uf(
    name="compare_metrics",
    version="1.0.0",
    description="Statistical anomaly detection in metrics between baseline and incident windows"
)
def compare_metrics(inputs: CompareMetricsInput) -> dict:
    # Implementation
    pass
```

---

## Testing Strategy

1. **Unit tests**: Each analyzer with synthetic data
2. **Integration tests**: Full tool chains with simulated telemetry
3. **Validation**: Run against known incidents with ground truth
4. **Performance**: Target <5s per tool call

---

## Success Metrics

- **Coverage**: All 15 tools from v6 prompt implemented
- **Statistical rigor**: Z-scores, p-values, changepoint detection
- **Speed**: <5s per tool call for 300s telemetry
- **Accuracy**: >90% anomaly detection on synthetic incidents
- **Usability**: LLM can successfully complete investigations end-to-end
