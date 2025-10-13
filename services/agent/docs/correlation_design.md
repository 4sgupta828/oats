# Correlation Design: LLM-Driven Intelligence

## Philosophy

**Core Principle**: Statistical correlation algorithms are brittle and produce false positives in complex distributed systems. Instead, we use the LLM's reasoning capabilities to perform sophisticated correlation analysis.

## Current Architecture

### The REACT Loop (from v3 prompt)

```
Phase 1: TRIAGE       → Classify symptom into layer
Phase 2: ORIENT       → Map architecture & dependencies
Phase 3: CORRELATE    → Find what changed (LLM builds timeline)
Phase 4: HYPOTHESIZE  → Form testable theories
Phase 5: ISOLATE      → Test hypotheses bottom-up
Phase 6: IDENTIFY     → Trace to root cause
Phase 7: VERIFY       → Fix and confirm recovery
```

### Correlation in Phase 3

The LLM is responsible for:
1. **Gathering signals** across all data sources
2. **Extracting timestamps** from events
3. **Building timeline** of changes
4. **Ranking by likelihood** based on:
   - Temporal proximity to symptom
   - Affected components
   - Change magnitude
   - Historical patterns
5. **Outputting structured timeline** to `state.diagnosis.timeline`

## Why LLM-Driven Correlation Works

### Advantages Over Statistical Methods

1. **Context-aware reasoning**
   - Understands service dependencies
   - Knows which changes are high-risk (DB schema vs CSS)
   - Recognizes deployment patterns

2. **Temporal reasoning**
   - "Deploy happened 3min before errors" → HIGH relevance
   - "Config change 2 days ago" → LOW relevance (unless other signals point to it)
   - Can handle delayed effects (cache TTL, gradual degradation)

3. **Multi-signal fusion**
   - Correlates logs + metrics + commits together
   - Example: "Error spike + memory increase + commit adding cache" → likely culprit

4. **Handles missing data gracefully**
   - If metrics unavailable, still correlates logs + commits
   - Statistical methods fail with missing data

5. **Domain knowledge**
   - Knows "OOM errors" + "memory leak in Java" likely related
   - Understands semantic relationships between events

### Example: LLM Correlation Reasoning

**Scenario**: API 504 errors starting at 14:23

**Signals gathered**:
- Logs: 504 errors starting 14:23
- Metrics: DB query latency jumped from 50ms → 5000ms at 14:22
- Commits: Deploy v2.3.1 at 14:20 (added new query)
- Commits: CSS change at 10:00 (unrelated)

**LLM reasoning** (Phase 3: CORRELATE):
```json
{
  "timeline": [
    {
      "timestamp": "14:20:00",
      "event": "Deploy v2.3.1 - added getUsersWithOrders query",
      "relevance": "HIGH",
      "reasoning": "3min before symptom, affects DB queries",
      "factIDs": [2, 5]
    },
    {
      "timestamp": "14:22:00",
      "event": "DB query latency spike 50ms → 5000ms",
      "relevance": "HIGH",
      "reasoning": "1min before errors, directly impacts API response time",
      "factIDs": [3]
    },
    {
      "timestamp": "10:00:00",
      "event": "CSS styling change to navbar",
      "relevance": "LOW",
      "reasoning": "4h before, frontend only, no backend impact",
      "factIDs": [1]
    }
  ]
}
```

**Correlation output**: Deploy v2.3.1 → DB query latency → 504 errors (3-hop causal chain)

## Tool Design: gather_investigation_data

### Purpose
A **data gathering helper** (not a correlator) that fetches all relevant signals in a time window.

### What It Does
- Fetches logs, metrics, traces, commits **in parallel**
- Returns **raw, timestamped data**
- NO correlation logic - just efficient data retrieval

### What It Doesn't Do
- ❌ Calculate correlation scores
- ❌ Rank events by relevance
- ❌ Build timelines
- ❌ Make causal inferences

**Rationale**: LLM does the intelligent work. Tool just fetches data efficiently.

### Proposed API

```python
class GatherInvestigationDataInput(UfInput):
    """Gather all observability signals for a time window"""
    time_window: str = Field(..., description="Time range: '15m', '1h', '24h'")
    service: Optional[str] = Field(None, description="Service name to focus on")
    repo: Optional[str] = Field(None, description="Repository to check for commits")
    include_logs: bool = Field(default=True, description="Fetch logs")
    include_metrics: bool = Field(default=True, description="Fetch key metrics")
    include_traces: bool = Field(default=True, description="Fetch traces")
    include_commits: bool = Field(default=True, description="Fetch commit history")
    log_filter: Optional[str] = Field(None, description="Optional log search pattern")


@uf(name="gather_investigation_data", version="1.0.0",
   description="Efficiently gather all observability signals (logs, metrics, traces, commits) for a time window. Returns raw timestamped data for LLM to correlate.")
def gather_investigation_data(inputs: GatherInvestigationDataInput) -> dict:
    """
    Fetch data from all sources in parallel.
    LLM will analyze the results to build timeline and correlate events.
    """
    # Fetch in parallel
    # Return structured data with timestamps
    # NO correlation logic
```

