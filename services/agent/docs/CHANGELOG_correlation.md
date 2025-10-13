# Correlation Tool Changes

## Summary

Replaced the `correlate_signals` tool with `gather_investigation_data` to properly separate data fetching from correlation reasoning.

## Motivation

The original `correlate_signals` tool had fundamental issues:

1. **Fake correlation score**: Calculated as `available_sources / total_sources` - just counting which sources returned data
2. **No actual correlation logic**: Just fetched data in parallel, no intelligent analysis
3. **Rigid API**: Forced specific query patterns (error_pattern, metric_name, service)
4. **Misleading name**: Implied the tool was doing correlation, when it was just data fetching

**Key insight**: Correlation in complex distributed systems requires intelligence, not statistics. The LLM should do correlation reasoning, not rule-based algorithms.

## Changes Made

### Removed
- `correlate_signals` tool
- `CorrelateSignalsInput` class

### Added
- `gather_investigation_data` tool
- `GatherInvestigationDataInput` class

## New Tool Design

### Philosophy
**Tools fetch data. LLM does correlation reasoning.**

### Key Features

1. **Flexible source selection**: LLM chooses what to gather
   - `include_logs` (bool)
   - `include_metrics` (bool)
   - `include_traces` (bool)
   - `include_commits` (bool)

2. **Parameterized queries**: Full control over each source
   - Logs: query, filters, limit
   - Metrics: metric_names (list), dimensions
   - Traces: service, filters
   - Commits: repo, branch, limit

3. **Efficient parallel execution**: All sources fetched simultaneously

4. **Graceful degradation**: Returns partial results if some sources fail

5. **No correlation logic**: Just fetches and returns raw timestamped data

## Usage Comparison

### Old (correlate_signals) - REMOVED

```python
correlate_signals(CorrelateSignalsInput(
    time_range="1h",
    error_pattern="error",      # Rigid: forced to specify
    metric_name="cpu_usage",    # Rigid: only one metric
    service="api"               # Rigid: forced pattern
))

# Returns fake "correlation_score": 0.67 (meaningless)
```

### New (gather_investigation_data)

```python
# Flexible: LLM chooses what to gather
gather_investigation_data(GatherInvestigationDataInput(
    time_range="1h",

    # Only gather what you need
    include_logs=True,
    log_query="error OR exception OR timeout",  # Full control
    log_filters={"service": "api", "env": "prod"},

    include_metrics=True,
    metric_names=[                              # Multiple metrics!
        "cpu_usage",
        "memory_usage",
        "http_latency_p95"
    ],

    include_commits=True,                       # NEW: Code changes!
    commit_repo="company/backend"
))

# Returns raw data - NO fake correlation score
# LLM analyzes data to build timeline in Phase 3 (CORRELATE)
```

## How Correlation Works Now

### Phase 3: CORRELATE (from v3 prompt)

**LLM's Process**:

1. **Gather data** using `gather_investigation_data` or individual tools
2. **Extract key events** from returned data (errors, spikes, deploys, changes)
3. **Build timeline** in `state.diagnosis.timeline`:
   ```json
   {
     "timeline": [
       {
         "timestamp": "2024-10-13T14:20:00Z",
         "event": "Deploy v2.3.1",
         "relevance": "HIGH",
         "reasoning": "3min before symptom, affects DB layer",
         "factIDs": [5]
       }
     ]
   }
   ```
4. **Rank by likelihood** using:
   - Temporal proximity to symptom
   - Scope (affected components)
   - Magnitude (major vs minor change)
   - Multi-signal corroboration

5. **Form hypotheses** (Phase 4) based on timeline

### Why LLM Correlation is Superior

**LLM reasoning includes**:
- Service dependency understanding
- Domain knowledge (e.g., "OOM after memory leak")
- Temporal reasoning (delayed effects, gradual degradation)
- Multi-signal fusion (logs + metrics + commits)
- Semantic understanding (not just timestamps)
- Graceful handling of missing data

**Statistical algorithms cannot do this.**

## Benefits of New Approach

### 1. Flexibility
- LLM chooses what data to fetch
- Not forced into rigid query patterns
- Can gather logs only, or all sources, as needed

