# Test Artifacts for UI Visualizations

This directory contains comprehensive test artifacts for all visualization types implemented in OATS infra-copilot.

## Overview

These artifacts are designed to test and showcase the visualization capabilities added in the `uivis` branch. Each artifact represents a realistic infrastructure incident scenario involving a payment service failure.

## Incident Scenario

All artifacts are part of a cohesive story:
- **Time**: 2025-10-16, 16:10-16:30 UTC
- **Incident**: Payment service experiencing cascading failures due to database connection pool exhaustion
- **Impact**: 12.3% error rate, 1245ms P95 latency, 142 failed payment requests
- **Root Cause**: Database connection timeouts leading to pool exhaustion and circuit breaker activation
- **Resolution**: Connection pool recovery, circuit breaker reset, service stabilization

## Artifacts

### 1. Topology Visualization
**File**: `topology_microservices.json`

Visualizes the microservices architecture with real-time health status:
- 10 nodes (services, databases, caches, message queues)
- 12 edges showing dependencies and communication patterns
- Color-coded status (healthy/degraded/unhealthy)
- Rich metadata (CPU, memory, latency, throughput)

**Key Features Tested**:
- Node-edge graph rendering
- Status-based coloring
- Interactive minimap
- Metadata tooltips

### 2. Time Series Visualization
**File**: `timeseries_metrics.json`

Shows 2-hour performance metrics with anomaly detection:
- 5 metrics series (CPU, Memory, Latency, Error Rate, Request Rate)
- 25 data points per series (30-second resolution)
- 5 annotated anomalies with severity levels
- Clear progression from healthy to critical state

**Key Features Tested**:
- Multi-series line charts
- Anomaly markers with colors
- Interactive zoom and tooltips
- Large dataset handling (125 data points)

### 3. Log Visualization
**File**: `logs_payment_service.json`

Contains 30 structured log entries showing the incident progression:
- Mixed log levels: ERROR (10), WARN (6), INFO (12), DEBUG (2)
- Trace ID correlation for distributed tracing
- Rich metadata and contextual information
- Timeline from failure detection to recovery

**Key Features Tested**:
- Virtual scrolling performance
- Level-based filtering
- Full-text search capability
- Trace ID filtering
- Color-coded log levels

### 4. Trace Visualization
**File**: `trace_payment_flow.json`

Distributed trace with 15 spans showing failed payment request:
- Root span: payment service endpoint (5178ms, error)
- Nested spans showing service calls (up to 3 levels deep)
- Multiple services involved (payment, fraud detection, redis, kafka)
- Error propagation and retry logic visible

**Key Features Tested**:
- Waterfall visualization
- Parent-child relationships
- Duration bars
- Error indication
- Span details with tags and logs

### 5. Mermaid Diagrams

#### a. Architecture Flowchart
**File**: `mermaid_architecture.json`

Flowchart showing payment service architecture and failure propagation:
- 4 layers (Client, Application, Business Logic, Data)
- 12 components with connections
- Numbered request flow (1-12)
- Color-coded by status
- Circuit breaker state visualization

**Diagram Type**: `flowchart TB` (top-to-bottom)

#### b. Sequence Diagram
**File**: `mermaid_sequence.json`

Interaction sequence during payment failure:
- 7 participants (Client, API Gateway, Payment Service, etc.)
- 20+ interactions showing request flow
- Error boxes highlighting failure points
- Timing annotations
- Return values and status codes

**Diagram Type**: `sequenceDiagram`

#### c. State Diagram
**File**: `mermaid_state.json`

Circuit breaker state transitions:
- 3 states (Closed, Open, Half-Open)
- Transition conditions with timestamps
- Detailed notes for each state
- Recovery path visualization

**Diagram Type**: `stateDiagram-v2`

#### d. Gantt Timeline
**File**: `mermaid_gantt.json`

Incident timeline with phases:
- 7 sections from normal operation to recovery
- 20+ events with durations
- Status-based coloring (done, active, critical)
- Milestone markers
- 15-minute time window

**Diagram Type**: `gantt`

## Data Structure Summary

All artifacts follow the base visualization spec format:

```json
{
  "type": "topology|timeseries|logs|trace|mermaid",
  "title": "Human-readable title",
  "timestamp": "ISO8601 timestamp",
  "metadata": {
    "description": "Context and details",
    ...
  },
  "data": {
    // Type-specific data structure
  }
}
```

## Usage

### Testing Individual Visualizations

To test a specific visualization type in the UI:

1. Start the OATS services
2. Navigate to the artifacts viewer
3. Load the desired JSON file
4. Interact with the visualization controls (pin, screenshot, download)

### Testing Complete Workflow

To test the full investigation workflow:

1. Load `topology_microservices.json` - Identify unhealthy payment service
2. Load `timeseries_metrics.json` - Analyze metric trends and anomalies
3. Load `logs_payment_service.json` - Review error messages and trace IDs
4. Load `trace_payment_flow.json` - Examine distributed request flow
5. Load `mermaid_*.json` - Review architecture and timeline diagrams

### Testing Agent Integration

These artifacts can be used to test the backend visualization tools:

```python
from tools.visualization_tools import (
    generate_topology_visualization,
    generate_metrics_visualization,
    generate_logs_visualization,
    generate_trace_visualization,
    generate_mermaid_diagram
)
```

## Performance Benchmarks

These artifacts are designed to test visualization performance:

- **Topology**: 10 nodes, 12 edges (medium complexity)
- **Time Series**: 125 data points, 5 series (moderate load)
- **Logs**: 30 entries (small dataset for quick testing)
- **Trace**: 15 spans, 3 nesting levels (typical complexity)
- **Mermaid**: Various sizes (10-30 elements)

For stress testing, multiply the data:
- Logs: Duplicate entries to simulate 1000+ logs
- Time Series: Add more data points to test 10k+ datapoints
- Topology: Add more nodes to test large graphs (50+ nodes)

## Validation

Each artifact has been validated against:
- JSON schema correctness
- Data type consistency
- Realistic values and relationships
- Frontend component compatibility
- Agent tool output format

## Related Files

- **Frontend Components**: `/services/ui/src/components/visualizations/`
- **Backend Tools**: `/services/agent/tools/visualization_tools.py`
- **Store**: `/services/ui/src/store/visualizationStore.js`
- **Viewer**: `/services/ui/src/components/ArtifactViewer.js`

## Future Enhancements

Potential additions for more comprehensive testing:
- Network topology with 50+ nodes
- Time series with 100k+ data points
- Logs with 10k+ entries for virtual scroll stress test
- Traces with 5+ nesting levels
- Entity-relationship diagrams
- Class diagrams for code structure
