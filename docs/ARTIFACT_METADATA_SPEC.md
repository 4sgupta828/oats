# Universal Artifact Metadata Specification v1.0

## Overview

This document describes the universal artifact metadata format used by all OATS agent tools. The LLM produces structured data with rich metadata hints, and the UI uses these hints to automatically detect content types and offer appropriate visualization options to users.

**Key Design Principles:**
1. **LLM produces data, not visualizations** - The LLM is decoupled from visualization tool selection
2. **UI controls visualization** - Users select from a dropdown of appropriate visualizations
3. **Universal format** - All tools (observability, code, shell, etc.) use the same metadata schema
4. **No hallucination** - LLM only needs to produce structured data, not make visualization tool calls

## Artifact Metadata Schema

### Top-Level Structure

```json
{
  "artifact_version": "1.0",
  "content_type": "logs",
  "timestamp": "2025-10-17T12:34:56Z",
  "source_tool": "query_logs",
  "suggested_visualizations": ["logs_viewer", "timeline", "table"],
  "visualization_hints": {
    "default_view": "logs_viewer",
    "supports_search": true,
    "supports_filtering": true,
    "time_field": "timestamp",
    "level_field": "level",
    "message_field": "message",
    "highlight_patterns": ["error", "exception", "timeout"]
  },
  "metadata": {
    "provider": "cloudwatch",
    "query": "error AND service:api",
    "time_range": "1h",
    "total_logs": 150
  },
  "data": {
    "logs": [ /* actual log data */ ],
    "query": "...",
    "time_range": "..."
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_version` | string | Yes | Metadata schema version (currently "1.0") |
| `content_type` | string | Yes | Type of content (see Content Types below) |
| `timestamp` | string | Yes | ISO 8601 timestamp when artifact was created |
| `source_tool` | string | Yes | Name of the tool that produced this artifact |
| `suggested_visualizations` | array[string] | Yes | List of appropriate visualization types |
| `visualization_hints` | object | Yes | Hints for rendering visualizations |
| `metadata` | object | Yes | Tool-specific contextual metadata |
| `data` | any | Yes | The actual data (structure varies by content_type) |

## Content Types

### Observability Data

#### `logs`
**Suggested Visualizations:** logs_viewer, timeline, table

**Data Structure:**
```json
{
  "data": {
    "logs": [
      {
        "timestamp": "2025-10-17T12:00:00Z",
        "level": "ERROR",
        "message": "Connection timeout to database",
        "service": "api-gateway",
        "...": "..."
      }
    ],
    "query": "error AND service:api",
    "time_range": "1h"
  }
}
```

**Visualization Hints:**
- `time_field`: Field containing timestamp
- `level_field`: Field containing log level (ERROR, WARN, INFO, etc.)
- `message_field`: Field containing log message
- `highlight_patterns`: Patterns to highlight in UI

#### `metrics`
**Suggested Visualizations:** timeseries, heatmap, table

**Data Structure:**
```json
{
  "data": {
    "series": [
      {
        "name": "cpu_utilization",
        "data": [
          {"timestamp": "2025-10-17T12:00:00Z", "value": 45.2},
          {"timestamp": "2025-10-17T12:01:00Z", "value": 47.8}
        ],
        "aggregation": "avg"
      }
    ],
    "time_range": "1h"
  }
}
```

**Visualization Hints:**
- `y_axis_label`: Label for Y axis
- `aggregation_type`: Type of aggregation (avg, sum, p95, etc.)
- `chart_type`: Suggested chart type (line, bar, area)
- `show_legend`: Whether to show legend

#### `traces`
**Suggested Visualizations:** trace_waterfall, trace_flamegraph, table

**Data Structure:**
```json
{
  "data": {
    "traces": [
      {
        "traceId": "abc123",
        "spans": [
          {
            "spanId": "span1",
            "operationName": "GET /api/users",
            "startTime": 1234567890,
            "duration": 125,
            "tags": {"http.status_code": 200}
          }
        ],
        "duration": 250
      }
    ],
    "service": "api-gateway",
    "time_range": "1h"
  }
}
```

**Visualization Hints:**
- `duration_field`: Field containing duration
- `span_hierarchy`: Whether spans have parent-child relationships
- `show_timeline`: Show timeline view
- `highlight_errors`: Highlight spans with errors

#### `topology`
**Suggested Visualizations:** graph_hierarchical, graph_force_directed, graph_circular, table

