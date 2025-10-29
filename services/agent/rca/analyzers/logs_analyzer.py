"""Logs analyzer with template mining and frequency analysis"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, Counter
import re
import hashlib

from rca.backends.base import TelemetryBackend, LogEntry
from core.logging_config import get_logger

logger = get_logger('logs_analyzer')

# Try to import Drain3 for production-grade template mining
try:
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    HAS_DRAIN3 = True
    logger.info("Drain3 library available - using production-grade template mining")
except ImportError:
    HAS_DRAIN3 = False
    logger.info("Drain3 library not available - using heuristic template mining")


@dataclass
class LogTemplate:
    """A log template extracted from log messages"""
    template_id: str
    template: str
    frequency: int
    first_seen: float
    severity: str
    example_message: str


class LogsAnalyzer:
    """Analyzer for detecting new log patterns and frequency spikes"""

    def __init__(self, backend: TelemetryBackend):
        """Initialize logs analyzer

        Args:
            backend: Telemetry backend for querying logs
        """
        self.backend = backend

        # Initialize Drain3 if available
        if HAS_DRAIN3:
            self._init_drain3()
        else:
            self.template_miner = None

    def _init_drain3(self):
        """Initialize Drain3 template miner with optimal configuration"""
        try:
            config = TemplateMinerConfig()
            # Tune parameters for cloud infrastructure logs
            config.load({
                "drain": {
                    "sim_th": 0.4,  # Similarity threshold (0-1, lower = more strict)
                    "depth": 4,  # Depth of prefix tree
                    "max_children": 100,  # Max children per node
                    "max_clusters": 1024,  # Max unique templates
                },
                "masking": [
                    # Common patterns to mask
                    {"regex_pattern": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "mask_with": "<IP>"},
                    {"regex_pattern": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "mask_with": "<UUID>"},
                    {"regex_pattern": r"\b[0-9a-fA-F]{32,}\b", "mask_with": "<ID>"},
                    {"regex_pattern": r"\b\d+\b", "mask_with": "<NUM>"},
                ]
            })
            self.template_miner = TemplateMiner(config=config)
            logger.info("Drain3 template miner initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Drain3: {e}, falling back to heuristics")
            self.template_miner = None

    def compare_logs(
        self,
        component: str,
        baseline_range: Tuple[float, float],
        incident_range: Tuple[float, Optional[float]]
    ) -> Dict[str, Any]:
        """Compare logs between baseline and incident periods

        Args:
            component: Component name to analyze
            baseline_range: (start, end) for baseline period
            incident_range: (start, end) for incident period

        Returns:
            Dictionary with new templates and frequency spikes
        """
        # Query logs for both periods
        baseline_logs = self.backend.query_logs(component, baseline_range)
        incident_logs = self.backend.query_logs(component, incident_range)

        # Extract templates
        baseline_templates = self._extract_templates(baseline_logs)
        incident_templates = self._extract_templates(incident_logs)

        # Find new templates (in incident but not baseline)
        new_templates = []
        for template_id, template in incident_templates.items():
            if template_id not in baseline_templates:
                new_templates.append({
                    "template_id": template.template_id,
                    "template": template.template,
                    "first_seen": template.first_seen,
                    "frequency": template.frequency,
                    "severity": template.severity,
                    "example_message": template.example_message
                })

        # Find frequency spikes (templates with significantly increased frequency)
        frequency_spikes = []
        for template_id, incident_template in incident_templates.items():
            if template_id in baseline_templates:
                baseline_template = baseline_templates[template_id]

                # Calculate frequency increase
                baseline_freq = baseline_template.frequency
                incident_freq = incident_template.frequency

                if baseline_freq > 0:
                    freq_increase = ((incident_freq - baseline_freq) / baseline_freq) * 100

                    # Only report significant spikes (>500% increase or >50 new occurrences)
                    if freq_increase > 500 or (incident_freq - baseline_freq) > 50:
                        # Calculate z-score (simplified)
                        z_score = (incident_freq - baseline_freq) / max(1, baseline_freq ** 0.5)

                        frequency_spikes.append({
                            "template_id": template_id,
                            "template": incident_template.template,
                            "baseline_frequency": baseline_freq,
                            "incident_frequency": incident_freq,
                            "frequency_increase": round(freq_increase, 1),
                            "z_score": round(z_score, 2),
                            "severity": incident_template.severity
                        })

        # Count error logs
        baseline_errors = sum(1 for log in baseline_logs if log.level in ['ERROR', 'FATAL'])
        incident_errors = sum(1 for log in incident_logs if log.level in ['ERROR', 'FATAL'])

        error_increase = 0.0
        if baseline_errors > 0:
            error_increase = ((incident_errors - baseline_errors) / baseline_errors) * 100

        return {
            "status": "success",
            "component": component,
            "new_templates": new_templates,
            "frequency_spikes": sorted(frequency_spikes, key=lambda x: x['frequency_increase'], reverse=True),
            "total_error_logs": incident_errors,
            "baseline_error_logs": baseline_errors,
            "error_log_increase": round(error_increase, 1),
            "baseline_range": baseline_range,
            "incident_range": incident_range
        }

    def _extract_templates(self, logs: List[LogEntry]) -> Dict[str, LogTemplate]:
        """Extract log templates using Drain3 or heuristics

        Uses Drain3 if available for production-grade template mining,
        otherwise falls back to simple pattern matching.
        """
        if HAS_DRAIN3 and self.template_miner is not None:
            return self._extract_templates_drain3(logs)
        else:
            return self._extract_templates_heuristic(logs)

    def _extract_templates_drain3(self, logs: List[LogEntry]) -> Dict[str, LogTemplate]:
        """Extract templates using Drain3 algorithm"""
        templates = {}
        cluster_examples = {}
        cluster_first_seen = {}
        cluster_severities = {}
        cluster_counts = defaultdict(int)

        # Reset template miner for each analysis
        if self.template_miner is not None:
            self._init_drain3()  # Re-initialize to clear state

        for log in logs:
            try:
                # Add log to Drain3
                result = self.template_miner.add_log_message(log.message)

                if result is not None:
                    cluster_id = str(result["cluster_id"])

                    # Track first occurrence
                    if cluster_id not in cluster_first_seen:
                        cluster_first_seen[cluster_id] = log.timestamp
                        cluster_examples[cluster_id] = log.message
                        cluster_severities[cluster_id] = log.level

                    # Update highest severity
                    if log.level == "ERROR" or log.level == "FATAL":
                        cluster_severities[cluster_id] = log.level

                    cluster_counts[cluster_id] += 1

            except Exception as e:
                logger.debug(f"Failed to process log with Drain3: {e}")
                continue

        # Convert Drain3 clusters to LogTemplates
        if self.template_miner is not None:
            for cluster_id, count in cluster_counts.items():
                cluster = self.template_miner.drain.clusters.get(int(cluster_id))
                if cluster is not None:
                    template_str = " ".join(cluster.log_template_tokens)

                    templates[cluster_id] = LogTemplate(
                        template_id=cluster_id,
                        template=template_str,
                        frequency=count,
                        first_seen=cluster_first_seen.get(cluster_id, 0.0),
                        severity=cluster_severities.get(cluster_id, "INFO"),
                        example_message=cluster_examples.get(cluster_id, "")
                    )

        return templates

    def _extract_templates_heuristic(self, logs: List[LogEntry]) -> Dict[str, LogTemplate]:
        """Fallback heuristic template extraction"""
        templates = {}
        template_examples = {}
        template_first_seen = {}

        for log in logs:
            # Generate template by replacing dynamic parts
            template = self._generalize_message(log.message)

            # Generate template ID
            template_id = hashlib.md5(template.encode()).hexdigest()[:8]

            # Track first occurrence
            if template_id not in template_first_seen:
                template_first_seen[template_id] = log.timestamp
                template_examples[template_id] = log.message

            # Count occurrences
            if template_id not in templates:
                templates[template_id] = LogTemplate(
                    template_id=template_id,
                    template=template,
                    frequency=1,
                    first_seen=log.timestamp,
                    severity=log.level,
                    example_message=log.message
                )
            else:
                templates[template_id].frequency += 1

        return templates

    def _generalize_message(self, message: str) -> str:
        """Generalize log message by replacing dynamic parts with placeholders

        This is a simplified heuristic-based approach.
        """
        # Replace numbers
        message = re.sub(r'\b\d+\b', '<NUM>', message)

        # Replace hexadecimal IDs
        message = re.sub(r'\b[0-9a-fA-F]{8,}\b', '<ID>', message)

        # Replace timestamps
        message = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TIMESTAMP>', message)

        # Replace IP addresses
        message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>', message)

        # Replace UUIDs
        message = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<UUID>', message)

        # Replace file paths
        message = re.sub(r'(/[\w\-./]+)+', '<PATH>', message)

        # Replace quoted strings
        message = re.sub(r'"[^"]*"', '<STRING>', message)
        message = re.sub(r"'[^']*'", '<STRING>', message)

        return message
