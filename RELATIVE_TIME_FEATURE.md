# Relative Time Display Feature

## Overview

The incident detection tool now supports **relative timestamp display** mode, which shows all timestamps as **T+seconds** from the data collection start time. This makes it much easier to understand event sequences without mentally calculating differences between large Unix timestamps.

## Usage

```bash
# Standard mode (absolute timestamps)
python run_incident_detection.py ~/oats/output/data_20251030_124211

# Relative time mode (T+seconds from start)
python run_incident_detection.py ~/oats/output/data_20251030_124211 --relative-time
```

## What Changes

### 1. Timeline Events

**Standard output:**
```
[1] 2025-10-30 12:38:30.000 (ts: 1761853110.00)
    EVENT: Anomaly START
```

**Relative time output:**
```
[1] T+68.5s (2025-10-30 12:38:30.000)
    EVENT: Anomaly START
```

### 2. Causal Relationships

**Standard output:**
```
Cause:  Cluster 6 at 2025-10-30 12:38:50.000
Effect: Cluster 1 at 2025-10-30 12:38:30.000
```

**Relative time output:**
```
Cause:  Cluster 6 at T+88.5s
Effect: Cluster 1 at T+68.5s
```

### 3. Correlation Groups

**Standard output:**
```
Group 1: 5 clusters starting around 2025-10-30 12:38:50.000
```

**Relative time output:**
```
Group 1: 5 clusters starting around T+88.5s
```

## Benefits

### Easy Time Calculations

**Without relative time:**
- First anomaly: 1761853110.00
- Second anomaly: 1761853120.00
- Difference: 1761853120.00 - 1761853110.00 = 10 seconds ❌ (hard to calculate)

**With relative time:**
- First anomaly: T+68.5s
- Second anomaly: T+78.5s
- Difference: 78.5 - 68.5 = 10 seconds ✅ (easy!)

### Clear Event Sequence

Instead of:
```
Event A: 1761853110.00
Event B: 1761853120.00
Event C: 1761853130.00
Event D: 1761853150.00
```

You see:
```
Event A: T+68.5s
Event B: T+78.5s   (10s later)
Event C: T+88.5s   (10s later)
Event D: T+108.5s  (20s later)
```

### Better for RCA

The relative timestamps make it immediately obvious:
- How quickly the incident progressed
- Time gaps between related events
- Propagation delays between components
- Cascading failure patterns

## JSON Output

When using `--relative-time`, the JSON report includes an additional field:

```json
{
  "timeline": [
    {
      "timestamp": 1761853110.0,
      "timestamp_formatted": "2025-10-30 12:38:30.000",
      "timestamp_relative": "T+68.5s",
      "event_type": "anomaly_start",
      ...
    }
  ]
}
```

The report is saved to `incident_detection_report_relative.json` instead of `incident_detection_report.json`.

## Technical Details

### Base Time Calculation

The base time (T+0) is the `start_time` from the `total_data_window`:

```json
{
  "time_windows": {
    "total_data_window": {
      "start_time": 1761853041.512001,  // This is T+0
      "end_time": 1761853326.512001
    }
  }
}
```

All relative timestamps are calculated as:
```
timestamp_relative = current_timestamp - base_time
```

### Fields with Relative Time

When `--relative-time` is enabled, these fields get `*_relative` equivalents:

1. **Timeline events**: `timestamp_relative`
2. **Causal relationship details**: `start_time_relative` (in cause_details and effect_details)
3. **Correlation groups**: `group_start_time_relative`

### Display Format

- Relative timestamps: `T+{seconds}s` (e.g., `T+68.5s`, `T+108.5s`)
- Precision: 1 decimal place (0.1 second precision)
- Always positive (time since data collection started)

## Use Cases

### 1. Quick Incident Analysis
Easily see how fast the incident progressed:
- Primary symptom at T+78.5s
- First cascade at T+108.5s (30s later)
- Full blast radius by T+150s (71.5s total)

### 2. Understanding Causality
Quickly identify time relationships:
- Cause A at T+88.5s
- Effect B at T+68.5s
- → B preceded A by 20s (suggests B is not caused by A)

### 3. Pattern Recognition
Spot recurring time patterns:
- Errors at T+78.5s, T+108.5s, T+138.5s (30s intervals)
- Suggests periodic retry logic or scheduled task

### 4. Correlation Validation
Verify if co-occurring anomalies are truly simultaneous:
- Group shows T+88.5s to T+89.0s (within 0.5s = likely related)
- vs T+88.5s to T+120.5s (32s gap = may not be directly related)

## Example Output

```
SUMMARY
====================================================================================================
Status: incident_detected
Total Anomaly Clusters: 19
Causal Relationships: 3

CHRONOLOGICAL TIMELINE
====================================================================================================
Note: Using relative timestamps (T+seconds from data start)

  [1] T+68.5s (2025-10-30 12:38:30.000)
      EVENT: Anomaly START - request duration DECREASE

  [2] T+78.5s (2025-10-30 12:38:40.000)
      EVENT: Anomaly START - NEW_ERROR (PRIMARY)

  [3] T+88.5s (2025-10-30 12:38:50.000)
      EVENT: Anomaly START - request count INCREASE

CAUSAL RELATIONSHIPS
====================================================================================================

  [1] requests (INCREASE) → duration (DECREASE)
      Cause:  Cluster 6 at T+88.5s
      Effect: Cluster 1 at T+68.5s

CORRELATION GROUPS
====================================================================================================

  Group 1: 2 clusters starting around T+68.5s
  Group 2: 5 clusters starting around T+88.5s
```

## Recommendation

For manual incident analysis and RCA, **use `--relative-time`** for easier comprehension. The absolute timestamps are still included in parentheses for reference if needed.

For automated processing where absolute timestamps matter, use the standard mode or read both the `timestamp` and `timestamp_relative` fields from the JSON.
