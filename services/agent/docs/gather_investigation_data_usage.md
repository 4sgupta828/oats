# gather_investigation_data Tool Usage

## Purpose

Efficiently gather observability signals (logs, metrics, traces, commits) in parallel for a time window. This tool is designed for **Phase 3 (CORRELATE)** of the RCA process, where the LLM needs to build a timeline of events.

**Key Principle**: This tool fetches data efficiently. The LLM performs the intelligent correlation reasoning.

## When to Use

### Use `gather_investigation_data` when:
- You're in Phase 3 (CORRELATE) and need data from multiple sources
- You want efficient parallel fetching to save time
- You need logs + commits together for timeline building
- You want metrics + traces to correlate performance issues

### Use individual tools when:
- You need only one data source (e.g., just logs)
- You want more control over specific query parameters
- You're doing targeted investigation (not building full timeline)
- Tools: `query_logs`, `query_metrics`, `query_traces`, `query_commits`, `search_code`

## Parameters

### Required
- `time_range` (str): Time window for data gathering ('15m', '1h', '24h')

### Data Source Selection (at least one must be True)
- `include_logs` (bool): Gather log data
- `include_metrics` (bool): Gather metric data
- `include_traces` (bool): Gather trace data
- `include_commits` (bool): Gather commit history

### Logs Parameters (required if include_logs=True)
- `log_query` (str): Search query for logs
- `log_filters` (dict, optional): Additional filters like `{'service': 'api'}`
- `log_limit` (int): Max entries (default: 100, max: 500)

### Metrics Parameters (required if include_metrics=True)
- `metric_names` (list[str]): List of metrics to query
- `metric_dimensions` (dict, optional): Dimensions like `{'service': 'api', 'region': 'us-east-1'}`

### Traces Parameters (optional)
- `trace_service` (str, optional): Service name for trace search
- `trace_filters` (dict, optional): Additional filters like `{'error': 'true'}`

### Commits Parameters (required if include_commits=True)
- `commit_repo` (str): Repository name (e.g., 'company/backend')
- `commit_branch` (str): Branch name (default: 'main')
- `commit_limit` (int): Max commits (default: 20, max: 50)

## Response Format

```json
{
  "status": "success",  // or "partial_success" if some sources failed
  "data": {
    "logs": {
      "entries": [...],  // Array of log entries with timestamps
      "count": 150,
      "metadata": {...}
    },
    "metrics": {
      "series": [
        {
          "metric_name": "http_request_duration_seconds",
          "data": [...],  // Time-series data points
          "metadata": {...}
        },
        ...
      ],
      "count": 3
    },
    "traces": {
      "traces": [...],  // Array of traces with timestamps
      "count": 45,
      "metadata": {...}
    },
    "commits": {
      "commits": [...],  // Array of commits with timestamps + diffs
      "count": 8,
      "metadata": {...}
    }
  },
  "metadata": {
    "time_range": "1h",
    "sources_requested": ["logs", "metrics", "commits"],
    "sources_succeeded": ["logs", "commits"],
    "sources_failed": ["metrics"]
  },
  "message": "Gathered 150 log entries, 8 commits from 2/3 sources"
}
```

## Usage Examples

### Example 1: Full Investigation (All Sources)

During Phase 3 (CORRELATE), gather all available signals:

```python
gather_investigation_data(GatherInvestigationDataInput(
    time_range="1h",

    # Logs
    include_logs=True,
    log_query="error OR exception",
    log_filters={"service": "payment-api"},
    log_limit=100,

    # Metrics
    include_metrics=True,
    metric_names=[
        "http_request_duration_seconds",
        "http_requests_total",
        "memory_usage_bytes"
    ],
    metric_dimensions={"service": "payment-api"},

    # Traces
    include_traces=True,
    trace_service="payment-api",
    trace_filters={"error": "true"},

    # Commits
    include_commits=True,
    commit_repo="company/backend",
    commit_branch="production"
))
```

**LLM then analyzes the response to**:
1. Extract timestamps from all data sources
2. Build timeline in `state.diagnosis.timeline`
3. Rank events by relevance (temporal proximity, scope, magnitude)
4. Form hypotheses about causal relationships

### Example 2: Logs + Commits Only

