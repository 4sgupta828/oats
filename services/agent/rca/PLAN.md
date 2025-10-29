  Key Issues & Design Corrections:

  1. Dynamic Incident Window Detection (Your Main Concern):
    - The v6 prompt currently expects {{incident_start}}, {{incident_end}}, {{baseline_start}}, {{baseline_end}} to be provided as template variables
    - The TOOLS_DESIGN.md has hardcoded incident_window and baseline_window parameters in all tool signatures
    - Problem: For real RCA scenarios, you don't always know the incident window upfront - you need to discover it from the data
    - Solution: Build a preprocessing tool that detects the incident window dynamically before the agent starts
  2. Understanding the Simulation Data Structure:
    - metrics.jsonl: Time-series with ts (nanoseconds), name, labels, value/summary
    - logs.jsonl: Structured logs with timestamp (simulation time like "60.00s"), level, message, attributes
    - traces.jsonl: OpenTelemetry spans with parent-child relationships, nanosecond timestamps
    - infra_context.json: Contains deployment_history with simulation_time field showing when deployments occurred
    - metadata.json: Summary stats, but notably has empty incidents and failure_injections arrays - this confirms you want the agent to discover incidents
  dynamically

  Proposed Implementation Plan:

  Phase 0: Build Dynamic Incident Detection (NEW)

  Purpose: Automatically detect anomaly windows from raw telemetry before the RCA agent starts.

  New Tool: detect_incident_window

  Input:
  {
    "data_dir": "/path/to/telemetry",
    "symptom_hint": "product-catalog errors" (optional),
    "lookback_seconds": 300,
    "sensitivity": "high" | "medium" | "low"
  }

  Implementation Strategy:
  1. Scan all metrics for anomalies using:
    - Z-score detection (threshold: z > 3.0)
    - Changepoint detection (ruptures library - Pelt algorithm)
    - Error rate spikes from logs
  2. Find first significant anomaly across all components
  3. Find last significant anomaly (or determine if still active)
  4. Calculate baseline window (time before first anomaly)
  5. Return incident window: [start_time, end_time or null]

  Output:
  {
    "status": "success",
    "incident_detected": true,
    "incident_window": {
      "start_time": 60.0,
      "end_time": 287.87,
      "status": "RESOLVED"  // or "ACTIVE" if end_time is null
    },
    "baseline_window": {
      "start_time": 0.0,
      "end_time": 60.0
    },
    "symptom_summary": {
      "primary_symptom_component": "product_catalog_service",
      "symptom_description": "Memory leak causing OOM crashes",
      "first_anomaly_time": 60.0,
      "affected_components": ["product_catalog_service", "api_gateway"]
    },
    "anomalies_detected": [
      {
        "component": "product_catalog_service",
        "metric": "component.errors.total",
        "anomaly_time": 60.0,
        "severity": "HIGH",
        "z_score": 15.2
      }
    ]
  }

  This tool runs BEFORE the RCA agent prompt is instantiated, so it can populate the template variables.

  ---
  Phase 1: Build Telemetry Data Adapters

  Purpose: Abstract telemetry access so tools work with both simulation JSONL files and production systems.

  Implementation:

  1. TelemetryBackend Abstract Class:
  class TelemetryBackend(ABC):
      @abstractmethod
      def query_metrics(self, component, metric_pattern, time_range):
          """Returns list of metric datapoints"""
          pass

      @abstractmethod
      def query_logs(self, component, time_range, level_filter=None):
          """Returns list of log entries"""
          pass

      @abstractmethod
      def query_traces(self, time_range, component_filter=None):
          """Returns list of trace spans"""
          pass

      @abstractmethod
      def get_topology(self):
          """Returns infrastructure topology and relationships"""
          pass

  2. SimulationBackend (Priority):
  class SimulationBackend(TelemetryBackend):
      def __init__(self, data_dir: str):
          self.data_dir = Path(data_dir)
          self.metrics_file = self.data_dir / "metrics.jsonl"
          self.logs_file = self.data_dir / "logs.jsonl"
          self.traces_file = self.data_dir / "traces.jsonl"
          self.infra_context = json.load(open(self.data_dir / "infra_context.json"))
          self.metadata = json.load(open(self.data_dir / "metadata.json"))

          # Build indexes for fast querying
          self._build_indexes()

      def query_metrics(self, component, metric_pattern, time_range):
          # Parse metrics.jsonl, filter by component and time_range
          # Convert nanosecond timestamps to simulation time
          # Return as structured data
          pass

  3. Key Data Transformations:
    - Convert nanosecond timestamps to simulation seconds using sim.time label
    - Parse log timestamps from strings like "60.00s" to floats
    - Extract component IDs from labels/attributes
    - Build dependency graph from traces

  ---
  Phase 2: Correct Tool Signatures & Implementation

  Major Changes to TOOLS_DESIGN.md:

  1. Remove Hardcoded Time Windows Where Possible:
    - Tools like get_service_dependencies, get_recent_changes don't need incident windows
    - Only statistical comparison tools need windows
  2. Support Dynamic Windows:
    - All tools should accept time_range: [start, end] where end can be null for active incidents
    - When end is null, query up to "current time" (last timestamp in data)
  3. Work with Simulation Data Format:

  Example Corrected Tool: get_recent_changes

  Original design:
  def get_recent_changes(component_name: str, lookback_window: List[float], data_dir: str)

  Corrected design:
  def get_recent_changes(
      component_name: str,
      reference_time: float,  # Incident start time
      lookback_seconds: float = 300,  # How far back to look
      data_dir: str
  ) -> dict:
      """
      Find deployments and changes before the incident.
      Reads from infra_context.json deployment_history.
      """
      backend = SimulationBackend(data_dir)
      topology = backend.get_topology()

      # Find component in topology
      component = find_component(topology, component_name)

      # Extract deployment_history
      deployments = component.get("deployment_history", [])

      # Filter deployments within lookback window
      relevant_changes = []
      for deployment in deployments:
          deploy_time = deployment["simulation_time"]
          time_before_incident = reference_time - deploy_time

          if 0 < time_before_incident <= lookback_seconds:
              correlation = calculate_correlation_likelihood(time_before_incident)
              relevant_changes.append({
                  "timestamp": deploy_time,
                  "component": component_name,
                  "change_type": "deployment",
                  "description": f"Deployed {deployment['commit_id']}: {deployment['message']}",
                  "time_before_incident": f"{time_before_incident:.1f}s",
                  "correlation_likelihood": correlation,
                  "details": deployment
              })

      return {
          "status": "success",
          "changes_detected": relevant_changes
      }

  Key Fix: Uses simulation_time from deployment_history, calculates correlation based on time proximity to incident start.

  ---
  Phase 3: Build Core Analyzers

  1. MetricsAnalyzer - Enhanced with changepoint detection:
  class MetricsAnalyzer:
      def __init__(self, backend: TelemetryBackend):
          self.backend = backend

      def detect_anomalies(self, component: str, time_range: List[float]) -> List[Anomaly]:
          """Detect metric anomalies using z-scores and changepoint detection"""
          metrics = self.backend.query_metrics(component, "*", time_range)

          anomalies = []
          for metric in metrics:
              # Calculate baseline statistics
              baseline_stats = self._calculate_stats(metric.baseline_values)

              # Detect anomalies
              for point in metric.incident_values:
                  z_score = (point.value - baseline_stats.mean) / baseline_stats.std
                  if abs(z_score) > 3.0:
                      anomalies.append(Anomaly(
                          metric_name=metric.name,
                          timestamp=point.timestamp,
                          value=point.value,
                          z_score=z_score,
                          pattern=self._detect_pattern(metric)  # STEP_CHANGE, SPIKE, etc.
                      ))

          return anomalies

      def _detect_pattern(self, metric) -> str:
          """Use ruptures library to detect changepoint patterns"""
          import ruptures as rpt
          algo = rpt.Pelt(model="rbf").fit(metric.values)
          changepoints = algo.predict(pen=10)

          if len(changepoints) == 1:
              return "STEP_CHANGE"
          elif len(changepoints) > 2:
              return "GRADUAL_DRIFT"
          # ... more logic

  2. LogsAnalyzer - Drain3 template mining:
  class LogsAnalyzer:
      def __init__(self, backend: TelemetryBackend):
          self.backend = backend
          self.drain = Drain3TemplateParser()

      def compare_logs(self, component: str, baseline_range: List[float], incident_range: List[float]):
          baseline_logs = self.backend.query_logs(component, baseline_range)
          incident_logs = self.backend.query_logs(component, incident_range)

          baseline_templates = self.drain.parse(baseline_logs)
          incident_templates = self.drain.parse(incident_logs)

          new_templates = incident_templates - baseline_templates
          frequency_spikes = self._detect_frequency_spikes(baseline_templates, incident_templates)

          return {
              "new_templates": new_templates,
              "frequency_spikes": frequency_spikes
          }

  3. TracesAnalyzer - OpenTelemetry span parsing:
  class TracesAnalyzer:
      def __init__(self, backend: TelemetryBackend):
          self.backend = backend

      def build_dependency_graph(self, time_range: List[float]) -> nx.DiGraph:
          """Build call graph from trace spans"""
          spans = self.backend.query_traces(time_range)

          graph = nx.DiGraph()
          for span in spans:
              if span.parent_id:
                  parent_component = self._extract_component(span.parent_id)
                  child_component = self._extract_component(span.span_id)
                  graph.add_edge(parent_component, child_component)

          return graph

  ---
  Phase 4: Implement All 15 Tools from TOOLS_DESIGN.md

  Using the corrected signatures and analyzers, implement:

  Group 1: Situational Awareness
  - analyze_blast_radius - Uses TracesAnalyzer to build dep graph
  - get_temporal_timeline - Correlates metrics/logs/traces by timestamp
  - get_recent_changes - Reads from infra_context.json

  Group 2: Baseline Comparison
  - compare_metrics - Uses MetricsAnalyzer
  - compare_logs - Uses LogsAnalyzer
  - compare_traces - Uses TracesAnalyzer

  Group 3: Active Validation
  - get_service_dependencies - Reads from infra_context.json relationships
  - check_instance_health - Queries CPU/memory metrics
  - get_database_stats - Queries db.* metrics
  - get_cache_stats - Queries cache.* metrics
  - check_dependency_health - Analyzes trace spans between components

  Group 4: Dynamic Analysis (Already in v6 prompt)
  - shell, create_file, python - No changes needed

  Group 5: Finish
  - finish - Submits final RCA report

  ---
  Phase 5: Integration with Agent Framework

  Workflow:

  1. User provides: data_dir="/path/to/simulation/output"
  2. System runs: detect_incident_window(data_dir)
  3. System populates v6.txt template variables:
     - {{incident_start}} = 60.0
     - {{incident_end}} = 287.87
     - {{baseline_start}} = 0.0
     - {{baseline_end}} = 60.0
     - {{symptom_description}} = "product-catalog OOM crashes"
     - {{analysis_mode}} = "POST_INCIDENT" or "LIVE"
  4. Agent starts with populated prompt
  5. Agent uses tools (all tools use data_dir internally)
  6. Tools query SimulationBackend
  7. Agent completes investigation, calls finish()

  ---
  Key Design Decisions:

  1. No Explicit Incident Window in Tools (where possible):
    - get_recent_changes takes reference_time + lookback_seconds
    - Statistical comparison tools still need baseline vs incident windows
    - This makes tools flexible for both post-incident and live mode
  2. Dynamic Window Detection is Preprocessing:
    - Runs before agent starts
    - Populates template variables
    - Agent can still adjust windows during investigation if needed
  3. Simulation-First Design:
    - All tools work perfectly with JSONL simulation data
    - SimulationBackend handles timestamp conversions, indexing
    - Easy to add PrometheusBackend later for production
  4. Statistical Rigor:
    - Z-scores, p-values, changepoint detection
    - Anomaly pattern classification (STEP_CHANGE, SPIKE, etc.)
    - Time correlation for deployment changes
  5. Respects Simulation Data Format:
    - Reads deployment_history from infra_context.json
    - Handles nanosecond timestamps in metrics/traces
    - Parses simulation time from log timestamps
    - Builds dependency graph from actual trace spans

  ---
  Summary of Major Changes Needed:

  1. Create detect_incident_window tool - Dynamically discovers incident windows
  2. Build SimulationBackend - Abstracts JSONL data access
  3. Correct tool signatures - Remove hardcoded windows where possible
  4. Implement all 15 tools - Using corrected designs
  5. Build core analyzers - MetricsAnalyzer, LogsAnalyzer, TracesAnalyzer
  6. Integration workflow - detect_incident_window → populate template → start agent

  This plan addresses your core requirement: No hardcoded incident windows. The system discovers anomalies dynamically from the telemetry data, just like a SOTA RCA
   agent should.