"""Simulation backend for accessing JSONL telemetry files

This backend reads telemetry data from simulation output files (metrics.jsonl, logs.jsonl, traces.jsonl)
and provides efficient indexed access for RCA analysis.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import re

from .base import TelemetryBackend, MetricDataPoint, LogEntry, TraceSpan
from core.logging_config import get_logger

logger = get_logger('simulation_backend')


class SimulationBackend(TelemetryBackend):
    """Backend for reading simulation JSONL files"""

    def __init__(self, data_dir: str):
        """Initialize simulation backend

        Args:
            data_dir: Path to directory containing simulation data files
        """
        self.data_dir = Path(data_dir)
        self.metrics_file = self.data_dir / "metrics.jsonl"
        self.logs_file = self.data_dir / "logs.jsonl"
        self.traces_file = self.data_dir / "traces.jsonl"
        self.infra_context_file = self.data_dir / "infra_context.json"
        self.metadata_file = self.data_dir / "metadata.json"

        # Validate files exist
        if not self.data_dir.exists():
            raise ValueError(f"Data directory does not exist: {data_dir}")

        # Load context files
        self.infra_context = self._load_json(self.infra_context_file) if self.infra_context_file.exists() else {}
        self.metadata = self._load_json(self.metadata_file) if self.metadata_file.exists() else {}

        # Build indexes for fast querying
        self._build_indexes()

        logger.info(f"Initialized SimulationBackend for {data_dir}")

    def _load_json(self, file_path: Path) -> Dict:
        """Load JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return {}

    def _build_indexes(self):
        """Build indexes for fast querying"""
        # Component-to-metrics index
        self.component_metrics = defaultdict(list)
        # Time range
        self.min_time = float('inf')
        self.max_time = float('-inf')

        # Index metrics if file exists
        if self.metrics_file.exists():
            logger.info(f"Indexing metrics from {self.metrics_file}")
            with open(self.metrics_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        metric = json.loads(line.strip())
                        # Extract component from labels
                        labels = metric.get('labels', {})
                        component = labels.get('component', labels.get('service', 'unknown'))

                        # Track time range
                        ts = metric.get('ts', 0)
                        if ts > 0:
                            sim_time = ts / 1e9  # Convert nanoseconds to seconds
                            self.min_time = min(self.min_time, sim_time)
                            self.max_time = max(self.max_time, sim_time)

                        # Index by component
                        self.component_metrics[component].append(line_num)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse metrics line {line_num}")

        logger.info(f"Indexed {len(self.component_metrics)} components, time range: [{self.min_time:.2f}, {self.max_time:.2f}]")

    def _parse_log_timestamp(self, timestamp_str: str) -> float:
        """Parse log timestamp from simulation format (e.g., '60.00s') to float"""
        if isinstance(timestamp_str, (int, float)):
            return float(timestamp_str)

        # Handle string format like "60.00s"
        if isinstance(timestamp_str, str):
            match = re.match(r'([0-9.]+)s', timestamp_str)
            if match:
                return float(match.group(1))

        return 0.0

    def query_metrics(
        self,
        component: Optional[str],
        metric_pattern: str,
        time_range: Tuple[float, Optional[float]]
    ) -> List[MetricDataPoint]:
        """Query metrics from metrics.jsonl"""
        if not self.metrics_file.exists():
            logger.warning(f"Metrics file not found: {self.metrics_file}")
            return []

        start_time, end_time = time_range
        if end_time is None:
            end_time = self.max_time

        results = []

        with open(self.metrics_file, 'r') as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())

                    # Convert timestamp from nanoseconds to simulation seconds
                    ts_ns = metric.get('ts', 0)
                    sim_time = ts_ns / 1e9

                    # Filter by time range
                    if sim_time < start_time or sim_time > end_time:
                        continue

                    # Extract component from labels
                    labels = metric.get('labels', {})
                    metric_component = labels.get('component', labels.get('service', 'unknown'))

                    # Filter by component
                    if component and metric_component != component:
                        continue

                    # Filter by metric name pattern
                    metric_name = metric.get('name', '')
                    if not self._matches_pattern(metric_name, metric_pattern):
                        continue

                    # Extract value (handle both gauge and summary types)
                    value = metric.get('value')
                    if value is None:
                        # Try summary format
                        summary = metric.get('summary', {})
                        value = summary.get('sum', 0.0)

                    results.append(MetricDataPoint(
                        timestamp=sim_time,
                        value=float(value) if value is not None else 0.0,
                        labels=labels
                    ))

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Skipping malformed metric: {e}")

        logger.info(f"Query returned {len(results)} metrics for component={component}, pattern={metric_pattern}")
        return results

    def query_logs(
        self,
        component: Optional[str],
        time_range: Tuple[float, Optional[float]],
        level_filter: Optional[str] = None
    ) -> List[LogEntry]:
        """Query logs from logs.jsonl"""
        if not self.logs_file.exists():
            logger.warning(f"Logs file not found: {self.logs_file}")
            return []

        start_time, end_time = time_range
        if end_time is None:
            end_time = self.max_time

        results = []

        with open(self.logs_file, 'r') as f:
            for line in f:
                try:
                    log = json.loads(line.strip())

                    # Parse timestamp
                    timestamp_str = log.get('timestamp', '0s')
                    sim_time = self._parse_log_timestamp(timestamp_str)

                    # Filter by time range
                    if sim_time < start_time or sim_time > end_time:
                        continue

                    # Extract component from attributes
                    attributes = log.get('attributes', {})
                    log_component = attributes.get('component', attributes.get('service', 'unknown'))

                    # Filter by component
                    if component and log_component != component:
                        continue

                    # Filter by level
                    level = log.get('level', 'INFO')
                    if level_filter and level != level_filter:
                        continue

                    results.append(LogEntry(
                        timestamp=sim_time,
                        level=level,
                        message=log.get('message', ''),
                        attributes=attributes,
                        component=log_component
                    ))

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Skipping malformed log: {e}")

        logger.info(f"Query returned {len(results)} logs for component={component}, level={level_filter}")
        return results

    def query_traces(
        self,
        time_range: Tuple[float, Optional[float]],
        component_filter: Optional[str] = None
    ) -> List[TraceSpan]:
        """Query traces from traces.jsonl"""
        if not self.traces_file.exists():
            logger.warning(f"Traces file not found: {self.traces_file}")
            return []

        start_time, end_time = time_range
        if end_time is None:
            end_time = self.max_time

        results = []

        with open(self.traces_file, 'r') as f:
            for line in f:
                try:
                    span = json.loads(line.strip())

                    # Convert timestamps from nanoseconds to simulation seconds
                    start_ns = span.get('start_time_unix_nano', 0)
                    end_ns = span.get('end_time_unix_nano', 0)
                    span_start = start_ns / 1e9
                    span_end = end_ns / 1e9

                    # Filter by time range
                    if span_start < start_time or span_start > end_time:
                        continue

                    # Extract component from attributes
                    attributes = span.get('attributes', {})
                    span_component = attributes.get('component', attributes.get('service.name', 'unknown'))

                    # Filter by component
                    if component_filter and span_component != component_filter:
                        continue

                    # Calculate duration
                    duration_ms = (span_end - span_start) * 1000

                    # Check for errors
                    status = span.get('status', {})
                    is_error = status.get('code') == 'ERROR' or attributes.get('error', False)

                    results.append(TraceSpan(
                        span_id=span.get('span_id', ''),
                        parent_id=span.get('parent_span_id'),
                        name=span.get('name', ''),
                        start_time=span_start,
                        end_time=span_end,
                        duration_ms=duration_ms,
                        component=span_component,
                        attributes=attributes,
                        status=status.get('code', 'OK'),
                        error=is_error
                    ))

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Skipping malformed trace span: {e}")

        logger.info(f"Query returned {len(results)} trace spans for component={component_filter}")
        return results

    def get_topology(self) -> Dict[str, Any]:
        """Get infrastructure topology from infra_context.json"""
        return self.infra_context

    def get_time_range(self) -> Tuple[float, float]:
        """Get the available time range of data"""
        return (self.min_time, self.max_time)

    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """Check if text matches pattern (supports * wildcard)"""
        if pattern == "*":
            return True

        # Convert wildcard pattern to regex
        regex_pattern = pattern.replace('.', '\\.').replace('*', '.*')
        return bool(re.match(f'^{regex_pattern}$', text))