### Response Format

```json
{
  "status": "success",
  "time_window": "1h",
  "data": {
    "logs": {
      "entries": [...],  // with timestamps
      "metadata": {...}
    },
    "metrics": {
      "series": [...],   // with timestamps
      "metadata": {...}
    },
    "traces": {
      "traces": [...],   // with timestamps
      "metadata": {...}
    },
    "commits": {
      "commits": [...],  // with timestamps + diffs
      "metadata": {...}
    }
  },
  "message": "Gathered 150 log entries, 12 metric points, 45 traces, 8 commits"
}
```

## Correlation Workflow

### Phase 3: CORRELATE

**LLM's process**:

1. **Gather data**
   ```python
   gather_investigation_data(GatherInvestigationDataInput(
       time_window="1h",
       service="payment-api",
       repo="company/backend",
       log_filter="error OR exception"
   ))
   ```

2. **Extract key events** from returned data
   - Parse timestamps
   - Identify significant events (errors, spikes, deploys, config changes)

3. **Build timeline** in `state.diagnosis.timeline`
   ```json
   {
     "timeline": [
       {"timestamp": "...", "event": "...", "relevance": "HIGH|MEDIUM|LOW", "factIDs": [...]},
       ...
     ]
   }
   ```

4. **Rank by likelihood**
   - Temporal proximity to symptom
   - Magnitude of change
   - Affected components
   - Domain knowledge (e.g., "OOM after memory leak commit")

5. **Form hypotheses** (Phase 4)
   - Use timeline to generate testable theories
   - Example: "Hypothesis: Missing index in v2.3.1 causes slow queries"

### Alternative: Individual Tool Calls

LLM can also call tools individually:

```python
# 1. Check recent commits
query_commits(QueryCommitsInput(
    repo="company/backend",
    since="1h",
    branch="production"
))

# 2. Check error logs
query_logs(QueryLogsInput(
    query="level:ERROR",
    time_range="1h",
    filters={"service": "payment-api"}
))

# 3. Check latency metrics
query_metrics(QueryMetricsInput(
    metric_name="http_request_duration_seconds",
    time_range="1h",
    dimensions={"service": "payment-api"}
))

# LLM analyzes results and builds timeline
```

**Tradeoff**:
- Individual calls: More flexible, LLM controls exactly what to fetch
- Bulk gather: More efficient (parallel), but less flexible

**Recommendation**: Support both. Individual tools for targeted investigation, bulk gather for Phase 3 CORRELATE.

## Handling False Positives

### How LLM Avoids False Positives

1. **Temporal filtering**
   - Changes days old are usually not relevant (unless symptom is chronic)
   - Focus on changes near symptom start time

2. **Scope filtering**
   - Frontend changes don't affect backend errors
   - Changes to unrelated services are ruled out

3. **Magnitude filtering**
   - Small config tweaks less likely than major deploys
   - CSS changes less risky than DB schema changes

4. **Multiple signal requirement**
   - Single correlation is weak ("post hoc ergo propter hoc")
   - Multiple signals strengthen hypothesis:
     - Deploy + error spike = weak
     - Deploy + error spike + latency spike = strong
     - Deploy + error spike + latency spike + memory increase = very strong

5. **Hypothesis testing** (Phase 5: ISOLATE)
   - Correlation suggests hypothesis
   - Must TEST hypothesis with evidence
   - Example: "If missing index is root cause, query plan should show Seq Scan"

### Example: Rejecting False Positive

**Scenario**: Deploy at 10:00, errors at 14:00

**Weak correlation**:
```
Timeline:
- 10:00: Deploy v2.3.1
- 14:00: Error spike

Correlation: 4h gap → relevance=LOW
```

**LLM reasoning**:
"Deploy was 4 hours ago. If it caused errors, we'd see them sooner. More likely: recent change (traffic spike? data issue?) or gradual degradation (memory leak?)."

**Next steps**:
- Check for changes closer to 14:00
- Check if traffic increased at 14:00
- Check memory/CPU trends over 4 hours

## Comparison: Rule-Based vs LLM Correlation

### Rule-Based Approach (Brittle)

