"""Abstract base class for telemetry backends

This provides a unified interface for accessing telemetry data from different sources
(simulation files, production systems, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class MetricDataPoint:
    """A single metric data point"""
    timestamp: float
    value: float
    labels: Dict[str, str]


@dataclass
class LogEntry:
    """A single log entry"""
    timestamp: float
    level: str
    message: str
    attributes: Dict[str, Any]
    component: Optional[str] = None


@dataclass
class TraceSpan:
    """A single trace span"""
    span_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: float
    duration_ms: float
    component: str
    attributes: Dict[str, Any]
    status: str
    error: bool = False


class TelemetryBackend(ABC):
    """Abstract base class for telemetry data access"""

    @abstractmethod
    def query_metrics(
        self,
        component: Optional[str],
        metric_pattern: str,
        time_range: Tuple[float, Optional[float]]
    ) -> List[MetricDataPoint]:
        """Query metrics for a component

        Args:
            component: Component name to filter by (None for all)
            metric_pattern: Metric name pattern (supports wildcards)
            time_range: (start_time, end_time) in seconds. end_time can be None for active incidents

        Returns:
            List of metric data points
        """
        pass

    @abstractmethod
    def query_logs(
        self,
        component: Optional[str],
        time_range: Tuple[float, Optional[float]],
        level_filter: Optional[str] = None
    ) -> List[LogEntry]:
        """Query logs for a component

        Args:
            component: Component name to filter by (None for all)
            time_range: (start_time, end_time) in seconds
            level_filter: Log level to filter (ERROR, WARN, INFO, etc.)

        Returns:
            List of log entries
        """
        pass

    @abstractmethod
    def query_traces(
        self,
        time_range: Tuple[float, Optional[float]],
        component_filter: Optional[str] = None
    ) -> List[TraceSpan]:
        """Query trace spans

        Args:
            time_range: (start_time, end_time) in seconds
            component_filter: Component name to filter by (None for all)

        Returns:
            List of trace spans
        """
        pass

    @abstractmethod
    def get_topology(self) -> Dict[str, Any]:
        """Get infrastructure topology and relationships

        Returns:
            Dictionary containing component topology and relationships
        """
        pass

    @abstractmethod
    def get_time_range(self) -> Tuple[float, float]:
        """Get the available time range of data

        Returns:
            (min_timestamp, max_timestamp) in seconds
        """
        pass