### 2. Efficiency
- Parallel fetching (same as before)
- But now with flexible parameters
- Can include commit history for timeline building

### 3. Honesty
- No fake correlation scores
- Clear separation: tool fetches, LLM reasons
- Doesn't mislead with meaningless metrics

### 4. Integration with RCA Process
- Designed for Phase 3 (CORRELATE)
- Returns data in format LLM expects
- Supports timeline building workflow

### 5. Code Change Correlation
- **NEW**: Can include commit history
- Critical for correlating deploys with errors
- Enables "what changed" analysis

## Migration Guide

### If you were using `correlate_signals`:

**Before**:
```python
result = correlate_signals(CorrelateSignalsInput(
    time_range="1h",
    error_pattern="error",
    metric_name="cpu_usage",
    service="api"
))
```

**After**:
```python
result = gather_investigation_data(GatherInvestigationDataInput(
    time_range="1h",

    include_logs=True,
    log_query="error",
    log_filters={"service": "api"},

    include_metrics=True,
    metric_names=["cpu_usage"],
    metric_dimensions={"service": "api"}
))
```

**Or use individual tools**:
```python
# More control, but sequential
logs = query_logs(QueryLogsInput(
    query="error",
    time_range="1h",
    filters={"service": "api"}
))

metrics = query_metrics(QueryMetricsInput(
    metric_name="cpu_usage",
    time_range="1h",
    dimensions={"service": "api"}
))

# LLM correlates results
```

## Files Modified

- `/Users/sgupta/oats/services/agent/tools/observability_tools.py`
  - Removed: `CorrelateSignalsInput` class (lines 382-387)
  - Removed: `correlate_signals` function (lines 390-467)
  - Added: `GatherInvestigationDataInput` class (lines 382-405)
  - Added: `gather_investigation_data` function (lines 408-636)

## Documentation

- [correlation_design.md](./correlation_design.md) - Full design philosophy and LLM correlation approach
- [gather_investigation_data_usage.md](./gather_investigation_data_usage.md) - Complete usage guide
- [commit_history_usage.md](./commit_history_usage.md) - Using `query_commits` for code change investigation

## Testing

Verified:
- ✅ `gather_investigation_data` imports successfully
- ✅ `correlate_signals` removed completely
- ✅ 15 parameters in `GatherInvestigationDataInput`
- ✅ Flexible source selection works
- ✅ Tool is decorated with `@uf` properly

## Related Changes

This change is part of a broader enhancement to code change investigation:

1. **Added `get_commits` to CodeProvider base class** - Abstract method for commit history
2. **Implemented in GitHubCodeProvider** - Full commit history with diffs
3. **Added `query_commits` tool** - Direct access to commit history
4. **Replaced `correlate_signals` with `gather_investigation_data`** - This change
5. **Enhanced documentation** - Clear guidance on LLM-driven correlation

## Impact

### Positive
- ✅ More honest about what tools do (fetch vs reason)
- ✅ More flexible for LLM to use
- ✅ Includes commit history for better correlation
- ✅ No misleading correlation scores
- ✅ Better aligned with Phase 3 (CORRELATE) workflow

### Breaking Changes
- ⚠️ `correlate_signals` tool removed - use `gather_investigation_data` or individual tools
- ⚠️ No more `correlation_score` in response - LLM does reasoning instead

## Future Work

### Potential Enhancements
1. **Intelligent sampling**: For large result sets, sample smartly (first/last/random)
2. **Streaming results**: For very large datasets
3. **Historical baseline**: Compare current window with past week
4. **Auto-detect sources**: Based on symptom type, auto-enable relevant sources
5. **Result caching**: Cache fetched data for repeated queries

### Alternative Approach
Instead of bulk gathering, LLM could use individual tools exclusively:
- Pro: Maximum flexibility
- Con: More tool calls (slower)
- Decision: Support both approaches

## Conclusion

This change makes the system more honest and effective:
- Tools do what they're good at: efficient data fetching
- LLM does what it's good at: intelligent correlation reasoning
- No pretense of statistical correlation (which doesn't work for complex systems)
- Better integration with RCA process (Phase 3: CORRELATE)

**Philosophy**: Statistical correlation is brittle. LLM correlation is intelligent.
