# Incident Detection Tool - Comprehensive RCA Report Guide

## Quick Start

Run incident detection on any simulation dataset:

```bash
python run_incident_detection.py ~/oats/output/data_YYYYMMDD_HHMMSS
```

## Output Files

The tool generates two JSON files in the data directory:

1. **`incident_detection_raw.json`** - Raw output from the detection tool
2. **`incident_detection_report.json`** - Comprehensive structured report for RCA

## Comprehensive Report Structure

The comprehensive report (`incident_detection_report.json`) provides everything the RCA tool needs:

### 1. **Summary**
```json
{
  "summary": {
    "status": "incident_detected",
    "analyzer_version": "v3",
    "v3_features_enabled": {...},
    "total_anomaly_clusters": 19,
    "affected_components": [...],
    "affected_component_count": 6,
    "causal_relationships_found": 3,
    "correlation_groups_found": 6
  }
}
```

### 2. **Time Windows** (Complete temporal context)
```json
{
  "time_windows": {
    "total_data_window": {
      "start_time": 1761853041.512001,
      "end_time": 1761853326.512001,
      "start_time_formatted": "2025-10-30 12:37:21.512",
      "end_time_formatted": "2025-10-30 12:42:06.512",
      "duration_seconds": 285.0,
      "duration_formatted": "4.8m (285.0s)"
    },
    "baseline_windows": [
      {
        "window_id": 1,
        "start_time": ...,
        "end_time": ...,
        "duration_seconds": 70.0,
        "quality": "poor",
        "stability_score": 0.0,
        "samples": 7,
        "detection_method": "heuristic"
      }
    ],
    "incident_windows": [
      {
        "window_id": 1,
        "start_time": ...,
        "end_time": ...,
        "duration_seconds": 188.5,
        "status": "RESOLVED",
        "anomaly_cluster_count": 19
      }
    ]
  }
}
```

### 3. **Primary Symptom** (Root cause candidate)
```json
{
  "primary_symptom": {
    "cluster_id": 2,
    "component": "aws_instance.product_compute_1_vprod_cat",
    "metric": "component.errors.total",
    "pattern": "SPIKE",
    "direction": "NEW_ERROR",
    "severity": "HIGH",
    "z_score": 10.0,
    "start_time": 1761853120.0,
    "start_time_formatted": "2025-10-30 12:38:40.000",
    "description": "..."
  }
}
```

### 4. **Timeline** (Chronological sequence of all anomaly events)
```json
{
  "timeline": [
    {
      "cluster_id": 1,
      "timestamp": 1761853110.0,
      "timestamp_formatted": "2025-10-30 12:38:30.000",
      "event_type": "anomaly_start",
      "component": "aws_lb.api_gateway",
      "metric": "http.server.request.duration",
      "direction": "DECREASE",
      "pattern": "SUSTAINED_DECREASE",
      "severity": "HIGH",
      "relationship": "CORRELATED",
      "peak_z_score": -197.63,
      "confidence": 1.0,
      "detection_methods": ["z_score", "z_score+multivariate"]
    },
    {
      "event_type": "anomaly_end",
      "timestamp": 1761853290.0,
      "duration": 180.0
    }
  ]
}
```

### 5. **Anomaly Clusters** (All detected anomalies)

#### 5.1 All Clusters (sorted chronologically)
```json
{
  "anomaly_clusters": {
    "all_clusters": [...]
  }
}
```

#### 5.2 By Relationship Type
```json
{
  "by_relationship": {
    "PRIMARY": [...],        // The root cause anomaly
    "CASCADING": [...],      // Anomalies that happened after primary
    "CORRELATED": [...],     // Anomalies that co-occurred with primary
    "SECONDARY_SYMPTOM": [...] // Effects that appeared later
  }
}
```

#### 5.3 By Component
```json
{
  "by_component": {
    "aws_lb.api_gateway": [...],
    "product_catalog_service.product_catalog": [...]
  }
}
```

### 6. **Relationships** (How anomalies relate to each other)

#### 6.1 Causal Relationships (Granger Causality)
```json
{
  "relationships": {
    "causal_relationships": [
      {
        "cause_cluster_id": 6,
        "effect_cluster_id": 1,
        "granger_p_value": 0.0457,
        "confidence": 0.95,
        "lag_buckets": 1,
        "cause_details": {
          "component": "aws_lb.api_gateway",
          "metric": "http.server.requests",
          "direction": "INCREASE",
          "start_time": 1761853130.0,
          "start_time_formatted": "2025-10-30 12:38:50.000"
        },
        "effect_details": {
          "component": "aws_lb.api_gateway",
          "metric": "http.server.request.duration",
          "direction": "DECREASE",
          "start_time": 1761853110.0,
          "start_time_formatted": "2025-10-30 12:38:30.000"
        },
        "interpretation": "aws_lb.api_gateway.http.server.requests (INCREASE) → aws_lb.api_gateway.http.server.request.duration (DECREASE)"
      }
    ]
  }
}
```

#### 6.2 Correlation Groups (Co-occurring anomalies)
```json
{
  "correlation_groups": [
    {
      "group_start_time": 1761853130.0,
      "group_start_time_formatted": "2025-10-30 12:38:50.000",
      "time_window": 10,  // seconds
      "cluster_count": 5,
      "clusters": [
        {
          "cluster_id": 6,
          "component": "aws_lb.api_gateway",
          "metric": "http.server.requests",
          "direction": "INCREASE",
          "severity": "HIGH",
          "relationship": "CORRELATED"
        }
      ]
    }
  ]
}
```