If you only need logs and code changes:

```python
gather_investigation_data(GatherInvestigationDataInput(
    time_range="24h",

    include_logs=True,
    log_query="OOM OR OutOfMemoryError",
    log_limit=200,

    include_commits=True,
    commit_repo="company/backend",
    commit_branch="main"
))
```

### Example 3: Metrics Only

If you just want metrics (though individual `query_metrics` might be better):

```python
gather_investigation_data(GatherInvestigationDataInput(
    time_range="1h",

    include_metrics=True,
    metric_names=[
        "cpu_usage_percent",
        "memory_usage_percent",
        "disk_io_operations"
    ],
    metric_dimensions={"host": "prod-server-01"}
))
```

### Example 4: Error Investigation with Targeted Queries

```python
gather_investigation_data(GatherInvestigationDataInput(
    time_range="15m",

    # Get error logs
    include_logs=True,
    log_query="status:500 OR status:502 OR status:504",
    log_filters={"service": "api-gateway"},

    # Check latency metrics
    include_metrics=True,
    metric_names=["api_latency_p95", "api_latency_p99"],
    metric_dimensions={"service": "api-gateway"},

    # Get recent deploys
    include_commits=True,
    commit_repo="company/api-gateway",
    commit_branch="production"
))
```

## LLM Correlation Workflow

### Step 1: Gather Data

```python
result = gather_investigation_data(GatherInvestigationDataInput(...))
```

### Step 2: Extract Key Events

LLM analyzes `result.data` to identify:
- **Log events**: Error spikes, new error types, pattern changes
- **Metric events**: Spikes, drops, threshold crossings
- **Trace events**: Slow traces, failed operations, dependency issues
- **Commit events**: Deploys, config changes, code modifications

### Step 3: Build Timeline

LLM constructs `state.diagnosis.timeline`:

```json
{
  "timeline": [
    {
      "timestamp": "2024-10-13T14:20:00Z",
      "event": "Deploy v2.3.1 - added caching layer",
      "source": "commits",
      "relevance": "HIGH",
      "reasoning": "3 minutes before symptom, affects data access pattern",
      "factIDs": [5, 7]
    },
    {
      "timestamp": "2024-10-13T14:22:00Z",
      "event": "Cache eviction spike: 50/min → 1500/min",
      "source": "metrics",
      "relevance": "HIGH",
      "reasoning": "1 minute before errors, indicates cache thrashing",
      "factIDs": [8]
    },
    {
      "timestamp": "2024-10-13T14:23:00Z",
      "event": "Error spike: CacheKeyCollisionException",
      "source": "logs",
      "relevance": "HIGH",
      "reasoning": "Symptom onset, directly related to cache",
      "factIDs": [1, 2, 3]
    }
  ]
}
```

### Step 4: Rank by Likelihood

LLM considers:
- **Temporal proximity**: Events closer to symptom are more relevant
- **Scope**: Changes affecting the failing component rank higher
- **Magnitude**: Major changes (DB schema) rank higher than minor (CSS)
- **Multi-signal correlation**: Multiple signals pointing to same cause increase likelihood

### Step 5: Form Hypotheses (Phase 4)

Based on timeline, generate testable theories:

```json
{
  "competingHypotheses": [
    {
      "claim": "Cache key collision in new caching layer causes exceptions",
      "layer": "BUSINESS_LOGIC",
      "likelihood": "HIGH",
      "evidence_for": [
        "Deploy 3min before errors",
        "Cache eviction spike 1min before errors",
        "CacheKeyCollisionException in logs"
      ],
      "discriminator": "Check cache key generation logic in v2.3.1 code"
    }
  ]
}
```

## What This Tool Does NOT Do

### ❌ NO Correlation Logic
The tool does **not** calculate correlation scores or rank events. It just fetches data.

### ❌ NO Timeline Building
The tool does **not** build timelines. That's the LLM's job in Phase 3.

### ❌ NO Hypothesis Generation
The tool does **not** suggest root causes. LLM does this in Phase 4.

### ❌ NO Causal Inference
The tool does **not** infer causality. LLM uses domain knowledge and reasoning.

## Why LLM Correlation is Better

