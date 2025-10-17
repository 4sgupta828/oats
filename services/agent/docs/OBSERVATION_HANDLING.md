# Observation Handling Best Practices

## Problem Statement

When tools produce large outputs (logs, metrics, topology data, etc.), naively passing all data through the LLM context:
1. **Wastes tokens** - Large data consumes context unnecessarily
2. **Causes hallucinations** - Truncated previews lead to fabricated data
3. **Breaks workflows** - LLM tries to reconstruct data from memory instead of orchestrating file I/O

## Core Principle

**LLMs should orchestrate, not consume large data**

The LLM acts as a "brain" that directs tools to process data. Intermediate outputs should be treated as **opaque file references**, not content to be memorized.

---

## Solution: File-Based Data Passing

### Tool Design Pattern

All data-heavy tools should support **dual modes**:

```python
# Mode 1: File path (PREFERRED for large data)
generate_topology_visualization(
    title="My Topology",
    input_file="topology.json"  # Tool reads file internally
)

# Mode 2: Inline data (for small datasets only)
generate_topology_visualization(
    title="My Topology",
    nodes=[...],  # Small list passed directly
    edges=[...]
)
```

### Observation Format

When tools detect large output, emit structured metadata:

```
SUCCESS (execute_shell):
📊 LARGE OUTPUT DETECTED:
  - Total: 5130 lines, 227036 chars
  - Full output saved to: /app/temp/output_xyz.txt
  - Summary: 4 namespaces, 2 nodes, 6 services, 15 pods
  - Preview (head 5 lines):
    {...first 5 lines...}
  - Preview (tail 5 lines):
    {...last 5 lines...}
```

**Key components:**
- ✅ File path where full data is saved
- ✅ Summary statistics (counts, types)
- ✅ Head/tail preview (not middle sections)
- ❌ NO attempt to show all data in observation

---

## Strategies for Large Data

### 1. **Sampling Strategy**

When LLM needs to verify data quality, use samples:

```python
# DON'T: Read entire file
logs = read_file("huge_logs.txt")  # 500MB

# DO: Sample-based validation
head_lines = execute_shell("head -20 huge_logs.txt")
tail_lines = execute_shell("tail -20 huge_logs.txt")
line_count = execute_shell("wc -l huge_logs.txt")
error_count = execute_shell("grep -c ERROR huge_logs.txt")

# LLM sees: "20 samples, 500K total lines, 1,234 errors"
# LLM decides: "Looks valid, pass file to log visualization tool"
```

### 2. **Progressive Disclosure**

Only load more data when LLM needs it for decisions:

```python
# Step 1: Get summary
summary = execute_shell("kubectl get pods --no-headers | wc -l")
# Observation: "42 pods"

# Step 2: LLM decides if more info needed
if user_wants_details:
    details = execute_shell("kubectl get pods -o json")
    # Save to file, pass path to visualization tool
```

### 3. **Streaming for Interactive Cases**

For real-time monitoring:

```python
# Don't accumulate all data
# Stream chunks and make decisions per chunk

for chunk in stream_logs():
    if contains_error(chunk):
        alert(chunk)
    # Don't store entire history in context
```

### 4. **Summary Statistics**

Replace large datasets with aggregates:

```python
# Instead of 10,000 metric data points
# Return: {min: 10, max: 100, avg: 55, p50: 54, p95: 89, p99: 97}

# LLM uses summary to decide next steps
# Full data only passed to visualization tools via file
```

---

## Agent Prompt Guidelines

### ✅ DO:

1. **Recognize file references**
   ```
   Observation: "Data saved to /tmp/topology.json (7KB)"
   Next action: generate_topology_visualization(input_file="/tmp/topology.json")
   ```

2. **Use head/tail for validation**
   ```
   Check if data looks valid:
   - head -10 data.json  # See structure
   - tail -10 data.json  # Check completeness
   - jq 'length' data.json  # Count items
   ```

3. **Pass file paths between tools**
   ```
   Tool 1: process_data() → saves to /tmp/processed.json
   Tool 2: visualize(input_file="/tmp/processed.json")
   ```

### ❌ DON'T:

1. **Don't try to memorize large output**
   ```
   ❌ Observation shows 200 lines
   ❌ LLM tries to type out all 200 items from memory
   ✅ LLM should say: "pass the file to next tool"
   ```