```python
# Naive statistical correlation
def correlate(errors, commits):
    for commit in commits:
        for error in errors:
            time_diff = error.timestamp - commit.timestamp
            if 0 < time_diff < 1_hour:
                score = 1.0 - (time_diff / 1_hour)
                yield (commit, error, score)
```

**Problems**:
- ❌ Ignores scope (unrelated services)
- ❌ Ignores magnitude (CSS vs DB schema)
- ❌ Fixed time window (what if delayed effect?)
- ❌ No multi-signal fusion
- ❌ No domain knowledge

### LLM Approach (Intelligent)

**LLM sees**:
```json
{
  "commits": [
    {"time": "10:00", "message": "Add caching layer", "files": ["cache.py", "config.yaml"]},
    {"time": "13:50", "message": "Fix CSS navbar", "files": ["styles.css"]}
  ],
  "errors": [
    {"time": "14:00", "level": "ERROR", "message": "Cache key collision: user_123"}
  ],
  "metrics": [
    {"time": "14:00", "metric": "cache_evictions", "value": 1500}  // spike!
  ]
}
```

**LLM reasoning**:
"Cache-related error at 14:00. CSS change at 13:50 is irrelevant (frontend only). Cache deployment at 10:00 is 4h before, but cache_evictions metric spiked at exactly 14:00. Hypothesis: Cache reached capacity threshold (possibly due to gradual fill-up since 10:00 deployment). TEST: Check cache size limits and current usage."

**Why this works**:
- ✅ Contextual reasoning (cache vs CSS)
- ✅ Multi-signal fusion (errors + metrics)
- ✅ Temporal reasoning (gradual vs immediate)
- ✅ Domain knowledge (cache capacity issues)
- ✅ Generates testable hypothesis

## Implementation Recommendations

### 1. Keep Individual Tools
- `query_logs`
- `query_metrics`
- `query_traces`
- `query_commits`
- `search_code`

**Rationale**: LLM can use these flexibly for targeted investigation

### 2. Add Bulk Gather Helper (Optional)
- `gather_investigation_data` for efficient Phase 3 CORRELATE

**Rationale**: Parallel fetching saves time when LLM needs everything

### 3. Remove Current `correlate_signals`
- Fake correlation score misleads LLM
- Rigid API limits flexibility
- No value over individual tools

### 4. Enhance Tool Outputs
- **Always include timestamps** in returned data
- Standardize timestamp format (ISO 8601)
- Include timezone information
- Example:
  ```json
  {
    "data": [
      {"timestamp": "2024-10-13T14:23:15Z", "message": "...", ...},
      ...
    ]
  }
  ```

### 5. LLM Prompt Guidance
Update prompt to emphasize:
- "Build timeline by extracting timestamps from tool results"
- "Rank events by temporal proximity, scope, and magnitude"
- "Require multiple corroborating signals before high confidence"
- "Test correlation hypotheses with evidence (Phase 5: ISOLATE)"

## Measuring Success

### Good Correlation
- ✅ Identifies actual root cause within top 3 timeline events
- ✅ Rejects unrelated changes (CSS when backend fails)
- ✅ Handles missing data gracefully
- ✅ Builds causal chain with evidence

### Bad Correlation
- ❌ Blames every recent commit
- ❌ Suggests unrelated changes
- ❌ Fails when one data source unavailable
- ❌ No evidence chain, just correlation

## Future Enhancements

### 1. Historical Pattern Learning
LLM could reference past incidents:
"Last time we saw 504 + DB latency, root cause was missing index (incident-2024-09-15)"

### 2. Confidence Scoring
LLM already tracks confidence in `state.diagnosis.confidence`:
```json
{
  "confidence": {
    "problem_definition": "HIGH",
    "root_cause_identified": "MEDIUM",
    "fix_will_work": "HIGH"
  }
}
```

### 3. Change Impact Analysis
Before deploy, predict impact:
"This commit changes DB schema → HIGH risk for performance issues"

### 4. Causal Graph Visualization
Export `state.diagnosis.causalChain` as graph:
```
Missing Index → Slow Query → Timeout → 504 Error
```

## Conclusion

**Key Insight**: Correlation in complex systems requires intelligence, not statistics. The LLM's reasoning capabilities far exceed any rule-based algorithm.

**Design Principle**: Tools fetch data efficiently. LLM does the intelligent correlation reasoning.

**Current Status**:
- ✅ Individual tools work well (`query_logs`, `query_metrics`, `query_commits`)
- ✅ LLM prompt guides correlation in Phase 3
- ⚠️ `correlate_signals` tool is misleading (fake score)
- 🔧 Need to ensure all tools return timestamps consistently

**Recommendation**: Remove `correlate_signals` or redesign as `gather_investigation_data` (bulk fetch only, no correlation logic).