**Data Structure:**
```json
{
  "data": {
    "nodes": [
      {"id": "service-1", "label": "API Gateway", "type": "service"},
      {"id": "service-2", "label": "Database", "type": "database"}
    ],
    "edges": [
      {"source": "service-1", "target": "service-2", "weight": 100}
    ]
  }
}
```

**Visualization Hints:**
- `layout_algorithm`: Suggested layout (hierarchical, force, circular)
- `node_types`: Types of nodes in graph
- `edge_weight_field`: Field representing edge weight

### Code and Version Control

#### `code`
**Suggested Visualizations:** code_viewer, table

**Data Structure:**
```json
{
  "data": {
    "matches": [
      {
        "file": "src/api/users.py",
        "line": 45,
        "content": "logger.error('Failed to connect')",
        "context": "..."
      }
    ],
    "query": "logger.error",
    "repo": "myorg/myapp"
  }
}
```

**Visualization Hints:**
- `language`: Programming language for syntax highlighting
- `show_line_numbers`: Whether to show line numbers

#### `diff`
**Suggested Visualizations:** diff_viewer, side_by_side, unified

**Data Structure:**
```json
{
  "data": {
    "file": "src/api/users.py",
    "additions": 15,
    "deletions": 8,
    "changes": [
      {"line": 45, "type": "addition", "content": "+    logger.error('Failed')"}
    ]
  }
}
```

**Visualization Hints:**
- `added_lines`: Number of lines added
- `removed_lines`: Number of lines removed
- `syntax_language`: Language for syntax highlighting

#### `commits`
**Suggested Visualizations:** commit_list, timeline, table

**Data Structure:**
```json
{
  "data": {
    "commits": [
      {
        "sha": "abc123",
        "author": "John Doe",
        "timestamp": "2025-10-17T10:00:00Z",
        "message": "Fix database connection",
        "files_changed": 3
      }
    ],
    "repo": "myorg/myapp",
    "branch": "main"
  }
}
```

**Visualization Hints:**
- `show_diffs`: Whether commit diffs are included
- `time_field`: Field for timeline visualization

### Generic Data Formats

#### `json`
**Suggested Visualizations:** json_viewer, tree_viewer, table

**Visualization Hints:**
- `schema_hints`: Optional JSON schema information
- `collapsible`: Whether to allow collapsing nested structures

#### `yaml`
**Suggested Visualizations:** yaml_viewer, tree_viewer, text_viewer

#### `text`
**Suggested Visualizations:** text_viewer, markdown_viewer

#### `markdown`
**Suggested Visualizations:** markdown_viewer, text_viewer

#### `table`
**Suggested Visualizations:** table, grid, csv_export

**Visualization Hints:**
- `columns`: Column definitions
- `sortable`: Whether columns are sortable
- `filterable`: Whether table supports filtering

#### `csv`
**Suggested Visualizations:** table, grid, chart

**Visualization Hints:**
- `delimiter`: CSV delimiter (usually ",")
- `has_header`: Whether first row is header

### Flows and Timelines

#### `timeline`
**Suggested Visualizations:** timeline, gantt, table

**Data Structure:**
```json
{
  "data": {
    "events": [
      {
        "timestamp": "2025-10-17T12:00:00Z",
        "event": "Deployment started",
        "duration_ms": 45000,
        "type": "deployment"
      }
    ]
  }
}
```

**Visualization Hints:**
- `event_field`: Field containing event description
- `duration_field`: Field containing duration (optional)
- `color_by`: Field to use for color coding

#### `flows`
**Suggested Visualizations:** sankey, graph_force_directed, timeline

**Data Structure:**
```json
{
  "data": {
    "nodes": [
      {"id": "source", "value": 100},
      {"id": "target", "value": 80}
    ],
    "links": [
      {"source": "source", "target": "target", "value": 80}
    ]
  }
}
```

### Shell Output

#### `shell_output`
**Suggested Visualizations:** terminal_viewer, text_viewer

**Data Structure:**
```json
{
  "data": {
    "command": "kubectl get pods",
    "stdout": "...",
    "stderr": "...",
    "exit_code": 0
  }
}
```

**Visualization Hints:**
- `exit_code`: Command exit code
- `show_stderr`: Whether to show stderr
- `syntax_highlight`: Whether to apply syntax highlighting

## UI Implementation Guide