2. **Don't reconstruct from preview**
   ```
   ❌ Preview shows pods 1-3
   ❌ LLM invents pods 4-N
   ✅ LLM should read full file if details needed
   ```

3. **Don't request full data unless necessary**
   ```
   ❌ cat 10GB_file.log
   ✅ tail -1000 10GB_file.log | grep ERROR
   ```

---

## Tool-Specific Guidelines

### Metrics Data
- **File format**: `{series: [{name, data: [[ts, val], ...]}], anomalies: [...]}`
- **Observation**: "Series count, total data points, time range, sample values"
- **Never** include all data points in observation

### Topology/Graph Data
- **File format**: `{nodes: [...], edges: [...]}`
- **Observation**: "Node count, edge count, node types summary, sample node IDs"
- **Never** list all nodes/edges in observation

### Logs
- **File format**: `{logs: [{timestamp, level, message, ...}]}`
- **Observation**: "Total lines, error count, time range, head/tail samples"
- **Never** include all log lines in observation

### Traces
- **File format**: `{trace_id, duration, spans: [...]}`
- **Observation**: "Span count, total duration, root service, error spans count"
- **Never** include all span details in observation

---

## Implementation Checklist

For each data-heavy tool:

- [ ] Add `input_file: Optional[str]` parameter
- [ ] Make data parameters optional when `input_file` provided
- [ ] Tool reads and parses file internally when `input_file` used
- [ ] Tool validates file exists and is valid JSON
- [ ] Tool logs file loading (for debugging)
- [ ] Update tool description: "PREFERRED: Use input_file to avoid context bloat"
- [ ] Emit structured observation with file path
- [ ] Emit summary statistics, not full data
- [ ] Include head/tail samples for validation
- [ ] Test with large (>10KB) data files

---

## Monitoring & Debugging

### Detect Context Bloat
```python
# Add to tool observation
print(f"Observation size: {len(observation_text)} chars")
if len(observation_text) > 10000:
    logger.warning("Large observation detected - consider file-based passing")
```

### Detect Hallucination Patterns
```python
# Check if LLM is recreating data
if tool_input_contains_many_items(input_data):
    if not from_file:
        logger.warning("LLM passing inline data - should use input_file")
```

### Audit Token Usage
```python
# Track context consumption per turn
# Alert if one observation uses >5% of context window
```

---

## Example: Correct Workflow

```python
# Turn 1: Get raw data
kubectl_output = execute_shell("kubectl get all -o json")
# Observation: "Data saved to /tmp/k8s_data.json (227KB, 5130 lines)"

# Turn 2: Process data
process_result = execute_shell("python process_topology.py /tmp/k8s_data.json > /tmp/topology.json")
# Observation: "Processed 42 resources → /tmp/topology.json (7KB, 20 nodes, 35 edges)"

# Turn 3: Visualize (LLM just passes file path)
result = generate_topology_visualization(
    title="K8s Cluster Topology",
    input_file="/tmp/topology.json"  # ✅ File path, not data
)
# Tool reads file internally, LLM never sees the 7KB of data
```

---

## FAQ

**Q: When should LLM read the full file?**

A: Only when LLM needs to make decisions based on content:
- Filtering data before visualization
- Detecting patterns or anomalies
- Validating data quality
- Answering specific questions about data

Even then, prefer:
- Sampling (head/tail/random)
- grep/jq for targeted extraction
- Summary statistics

**Q: What if file path is not accessible to next tool?**

A: Ensure tools run in same environment with shared filesystem, OR:
- Use absolute paths
- Tools explicitly document working directory
- Use artifact storage system with stable paths

**Q: How to handle streaming data?**

A: Don't accumulate in memory:
- Process chunks as they arrive
- Emit incremental summaries
- Save snapshots to files
- Pass file references to visualization

**Q: What about small data (<1KB)?**

A: Inline data is fine for:
- Single log entries
- Small config files
- Error messages
- Summary statistics
- <100 items in lists

---

## Success Metrics

- **Token efficiency**: <10% of context used for observations
- **No hallucinations**: Data accuracy = 100% (file-based)
- **Workflow correctness**: Tools consume full data, not truncated previews
- **Performance**: No unnecessary file reads by LLM
