# RCA System Installation Guide

## Quick Start

### 1. Install Dependencies

```bash
cd services/agent

# Install core dependencies
pip install networkx>=2.8

# Install statistical analysis libraries
pip install ruptures>=1.1.7 scipy>=1.9.0

# Install log analysis libraries
pip install drain3>=0.9.11 cachetools>=5.0.0

# Or install all at once:
pip install -r rca/requirements.txt
```

### 2. Verify Installation

```bash
cd services/agent

# Verify RCA tools are registered
python -c "from tools.rca_tools_integration import verify_rca_tools; verify_rca_tools()"
```

**Expected Output:**
```
✓ 13 RCA tools available:

Incident Detection:
  - detect_incident_window

Situational Awareness (Phase 0):
  - analyze_blast_radius
  - get_temporal_timeline
  - get_recent_changes

Baseline Comparison (Phase 2):
  - compare_metrics
  - compare_logs
  - compare_traces

Active Validation (Phase 3-4):
  - get_service_dependencies
  - check_instance_health
  - get_database_stats
  - get_cache_stats
  - check_dependency_health

Completion (Phase 5):
  - finish
```

### 3. Run Integration Tests (Optional)

```bash
cd services/agent

# Install pytest if not already installed
pip install pytest

# Run tests
pytest rca/tests/test_integration.py -v
```

---

## Testing with Simulation Data

### 1. Prepare Simulation Data

Ensure your simulation output directory contains:
- `metrics.jsonl` - Time-series metrics
- `logs.jsonl` - Structured logs
- `traces.jsonl` - OpenTelemetry spans
- `infra_context.json` - Topology and deployment history
- `metadata.json` - Simulation metadata

### 2. Detect Incident Window

```python
from rca.tools.incident_detection import detect_incident_window

# Create input
class Input:
    data_dir = "/path/to/simulation/output"
    symptom_hint = None
    lookback_seconds = 300
    sensitivity = "high"  # high, medium, or low

# Run detection
result = detect_incident_window(Input())

print(f"Incident detected: {result['incident_detected']}")
if result['incident_detected']:
    print(f"Incident window: {result['incident_window']}")
    print(f"Baseline window: {result['baseline_window']}")
    print(f"Primary symptom: {result['symptom_summary']['symptom_description']}")
```

### 3. Use RCA Tools

```python
from rca.tools.rca_tools import (
    analyze_blast_radius,
    compare_metrics,
    get_recent_changes
)

# Example: Analyze blast radius
class BlastRadiusInput:
    symptom_component = "product_catalog_service"
    incident_window = [60.0, 287.87]
    data_dir = "/path/to/simulation/output"

blast_radius_result = analyze_blast_radius(BlastRadiusInput())
print(f"Directly affected: {blast_radius_result['directly_affected']}")
print(f"Upstream suspects: {blast_radius_result['upstream_suspects']}")

# Example: Compare metrics
class CompareMetricsInput:
    component_name = "product_catalog_service"
    incident_window = [60.0, 287.87]
    baseline_window = [0.0, 60.0]
    data_dir = "/path/to/simulation/output"

metrics_result = compare_metrics(CompareMetricsInput())
print(f"Anomalous metrics: {len(metrics_result['anomalous_metrics'])}")
for metric in metrics_result['anomalous_metrics'][:3]:  # Show top 3
    print(f"  - {metric['metric_name']}: z-score={metric['z_score']}, pattern={metric['anomaly_pattern']}")

# Example: Get recent changes
class RecentChangesInput:
    component_name = "product_catalog_service"
    reference_time = 60.0
    lookback_seconds = 300
    data_dir = "/path/to/simulation/output"

changes_result = get_recent_changes(RecentChangesInput())
print(f"Changes detected: {len(changes_result['changes_detected'])}")
for change in changes_result['changes_detected']:
    print(f"  - {change['description']} (correlation: {change['correlation_likelihood']})")
```

---

## Integration with Agent Framework

The RCA tools are automatically registered when the agent starts. The tools are available through the `@uf` decorator system.

### Using Tools in Agent Workflow

1. **Preprocessing**: System runs `detect_incident_window` to discover anomaly windows
2. **Template Population**: System populates v6.txt template with:
   - `{{incident_start}}`
   - `{{incident_end}}`
   - `{{baseline_start}}`
   - `{{baseline_end}}`
   - `{{symptom_description}}`
   - `{{data_dir}}`
3. **Agent Investigation**: Agent uses RCA tools following the v6.txt prompt methodology
4. **Completion**: Agent calls `finish()` to submit final report

---

## Troubleshooting

### Issue: Ruptures or Drain3 not available

**Solution**: The system will automatically fall back to heuristic methods. You'll see:
```
INFO | Ruptures library not available - using heuristic changepoint detection
INFO | Drain3 library not available - using heuristic template mining
```

To enable full functionality:
```bash
pip install ruptures scipy drain3 cachetools
```

### Issue: Import errors

**Solution**: Make sure you're in the correct directory:
```bash
cd services/agent
python -c "from tools.rca_tools_integration import verify_rca_tools; verify_rca_tools()"
```

### Issue: No data found

**Solution**: Check that your simulation data directory contains all required files:
```bash
ls /path/to/simulation/output
# Should show: metrics.jsonl, logs.jsonl, traces.jsonl, infra_context.json, metadata.json
```

### Issue: Tests failing

**Solution**: Install test dependencies:
```bash
pip install pytest
cd services/agent
pytest rca/tests/test_integration.py -v
```

---

## Performance Tuning

### Incident Detection Sensitivity

Adjust sensitivity based on your needs:
- **high** (z > 3.0): Detects most anomalies, may have false positives
- **medium** (z > 3.5): Balanced detection
- **low** (z > 4.0): Only very significant anomalies

### Changepoint Detection (Ruptures)

Tune the penalty parameter in `metrics_analyzer.py`:
```python
changepoints = algo.predict(pen=10)  # Lower = more sensitive
```

### Log Template Mining (Drain3)

Tune similarity threshold in `logs_analyzer.py`:
```python
"sim_th": 0.4  # Lower = more strict grouping
```

---

## Directory Structure After Installation

```
services/agent/
├── rca/                           # ✓ Installed
│   ├── backends/                  # ✓ Installed
│   ├── analyzers/                 # ✓ Installed
│   ├── tools/                     # ✓ Installed
│   ├── tests/                     # ✓ Installed
│   └── requirements.txt           # ✓ Installed
├── tools/
│   └── rca_tools_integration.py   # ✓ Installed
├── reactor/
│   └── prompts/
│       └── v6.txt                 # ✓ Updated
└── .oats_artifacts/               # Created on first use
    └── rca_reports/               # RCA reports saved here
```

---

## Verification Checklist

- [ ] Dependencies installed (`pip install -r rca/requirements.txt`)
- [ ] Tool verification passes (`verify_rca_tools()`)
- [ ] Integration tests pass (optional)
- [ ] Can import RCA modules from Python
- [ ] Simulation data directory available
- [ ] Can run incident detection
- [ ] Can use RCA tools

---

## Need Help?

1. Check the [README.md](services/agent/rca/README.md) for comprehensive documentation
2. Review the [RCA_IMPLEMENTATION_SUMMARY.md](RCA_IMPLEMENTATION_SUMMARY.md) for architecture details
3. Look at [PLAN.md](PLAN.md) for design decisions
4. Examine [TOOLS_DESIGN.md](TOOLS_DESIGN.md) for tool specifications

---

**Installation Status**: ✅ Ready to use with simulation data
