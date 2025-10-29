# RCA System for OATS Agent

This directory contains the Root Cause Analysis (RCA) system implementation for the OATS agent, designed to build a SOTA RCA agent for cloud infrastructure incidents.

## Overview

The RCA system implements a comprehensive toolkit for investigating distributed system failures using telemetry data (metrics, logs, traces) and systematic hypothesis-driven methodology.

## Architecture

```
rca/
├── backends/           # Telemetry data access layer
│   ├── base.py        # Abstract TelemetryBackend interface
│   └── simulation.py  # SimulationBackend for JSONL files
├── analyzers/         # Statistical analysis engines
│   ├── metrics_analyzer.py   # Anomaly detection with z-scores, changepoint detection
│   ├── logs_analyzer.py      # Log template mining and frequency analysis
│   └── traces_analyzer.py    # Latency degradation and dependency analysis
└── tools/             # RCA tools exposed to the agent
    ├── incident_detection.py  # Dynamic incident window detection
    └── rca_tools.py          # All 15 RCA tools (situational, comparison, validation)
```

## Key Features

### 1. Dynamic Incident Detection

The `detect_incident_window` tool automatically discovers anomaly windows from telemetry data:

- Scans all metrics for statistical anomalies (z-score > 3.0)
- Uses changepoint detection to identify incident start/end times
- Calculates baseline windows automatically
- No hardcoded incident windows required!

**Usage:**
```python
detect_incident_window(
    data_dir="/path/to/telemetry",
    sensitivity="high"  # high, medium, or low
)
```

### 2. Telemetry Backend Abstraction

The `TelemetryBackend` provides a unified interface for accessing telemetry from different sources:

- **SimulationBackend**: Reads JSONL files from simulation output
  - `metrics.jsonl` - Time-series metrics (nanosecond timestamps)
  - `logs.jsonl` - Structured logs (simulation time format)
  - `traces.jsonl` - OpenTelemetry spans
  - `infra_context.json` - Topology and deployment history
  - `metadata.json` - Simulation metadata

- **Future**: PrometheusBackend, CloudWatchBackend, etc. can be added

### 3. Statistical Analyzers

#### MetricsAnalyzer
- Z-score based anomaly detection
- Anomaly pattern classification:
  - `SPIKE` - Short-lived deviation (<30s)
  - `STEP_CHANGE` - Instantaneous jump
  - `SUSTAINED_INCREASE` - Jump + plateau
  - `GRADUAL_DRIFT` - Linear trend
- Statistical significance (p-values)
- Percentage change calculations

#### LogsAnalyzer
- Template extraction (generalizes dynamic parts)
- New template detection (templates in incident but not baseline)
- Frequency spike detection (significant increases)
- Error log counting and classification

#### TracesAnalyzer
- Latency percentile comparison (P50, P95, P99)
- Degradation factor calculation
- Dependency graph construction
- Error span analysis

### 4. RCA Tools (15 tools)

#### Group 1: Situational Awareness
1. **analyze_blast_radius** - Identify affected components and isolation boundary
2. **get_temporal_timeline** - Find first component to fail and failure sequence
3. **get_recent_changes** - Discover deployments/changes near incident time

#### Group 2: Baseline Comparison
4. **compare_metrics** - Statistical anomaly detection in metrics
5. **compare_logs** - Detect new log templates and frequency spikes
6. **compare_traces** - Identify degraded service calls

#### Group 3: Active Validation
7. **get_service_dependencies** - Get dependency graph for a service
8. **check_instance_health** - Check CPU, memory, disk, network utilization
9. **get_database_stats** - Check connections, queries, locks
10. **get_cache_stats** - Check hit ratio, evictions
11. **check_dependency_health** - Verify connectivity between components

#### Group 4: Completion
12. **finish** - Submit final RCA report

## Integration with v6.txt Prompt

The v6.txt prompt has been updated to:

1. Accept `{{data_dir}}` template variable pointing to telemetry data
2. Document that all RCA tools require `data_dir` parameter
3. Update tool signatures with correct parameters

### Workflow

1. **User provides**: `data_dir="/path/to/simulation/output"`
2. **System runs**: `detect_incident_window(data_dir)` (preprocessing)
3. **System populates** v6.txt template variables:
   - `{{incident_start}}` = 60.0
   - `{{incident_end}}` = 287.87
   - `{{baseline_start}}` = 0.0
   - `{{baseline_end}}` = 60.0
   - `{{symptom_description}}` = "product-catalog OOM crashes"
   - `{{data_dir}}` = "/path/to/simulation/output"