### 1. Detecting Artifacts

When the agent produces output, check for the presence of `artifact_path` in the response:

```python
if response.get("artifact_path"):
    # Load artifact from file
    with open(response["artifact_path"]) as f:
        artifact = json.load(f)
```

### 2. Reading Metadata

Extract key information from the artifact:

```python
content_type = artifact["content_type"]
suggested_viz = artifact["suggested_visualizations"]
hints = artifact["visualization_hints"]
data = artifact["data"]
```

### 3. Rendering Visualization Selector

Present users with a dropdown of appropriate visualizations:

```jsx
<VisualizationSelector
  options={artifact.suggested_visualizations}
  default={artifact.visualization_hints.default_view}
  onSelect={(vizType) => renderVisualization(vizType, artifact)}
/>
```

### 4. Implementing Visualizations

Each visualization type should:
1. Read `data` field for the actual content
2. Use `visualization_hints` for rendering guidance
3. Use `metadata` for contextual information

Example for logs viewer:

```jsx
function LogsViewer({ artifact }) {
  const { logs } = artifact.data;
  const hints = artifact.visualization_hints;

  return (
    <LogsDisplay
      logs={logs}
      timeField={hints.time_field}
      levelField={hints.level_field}
      messageField={hints.message_field}
      highlightPatterns={hints.highlight_patterns}
      searchEnabled={hints.supports_search}
      filterEnabled={hints.supports_filtering}
    />
  );
}
```

## Benefits of This Approach

### For the LLM
- **No hallucination risk**: LLM only produces structured data, not tool calls
- **Simpler reasoning**: Focus on data extraction, not visualization selection
- **Fewer tools**: No need for 20+ visualization tools

### For Users
- **More control**: Users choose how to view data
- **Multiple views**: Same data can be viewed in different ways
- **Better UX**: Appropriate visualizations automatically suggested

### For Developers
- **Maintainable**: Adding new visualizations doesn't require LLM changes
- **Consistent**: All tools follow same metadata format
- **Extensible**: Easy to add new content types and visualizations

## Migration from Old System

The old system had the LLM call visualization tools like:
```
generate_logs_visualization(input_file='logs.json')
```

**Problems:**
- LLM had to choose correct visualization tool
- LLM had to provide correct parameters
- Added complexity and hallucination risk
- User had no control over visualization

New system:
- LLM produces data with metadata
- UI offers visualization options
- User selects preferred view
- Same data, multiple visualizations possible

## Example: Complete Flow

### 1. User Request
"Show me errors from the API service in the last hour"

### 2. LLM Uses Tool
```python
query_logs(
  query="error AND service:api",
  time_range="1h"
)
```

### 3. Tool Returns Artifact
```json
{
  "status": "success",
  "artifact_path": ".oats_artifacts/execution_123/logs_api_errors_20251017.json",
  "content_type": "logs",
  "suggested_visualizations": ["logs_viewer", "timeline", "table"],
  "summary": {
    "total_logs": 150,
    "levels": {"ERROR": 142, "WARN": 8}
  },
  "message": "Retrieved 150 log entries. UI will offer: logs_viewer, timeline, table"
}
```

### 4. UI Loads Artifact
```javascript
// UI loads the artifact file
const artifact = await loadArtifact(response.artifact_path);

// UI shows visualization selector
showVisualizationDropdown({
  options: ["Logs Viewer", "Timeline", "Table"],
  default: "Logs Viewer",
  artifact: artifact
});
```

### 5. User Selects Visualization
User can switch between:
- **Logs Viewer**: Traditional log viewing with search/filter
- **Timeline**: Visual timeline of events
- **Table**: Tabular view with sorting/filtering

All from the same artifact!

## Adding New Content Types

To add a new content type:

1. Add to `CONTENT_TYPES` in `core/artifact_metadata.py`:
```python
"new_type": {
    "visualizations": ["viz1", "viz2"],
    "default": "viz1",
    "supports_search": True,
    "supports_filtering": True
}
```

2. Update tools to use the new content type:
```python
create_artifact_with_metadata(
    content_type="new_type",
    data=your_data,
    ...
)
```

3. Implement visualization in UI

No LLM changes required!

## Version History

- **v1.0** (2025-10-17): Initial specification
  - Universal metadata schema
  - Support for logs, metrics, traces, code, and generic formats
  - Decoupled LLM from visualization selection
