"""Logs analyzer with template mining and frequency analysis"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, Counter
import re
import hashlib

from rca.backends.base import TelemetryBackend, LogEntry
from core.logging_config import get_logger

logger = get_logger('logs_analyzer')


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
        """Extract log templates using simple pattern matching

        This is a simplified version. For production, use Drain3 or similar algorithms.
        """
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