### Statistical Correlation (Naive Approach)
```python
# Rule-based: Brittle and produces false positives
if error_time - commit_time < 1_hour:
    correlation_score = 1.0 - (error_time - commit_time) / 1_hour
```

**Problems**:
- ❌ Ignores scope (unrelated services)
- ❌ Ignores magnitude (CSS vs DB schema)
- ❌ Fixed time window (what about delayed effects?)
- ❌ No multi-signal fusion
- ❌ No domain knowledge

### LLM Correlation (Intelligent Approach)

**Advantages**:
- ✅ Understands service dependencies
- ✅ Knows which changes are high-risk
- ✅ Handles temporal reasoning (delayed effects, gradual degradation)
- ✅ Fuses multiple signals (logs + metrics + commits)
- ✅ Applies domain knowledge ("OOM after memory leak commit")
- ✅ Gracefully handles missing data

## Error Handling

### Partial Success
If some data sources fail, the tool returns `status: "partial_success"`:

```json
{
  "status": "partial_success",
  "data": {
    "logs": {...},
    "commits": {...},
    "metrics": {"error": "Metric provider timeout"}
  },
  "metadata": {
    "sources_succeeded": ["logs", "commits"],
    "sources_failed": ["metrics"]
  }
}
```

LLM can still proceed with available data.

### Complete Failure
If all sources fail:

```json
{
  "status": "error",
  "error": "All data sources failed",
  "details": {...}
}
```

LLM should try individual tools or ask user for help.

## Performance

### Parallel Execution
All queries run in parallel (max 4 workers), reducing total time:
- Sequential: 4 queries × 5s each = 20s
- Parallel: max(5s, 5s, 5s, 5s) = 5s

### Timeouts
Each query has 30s timeout to prevent hanging.

### Result Limits
- Logs: max 500 entries
- Commits: max 50 commits
- Metrics: no limit (but queries are bounded by time_range)
- Traces: no limit

## Comparison with Individual Tools

| Aspect | gather_investigation_data | Individual Tools |
|--------|---------------------------|------------------|
| **Speed** | Fast (parallel) | Slower (sequential) |
| **Flexibility** | Limited to predefined params | Full control |
| **Use Case** | Phase 3 bulk gathering | Targeted investigation |
| **Overhead** | Single tool call | Multiple tool calls |
| **Complexity** | More parameters | Simpler per-call |

**Recommendation**: Use both as appropriate.
- Phase 3 (CORRELATE): Use `gather_investigation_data` for efficiency
- Other phases: Use individual tools for precision

## Implementation Notes

### Key Features
1. **Flexible source selection**: LLM chooses what to fetch
2. **Parallel execution**: Efficient data gathering
3. **Graceful degradation**: Partial success if some sources fail
4. **Validation**: Clear error messages for missing parameters
5. **Structured output**: Consistent format for LLM to parse

### Source Code
Location: `/Users/sgupta/oats/services/agent/tools/observability_tools.py:382-636`

Key design choices:
- ThreadPoolExecutor for parallel queries
- 30s timeout per query to prevent hanging
- Normalize log entries for consistent format
- Multiple metrics queried in parallel
- Clear separation: data in `data`, status in `metadata`

## Future Enhancements

### 1. Sampling for Large Results
If logs return 10K entries, sample intelligently:
- First 100 entries
- Last 100 entries
- Random sample of 100 from middle

### 2. Streaming Results
For very large datasets, stream results instead of buffering:
```python
gather_investigation_data(
    ...,
    streaming=True  # Return iterator
)
```

### 3. Historical Context
Compare current window with historical baseline:
```python
gather_investigation_data(
    time_range="1h",
    baseline_range="7d",  # Compare with past week
    ...
)
```

### 4. Auto-detect Relevant Sources
Based on symptom type, automatically enable relevant sources:
- "500 errors" → logs + metrics + commits
- "slow queries" → logs + traces + metrics
- "OOM" → logs + metrics + commits (memory-related)

## See Also

- [correlation_design.md](./correlation_design.md) - Full design philosophy
- [commit_history_usage.md](./commit_history_usage.md) - Using `query_commits`
- Individual tool documentation: `query_logs`, `query_metrics`, `query_traces`, `search_code`