4. **Agent starts** with populated prompt
5. **Agent uses tools** (all tools use data_dir internally)
6. **Agent completes** investigation, calls `finish()`

## Data Format Requirements

### Simulation Data Structure

The SimulationBackend expects the following files in `data_dir`:

#### metrics.jsonl
```json
{"ts": 60000000000, "name": "cache.hit_ratio", "value": 0.98, "labels": {"component": "user_cache"}}
{"ts": 60100000000, "name": "cache.eviction_rate", "value": 10.5, "labels": {"component": "user_cache"}}
```

#### logs.jsonl
```json
{"timestamp": "60.00s", "level": "ERROR", "message": "Cache eviction failed", "attributes": {"component": "user_cache"}}
```

#### traces.jsonl
```json
{"span_id": "abc123", "parent_span_id": null, "name": "cache.get", "start_time_unix_nano": 60000000000, "end_time_unix_nano": 60005000000, "attributes": {"component": "user_cache"}, "status": {"code": "OK"}}
```

#### infra_context.json
```json
{
  "components": {
    "user_cache": {
      "type": "cache",
      "product": "redis",
      "dependencies": ["redis_cluster"],
      "deployment_history": [
        {
          "simulation_time": 57.0,
          "commit_id": "abc123",
          "message": "Deployed v1.2.3"
        }
      ]
    }
  }
}
```

## Design Decisions

### 1. No Hardcoded Incident Windows
Tools accept `reference_time` + `lookback_seconds` instead of explicit incident windows where possible. This makes tools flexible for both post-incident and live mode.

### 2. Simulation-First Design
All tools work perfectly with JSONL simulation data. The SimulationBackend handles:
- Timestamp conversions (nanoseconds → seconds)
- Log timestamp parsing ("60.00s" → 60.0)
- Component extraction from labels/attributes
- Indexing for fast querying

### 3. Statistical Rigor
- Z-scores and p-values for anomaly detection
- Changepoint detection for pattern classification
- Time correlation for deployment changes
- Percentile calculations for latency analysis

### 4. Respects Simulation Data Format
- Reads deployment_history from infra_context.json
- Handles nanosecond timestamps in metrics/traces
- Parses simulation time from log timestamps
- Builds dependency graph from actual trace spans

## Example Usage

### Detecting Incident Window

```python
from rca.tools.incident_detection import detect_incident_window

result = detect_incident_window({
    "data_dir": "/path/to/simulation/output",
    "sensitivity": "high"
})

# Returns:
# {
#   "status": "success",
#   "incident_detected": True,
#   "incident_window": {"start_time": 60.0, "end_time": 287.87, "status": "RESOLVED"},
#   "baseline_window": {"start_time": 0.0, "end_time": 60.0},
#   "symptom_summary": {
#     "primary_symptom_component": "product_catalog_service",
#     "symptom_description": "Memory leak causing OOM crashes",
#     "affected_components": ["product_catalog_service", "api_gateway"]
#   }
# }
```

### Using RCA Tools

```python
from rca.tools.rca_tools import compare_metrics, get_recent_changes

# Compare metrics
result = compare_metrics({
    "component_name": "user_cache",
    "incident_window": [60.0, 287.87],
    "baseline_window": [0.0, 60.0],
    "data_dir": "/path/to/simulation/output"
})

# Get recent changes
changes = get_recent_changes({
    "component_name": "user_cache",
    "reference_time": 60.0,
    "lookback_seconds": 300,
    "data_dir": "/path/to/simulation/output"
})
```

## Future Enhancements

1. **Add ruptures library** for advanced changepoint detection
2. **Add Drain3** for production-grade log template mining
3. **Implement PrometheusBackend** for production Prometheus data
4. **Implement CloudWatchBackend** for AWS CloudWatch data
5. **Add correlation analysis** between different signal types
6. **Implement Bayesian inference** for hypothesis confidence updates
7. **Add causal graph learning** to discover unknown dependencies

## Testing

To test the RCA system with simulation data:

1. Generate simulation data using the simulator
2. Run incident detection:
   ```bash
   python -c "from rca.tools.incident_detection import detect_incident_window; print(detect_incident_window({'data_dir': '/path/to/output'}))"
   ```
3. Test individual tools with the detected windows

## Dependencies

Required:
- Python 3.8+
- No external dependencies for core functionality

Optional (for enhanced features):
- `networkx` - For dependency graph analysis
- `ruptures` - For advanced changepoint detection (future)
- `drain3` - For production log template mining (future)

See `requirements.txt` for details.