#### 6.3 Cascading Chain
```json
{
  "cascading_chain": [
    {
      "cluster_id": 15,
      "component": "aws_instance.product_compute_3_vprod_cat",
      "metric": "component.errors.total",
      "direction": "NEW_ERROR",
      "start_time": 1761853150.0,
      "start_time_formatted": "2025-10-30 12:39:10.000",
      "delay_from_primary_seconds": 30.0
    }
  ]
}
```

## Key Features for RCA

### 1. **Complete Temporal Context**
- Total data window with exact timestamps
- Baseline window(s) with quality metrics
- Incident window(s) with status (ACTIVE/RESOLVED)
- All durations in both seconds and human-readable format

### 2. **Anomaly Classification**
Every anomaly includes:
- **Direction**: INCREASE, DECREASE, NEW_ERROR
- **Pattern**: SPIKE, STEP_CHANGE, SUSTAINED_INCREASE, SUSTAINED_DECREASE
- **Relationship**: PRIMARY, CASCADING, CORRELATED, SECONDARY_SYMPTOM
- **Confidence score**: 0-1 (from detection methods)
- **Detection methods**: z_score, mad, iqr, percentile, multivariate

### 3. **Causal Analysis**
- Granger causality tests between anomaly clusters
- Confidence scores and p-values
- Time lags between cause and effect
- Full details of both cause and effect anomalies

### 4. **Correlation Analysis**
- Groups of anomalies that co-occurred (within 10s window)
- Helps identify which metrics changed together
- Useful for understanding blast radius

### 5. **Timeline View**
- Chronological sequence of every anomaly start/end event
- Makes it easy to see the order of events
- Includes all metadata for each event

### 6. **Component Grouping**
- All anomalies grouped by component
- Helps identify which services/instances were affected
- Shows blast radius and propagation pattern

## V3 Advanced Features

All enabled by default:

1. **Bayesian Online Changepoint Detection (BOCD)**
   - Adaptive baseline detection using Student-t distribution
   - More accurate than simple threshold-based methods

2. **Multivariate Anomaly Detection**
   - Isolation Forest detects complex multi-metric anomalies
   - Finds anomalies that standard methods miss

3. **Granger Causality Analysis**
   - Statistical causality testing between metric time series
   - Identifies which metrics caused changes in others

4. **Seasonality Detection**
   - FFT-based periodic pattern detection
   - Removes seasonal effects to reduce false positives

## RCA Tool Usage

The RCA tool should use this report to:

1. **Start with Primary Symptom**: Focus investigation on the root cause candidate
2. **Follow Causal Relationships**: Trace back from effects to causes
3. **Check Timeline**: Understand sequence of events
4. **Examine Correlation Groups**: See what changed together
5. **Track Cascading Effects**: Follow the failure propagation
6. **Use Component Grouping**: Identify affected services

## Example RCA Workflow

```python
# Load comprehensive report
with open('incident_detection_report.json') as f:
    report = json.load(f)

# 1. Get primary symptom
primary = report['primary_symptom']
print(f"Root cause candidate: {primary['component']}.{primary['metric']}")
print(f"Direction: {primary['direction']}, Pattern: {primary['pattern']}")

# 2. Get timeline to understand sequence
timeline = report['timeline']
print(f"First anomaly at: {timeline[0]['timestamp_formatted']}")

# 3. Check causal relationships
for rel in report['relationships']['causal_relationships']:
    print(f"Causality: {rel['interpretation']}")
    print(f"  Confidence: {rel['confidence']:.2%}")

# 4. Get all PRIMARY and CASCADING anomalies
primary_anomalies = report['anomaly_clusters']['by_relationship']['PRIMARY']
cascading = report['anomaly_clusters']['by_relationship']['CASCADING']

# 5. Check which components were affected
affected = report['summary']['affected_components']
print(f"Affected components: {len(affected)}")

# 6. Look at correlation groups to see co-occurring changes
for group in report['relationships']['correlation_groups']:
    print(f"Group of {group['cluster_count']} anomalies at {group['group_start_time_formatted']}")
```

## Configuration Options

You can customize detection parameters:

```python
from rca.tools.incident_detection import detect_incident_window, DetectIncidentWindowInput

inputs = DetectIncidentWindowInput(
    data_dir="/path/to/data",
    sensitivity="high",  # high, medium, or low
    enable_bayesian_changepoint=True,
    enable_multivariate=True,
    enable_causality=True,
    enable_seasonality=True,
    enable_streaming=False  # For very large datasets
)

result = detect_incident_window(inputs)
```

## Output Format Summary

**Human-readable console output** includes:
- Summary with key metrics
- Time windows (total, baseline, incident)
- Primary symptom details
- Complete timeline with all events
- Anomalies grouped by relationship type
- Causal relationships with interpretations
- Correlation groups
- Anomalies grouped by component

**JSON report** (`incident_detection_report.json`) contains:
- All of the above in structured format
- Ready for programmatic consumption by RCA tool
- All timestamps in both Unix and formatted datetime
- All durations in both seconds and human-readable
- Complete metadata for every anomaly

## Questions?

The report is designed to give the RCA tool complete visibility into:
- **What happened**: All anomalies detected
- **When it happened**: Exact timeline of events
- **Where it happened**: Components and metrics affected
- **How it spread**: Causal and correlation relationships
- **What to investigate**: Primary symptom and cascading effects
