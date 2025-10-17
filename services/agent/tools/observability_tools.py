"""Universal Observability Tools for OATS Agent

These tools provide a consistent interface for the LLM to interact with different
data sources (logs, metrics, traces, code) regardless of the underlying provider.
The LLM only needs to know about these 4 universal tools, not 20+ provider-specific ones.
"""

from pydantic import Field
from typing import Optional, Dict, List, Any
from core.sdk import uf, UfInput
from core.logging_config import get_logger
import re
import json
from pathlib import Path
from datetime import datetime

logger = get_logger('observability_tools')


# File-based output helpers
def _should_save_to_file(data: Any, threshold_chars: int = 2000, threshold_items: int = 50) -> bool:
    """Determine if data is large enough to warrant file-based output"""
    if isinstance(data, list):
        return len(data) > threshold_items
    elif isinstance(data, str):
        return len(data) > threshold_chars
    elif isinstance(data, dict):
        data_json = json.dumps(data)
        return len(data_json) > threshold_chars
    return False


def _save_data_to_file(data: Any, data_type: str, suffix: str = "") -> str:
    """Save data to file and return path"""
    try:
        from core.sdk import get_execution_context

        # Get execution context for artifact tracking
        context = get_execution_context()
        execution_id = context.get('execution_id') if context else None

        if not execution_id:
            execution_id = "default"

        # Create artifacts directory
        artifact_dir = Path(f".oats_artifacts/{execution_id}/observability")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{data_type}_{suffix}_{timestamp}.json" if suffix else f"{data_type}_{timestamp}.json"
        file_path = artifact_dir / filename

        # Save data
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {data_type} data to {file_path}")

        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to save data to file: {e}")
        raise


def _create_summary_for_logs(logs: List[Dict]) -> Dict:
    """Create summary statistics for log data"""
    summary = {
        "total_logs": len(logs),
        "levels": {},
        "time_range": None,
        "sample": logs[:3] if logs else []
    }

    # Count by level
    for log in logs:
        level = log.get("level", "UNKNOWN")
        summary["levels"][level] = summary["levels"].get(level, 0) + 1

    # Extract time range if available
    if logs:
        timestamps = [log.get("timestamp") for log in logs if log.get("timestamp")]
        if timestamps:
            summary["time_range"] = {"start": min(timestamps), "end": max(timestamps)}

    return summary


def _create_summary_for_metrics(metric_data: Any, metric_name: str) -> Dict:
    """Create summary statistics for metric data"""
    summary = {
        "metric_name": metric_name,
        "data_points": 0,
        "sample": None
    }

    # Handle different metric data formats
    if isinstance(metric_data, dict):
        if "datapoints" in metric_data:
            summary["data_points"] = len(metric_data["datapoints"])
            summary["sample"] = metric_data["datapoints"][:3] if metric_data["datapoints"] else None
        elif "values" in metric_data:
            summary["data_points"] = len(metric_data["values"])
            summary["sample"] = metric_data["values"][:3] if metric_data["values"] else None

    return summary


# Validation helpers
def validate_time_range(time_range: str) -> bool:
    """Validate time range format (e.g., 15m, 1h, 24h)"""
    return bool(re.match(r'^\d+[mhd]$', time_range))


def create_error_response(error: Exception, context: str) -> dict:
    """Create error response with full context for LLM to understand

    We pass the raw error to the LLM instead of trying to categorize it.
    The LLM is better at understanding errors contextually than rule-based matching.
    """
    return {
        "status": "error",
        "error": f"{context}: {str(error)}",
        "context": context,
        "error_details": str(error)
    }


def normalize_log_entry(entry: Dict, provider: str) -> Dict:
    """Normalize log entry to consistent format across providers"""
    if provider == "cloudwatch":
        # CloudWatch returns list of [{field, value}, ...]
        if isinstance(entry, list):
            normalized = {}
            for item in entry:
                if isinstance(item, dict):
                    field = item.get('field', '').lstrip('@')
                    value = item.get('value', '')
                    normalized[field] = value
            return normalized
        else:
            return entry
    else:
        # Other providers - return as-is
        return entry


class QueryLogsInput(UfInput):
    """Universal log query interface - provider-agnostic"""
    query: str = Field(..., description="Natural language or structured query (e.g., 'errors in payment service' or 'level:ERROR service:api')")
    time_range: str = Field(..., description="Time range: '15m', '1h', '24h', or ISO timestamp range")
    filters: Optional[Dict[str, str]] = Field(None, description="Additional filters like {'service': 'checkout', 'environment': 'prod'}")
    limit: int = Field(default=100, description="Max results to return")
    save_to_file: bool = Field(default=True, description="Save large results to file (recommended to avoid context bloat)")
    output_file: Optional[str] = Field(None, description="Explicit output file path (auto-generated if not provided)")


@uf(name="query_logs", version="2.0.0",
   description="Search logs across configured log backends. IMPORTANT: Large results (>50 entries) are automatically saved to files to avoid context bloat. Use the returned file path with visualization tools like generate_logs_visualization(input_file=...). Supports natural language queries translated to provider-specific syntax.")
def query_logs(inputs: QueryLogsInput) -> dict:
    """Search logs using the configured log provider"""
    try:
        # Handle both dict and Pydantic model inputs
        if isinstance(inputs, dict):
            inputs = QueryLogsInput(**inputs)
        
        # Input validation
        if not validate_time_range(inputs.time_range):
            return {
                "status": "error",
                "error": f"Invalid time_range '{inputs.time_range}'. Use format: 15m, 1h, 24h",
                "suggestion": "Use a valid time range like '15m' (15 minutes), '1h' (1 hour), or '24h' (24 hours)"
            }

        if len(inputs.query) > 1000:
            return {
                "status": "error",
                "error": "Query too long (max 1000 characters)",
                "suggestion": "Simplify your query or break it into multiple smaller queries"
            }

        if not inputs.query.strip():
            return {
                "status": "error",
                "error": "Query cannot be empty",
                "suggestion": "Provide a search term like 'error', 'exception', or a specific error message"
            }

        # Cap limit to reasonable value
        safe_limit = min(inputs.limit, 500)
        if inputs.limit > 500:
            logger.warning(f"Limit {inputs.limit} capped to 500 for performance")

        from providers import get_log_provider

        provider = get_log_provider()
        result = provider.query(
            query=inputs.query,
            time_range=inputs.time_range,
            filters=inputs.filters,
            limit=safe_limit
        )

        if result.success:
            # Normalize results for consistent format
            normalized_data = [
                normalize_log_entry(entry, result.metadata.get("provider", "unknown"))
                for entry in result.data
            ]

            # Check if we should save to file
            if _should_save_to_file(normalized_data):
                # Save to file
                output_path = _save_data_to_file(
                    {
                        "logs": normalized_data,
                        "metadata": result.metadata,
                        "query": inputs.query,
                        "time_range": inputs.time_range
                    },
                    "logs",
                    inputs.query.replace(" ", "_")[:30]
                )

                # Create summary
                summary = _create_summary_for_logs(normalized_data)

                # Emit artifact marker
                print(f"Artifact available: {output_path}")

                return {
                    "status": "success",
                    "output_file": output_path,
                    "summary": summary,
                    "provider": result.metadata.get("provider", "unknown"),
                    "message": f"Retrieved {len(normalized_data)} log entries. Full data saved to {output_path}. Use this file with generate_logs_visualization(input_file='{output_path}')"
                }
            else:
                # Small result - return inline
                return {
                    "status": "success",
                    "data": normalized_data,
                    "metadata": result.metadata,
                    "provider": result.metadata.get("provider", "unknown"),
                    "count": len(normalized_data)
                }
        else:
            return create_error_response(
                Exception(result.error),
                "Log query failed"
            )

    except Exception as e:
        logger.error(f"Error querying logs: {e}", exc_info=True)
        return create_error_response(e, "Log query failed")


class QueryMetricsInput(UfInput):
    """Universal metrics query interface"""
    metric_name: str = Field(..., description="Metric to query (e.g., 'CPUUtilization', 'http_requests_total', 'api.latency')")
    dimensions: Optional[Dict[str, str]] = Field(None, description="Dimensions/tags to filter by (e.g., {'service': 'api', 'region': 'us-east-1'})")
    time_range: str = Field(..., description="Time range: '15m', '1h', '24h'")
    aggregation: str = Field(default="avg", description="Aggregation function: avg, sum, min, max, p95, p99")
    save_to_file: bool = Field(default=True, description="Save large results to file (recommended)")
    output_file: Optional[str] = Field(None, description="Explicit output file path")


@uf(name="query_metrics", version="2.0.0",
   description="Query time-series metrics from monitoring systems. IMPORTANT: Large results are saved to files automatically. Use the returned file path with generate_metrics_visualization(input_file=...). Supports checking resource utilization, request rates, error rates, latency percentiles.")
def query_metrics(inputs: QueryMetricsInput) -> dict:
    """Query metrics using the configured metric provider"""
    try:
        # Handle both dict and Pydantic model inputs
        if isinstance(inputs, dict):
            inputs = QueryMetricsInput(**inputs)
        
        # Input validation
        if not validate_time_range(inputs.time_range):
            return {
                "status": "error",
                "error": f"Invalid time_range '{inputs.time_range}'. Use format: 15m, 1h, 24h",
                "suggestion": "Use a valid time range like '15m' (15 minutes), '1h' (1 hour), or '24h' (24 hours)"
            }

        if not inputs.metric_name.strip():
            return {
                "status": "error",
                "error": "Metric name cannot be empty",
                "suggestion": "Provide a metric name like 'CPUUtilization', 'http_requests_total', or 'api.latency'"
            }

        # Validate aggregation
        valid_aggregations = ["avg", "sum", "min", "max", "p50", "p90", "p95", "p99"]
        if inputs.aggregation not in valid_aggregations:
            return {
                "status": "error",
                "error": f"Invalid aggregation '{inputs.aggregation}'",
                "suggestion": f"Use one of: {', '.join(valid_aggregations)}"
            }

        from providers import get_metric_provider

        provider = get_metric_provider()
        result = provider.query(
            metric_name=inputs.metric_name,
            dimensions=inputs.dimensions,
            time_range=inputs.time_range,
            aggregation=inputs.aggregation
        )

        if result.success:
            # Check if we should save to file
            if _should_save_to_file(result.data):
                # Save to file
                output_path = _save_data_to_file(
                    {
                        "series": [{
                            "name": inputs.metric_name,
                            "data": result.data,
                            "metadata": result.metadata
                        }],
                        "yAxisLabel": inputs.metric_name,
                        "query_info": {
                            "metric_name": inputs.metric_name,
                            "dimensions": inputs.dimensions,
                            "time_range": inputs.time_range,
                            "aggregation": inputs.aggregation
                        }
                    },
                    "metrics",
                    inputs.metric_name.replace(".", "_")[:30]
                )

                # Create summary
                summary = _create_summary_for_metrics(result.data, inputs.metric_name)

                # Emit artifact marker
                print(f"Artifact available: {output_path}")

                return {
                    "status": "success",
                    "output_file": output_path,
                    "summary": summary,
                    "provider": result.metadata.get("provider", "unknown"),
                    "message": f"Retrieved metric data for '{inputs.metric_name}'. Full data saved to {output_path}. Use with generate_metrics_visualization(input_file='{output_path}')"
                }
            else:
                # Small result - return inline
                return {
                    "status": "success",
                    "data": result.data,
                    "metadata": result.metadata,
                    "provider": result.metadata.get("provider", "unknown")
                }
        else:
            return create_error_response(
                Exception(result.error),
                "Metric query failed"
            )

    except Exception as e:
        logger.error(f"Error querying metrics: {e}", exc_info=True)
        return create_error_response(e, "Metric query failed")


class QueryTracesInput(UfInput):
    """Universal trace query interface"""
    trace_id: Optional[str] = Field(None, description="Specific trace ID to retrieve")
    service: Optional[str] = Field(None, description="Service name to search traces for")
    operation: Optional[str] = Field(None, description="Operation/endpoint name")
    time_range: str = Field(default="1h", description="Time range to search")
    filters: Optional[Dict[str, str]] = Field(None, description="Additional filters like {'error': 'true', 'duration_gt': '1000ms'}")
    save_to_file: bool = Field(default=True, description="Save large results to file (recommended)")
    output_file: Optional[str] = Field(None, description="Explicit output file path")


@uf(name="query_traces", version="2.0.0",
   description="Search distributed traces. IMPORTANT: Large results are saved to files automatically. Use the returned file path with generate_trace_visualization(input_file=...). Use trace_id for specific trace lookup, or service+operation+filters to find problematic traces.")
def query_traces(inputs: QueryTracesInput) -> dict:
    """Query traces using the configured trace provider"""
    try:
        # Handle both dict and Pydantic model inputs
        if isinstance(inputs, dict):
            inputs = QueryTracesInput(**inputs)
        
        # Input validation
        if not validate_time_range(inputs.time_range):
            return {
                "status": "error",
                "error": f"Invalid time_range '{inputs.time_range}'. Use format: 15m, 1h, 24h",
                "suggestion": "Use a valid time range like '15m' (15 minutes), '1h' (1 hour), or '24h' (24 hours)"
            }

        # Validate that at least one search parameter is provided
        if not inputs.trace_id and not inputs.service and not inputs.operation:
            return {
                "status": "error",
                "error": "Must provide at least one of: trace_id, service, or operation",
                "suggestion": "Specify a trace_id for exact lookup, or service/operation to search for traces"
            }

        from providers import get_trace_provider

        provider = get_trace_provider()
        result = provider.query(
            trace_id=inputs.trace_id,
            service=inputs.service,
            operation=inputs.operation,
            time_range=inputs.time_range,
            filters=inputs.filters
        )

        if result.success:
            # Check if we should save to file
            if _should_save_to_file(result.data):
                # Save to file
                trace_suffix = inputs.trace_id[:16] if inputs.trace_id else (inputs.service or "traces")
                output_path = _save_data_to_file(
                    {
                        "traces": result.data if isinstance(result.data, list) else [result.data],
                        "metadata": result.metadata,
                        "query_info": {
                            "trace_id": inputs.trace_id,
                            "service": inputs.service,
                            "operation": inputs.operation,
                            "time_range": inputs.time_range
                        }
                    },
                    "traces",
                    trace_suffix.replace(".", "_")[:30]
                )

                # Create summary
                trace_count = len(result.data) if isinstance(result.data, list) else 1
                summary = {
                    "trace_count": trace_count,
                    "sample": result.data[0] if isinstance(result.data, list) and result.data else result.data
                }

                # Emit artifact marker
                print(f"Artifact available: {output_path}")

                return {
                    "status": "success",
                    "output_file": output_path,
                    "summary": summary,
                    "provider": result.metadata.get("provider", "unknown"),
                    "message": f"Retrieved {trace_count} trace(s). Full data saved to {output_path}. Use with generate_trace_visualization(input_file='{output_path}')"
                }
            else:
                # Small result - return inline
                return {
                    "status": "success",
                    "data": result.data,
                    "metadata": result.metadata,
                    "provider": result.metadata.get("provider", "unknown")
                }
        else:
            return create_error_response(
                Exception(result.error),
                "Trace query failed"
            )

    except Exception as e:
        logger.error(f"Error querying traces: {e}", exc_info=True)
        return create_error_response(e, "Trace query failed")


class SearchCodeInput(UfInput):
    """Universal code search interface"""
    query: str = Field(..., description="Search query (supports regex, literal strings, or natural language)")
    repo: Optional[str] = Field(None, description="Repository name/path to search in")
    file_patterns: Optional[List[str]] = Field(None, description="File patterns to include (e.g., ['*.py', '*.yaml'])")
    branch: str = Field(default="main", description="Branch to search")
    save_to_file: bool = Field(default=True, description="Save large results to file (recommended)")
    output_file: Optional[str] = Field(None, description="Explicit output file path")


@uf(name="search_code", version="2.0.0",
   description="Search source code repositories. IMPORTANT: Large search results (>50 matches) are saved to files automatically. Work with file paths, not inline data. Use this to find where errors are logged, how services are configured, or locate specific code patterns.")
def search_code(inputs: SearchCodeInput) -> dict:
    """Search code using the configured code provider"""
    try:
        # Handle both dict and Pydantic model inputs
        if isinstance(inputs, dict):
            inputs = SearchCodeInput(**inputs)
        
        # Input validation
        if not inputs.query.strip():
            return {
                "status": "error",
                "error": "Search query cannot be empty",
                "suggestion": "Provide a search term like 'error', 'class UserService', or a specific function name"
            }

        if len(inputs.query) > 500:
            return {
                "status": "error",
                "error": "Query too long (max 500 characters)",
                "suggestion": "Simplify your search query or search for a more specific term"
            }

        from providers import get_code_provider

        provider = get_code_provider()
        result = provider.search(
            query=inputs.query,
            repo=inputs.repo,
            file_patterns=inputs.file_patterns,
            branch=inputs.branch
        )

        if result.success:
            # Check if we should save to file
            if _should_save_to_file(result.data):
                # Save to file
                output_path = _save_data_to_file(
                    {
                        "matches": result.data if isinstance(result.data, list) else [result.data],
                        "metadata": result.metadata,
                        "query_info": {
                            "query": inputs.query,
                            "repo": inputs.repo,
                            "file_patterns": inputs.file_patterns,
                            "branch": inputs.branch
                        }
                    },
                    "code_search",
                    inputs.query.replace(" ", "_")[:30]
                )

                # Create summary
                match_count = len(result.data) if isinstance(result.data, list) else 1
                summary = {
                    "total_matches": match_count,
                    "sample": result.data[:3] if isinstance(result.data, list) else result.data
                }

                # Emit artifact marker
                print(f"Artifact available: {output_path}")

                return {
                    "status": "success",
                    "output_file": output_path,
                    "summary": summary,
                    "provider": result.metadata.get("provider", "unknown"),
                    "message": f"Found {match_count} code match(es). Full results saved to {output_path}. Use head/jq to inspect: head -50 {output_path}"
                }
            else:
                # Small result - return inline
                return {
                    "status": "success",
                    "data": result.data,
                    "metadata": result.metadata,
                    "provider": result.metadata.get("provider", "unknown")
                }
        else:
            return create_error_response(
                Exception(result.error),
                "Code search failed"
            )

    except Exception as e:
        logger.error(f"Error searching code: {e}", exc_info=True)
        return create_error_response(e, "Code search failed")


class QueryCommitsInput(UfInput):
    """Universal commit history query interface"""
    repo: str = Field(..., description="Repository name/path (e.g., 'owner/repo')")
    branch: str = Field(default="main", description="Branch to get commits from")
    limit: int = Field(default=20, description="Maximum number of commits to return (max 50)")
    since: Optional[str] = Field(None, description="Get commits since this time ('24h', '7d', or ISO timestamp)")
    author: Optional[str] = Field(None, description="Filter by commit author")
    path: Optional[str] = Field(None, description="Filter commits that touched specific file/directory path")
    include_diffs: bool = Field(default=True, description="Include file diffs in the response")
    save_to_file: bool = Field(default=True, description="Save large results to file (recommended, especially with diffs)")
    output_file: Optional[str] = Field(None, description="Explicit output file path")


@uf(name="query_commits", version="2.0.0",
   description="Get recent commit history from code repositories with diffs. IMPORTANT: Large results (>20 commits or with diffs) are saved to files automatically. Work with file paths for commit history. Use this to investigate recent code changes that may have caused issues.")
def query_commits(inputs: QueryCommitsInput) -> dict:
    """Query commit history using the configured code provider"""
    try:
        # Handle both dict and Pydantic model inputs
        if isinstance(inputs, dict):
            inputs = QueryCommitsInput(**inputs)
        
        # Input validation
        if not inputs.repo.strip():
            return {
                "status": "error",
                "error": "Repository name cannot be empty",
                "suggestion": "Provide a repository name like 'owner/repo'"
            }

        # Cap limit to reasonable value
        safe_limit = min(inputs.limit, 50)
        if inputs.limit > 50:
            logger.warning(f"Limit {inputs.limit} capped to 50 for performance")

        # Validate since format if provided
        if inputs.since:
            import re
            valid_since = re.match(r'^(\d+[hd]|[\d\-:T+Z\.]+)$', inputs.since)
            if not valid_since:
                return {
                    "status": "error",
                    "error": f"Invalid 'since' format: {inputs.since}",
                    "suggestion": "Use format like '24h' (24 hours), '7d' (7 days), or ISO timestamp"
                }

        from providers import get_code_provider

        provider = get_code_provider()
        result = provider.get_commits(
            repo=inputs.repo,
            branch=inputs.branch,
            limit=safe_limit,
            since=inputs.since,
            author=inputs.author,
            path=inputs.path,
            include_diffs=inputs.include_diffs
        )

        if result.success:
            # Check if we should save to file (always for commits with diffs, or if count is large)
            commit_count = len(result.data) if isinstance(result.data, list) else 1
            should_save = inputs.include_diffs or _should_save_to_file(result.data, threshold_items=20)

            if should_save:
                # Save to file
                repo_suffix = inputs.repo.replace("/", "_")[:30]
                output_path = _save_data_to_file(
                    {
                        "commits": result.data if isinstance(result.data, list) else [result.data],
                        "metadata": result.metadata,
                        "query_info": {
                            "repo": inputs.repo,
                            "branch": inputs.branch,
                            "since": inputs.since,
                            "author": inputs.author,
                            "path": inputs.path,
                            "include_diffs": inputs.include_diffs
                        }
                    },
                    "commits",
                    repo_suffix
                )

                # Create summary
                summary = {
                    "total_commits": commit_count,
                    "has_diffs": inputs.include_diffs,
                    "sample": result.data[:3] if isinstance(result.data, list) else result.data
                }

                # Emit artifact marker
                print(f"Artifact available: {output_path}")

                return {
                    "status": "success",
                    "output_file": output_path,
                    "summary": summary,
                    "provider": result.metadata.get("provider", "unknown"),
                    "message": f"Retrieved {commit_count} commit(s){' with diffs' if inputs.include_diffs else ''}. Full data saved to {output_path}. Use head/jq to inspect: head -100 {output_path}"
                }
            else:
                # Small result without diffs - return inline
                return {
                    "status": "success",
                    "data": result.data,
                    "metadata": result.metadata,
                    "provider": result.metadata.get("provider", "unknown")
                }
        else:
            return create_error_response(
                Exception(result.error),
                "Commit query failed"
            )

    except Exception as e:
        logger.error(f"Error querying commits: {e}", exc_info=True)
        return create_error_response(e, "Commit query failed")


class GatherInvestigationDataInput(UfInput):
    """Input for gathering observability signals across multiple data sources"""
    time_range: str = Field(..., description="Time range for data gathering: '15m', '1h', '24h'")

    # Optional filters - LLM can choose what to gather
    include_logs: bool = Field(default=False, description="Gather log data")
    include_metrics: bool = Field(default=False, description="Gather metric data")
    include_traces: bool = Field(default=False, description="Gather trace data")
    include_commits: bool = Field(default=False, description="Gather commit history")

    # Optional parameters for each data source
    log_query: Optional[str] = Field(None, description="Log search query (required if include_logs=True)")
    log_filters: Optional[Dict[str, str]] = Field(None, description="Additional log filters")
    log_limit: int = Field(default=100, description="Max log entries to return")

    metric_names: Optional[List[str]] = Field(None, description="List of metrics to query (required if include_metrics=True)")
    metric_dimensions: Optional[Dict[str, str]] = Field(None, description="Metric dimensions/tags filter")

    trace_service: Optional[str] = Field(None, description="Service name for trace search")
    trace_filters: Optional[Dict[str, str]] = Field(None, description="Additional trace filters")

    commit_repo: Optional[str] = Field(None, description="Repository for commit history (required if include_commits=True)")
    commit_branch: str = Field(default="main", description="Branch to get commits from")
    commit_limit: int = Field(default=20, description="Max commits to return")


@uf(name="gather_investigation_data", version="2.0.0",
   description="Efficiently gather observability signals (logs, metrics, traces, commits) in parallel for a time window. CRITICAL: All data is saved to separate files automatically to prevent context bloat. Returns file paths and summaries, NOT raw data. Use during Phase 3 (CORRELATE) of RCA to build timeline. Chain with visualization tools using returned file paths.")
def gather_investigation_data(inputs: GatherInvestigationDataInput) -> dict:
    """Gather data from multiple sources in parallel - NO correlation logic, just efficient fetching"""
    import concurrent.futures
    from providers import get_log_provider, get_metric_provider, get_trace_provider, get_code_provider

    # Input validation
    if not validate_time_range(inputs.time_range):
        return {
            "status": "error",
            "error": f"Invalid time_range '{inputs.time_range}'. Use format: 15m, 1h, 24h",
            "suggestion": "Use a valid time range like '15m' (15 minutes), '1h' (1 hour), or '24h' (24 hours)"
        }

    # Validate required parameters for enabled sources
    if inputs.include_logs and not inputs.log_query:
        return {
            "status": "error",
            "error": "log_query is required when include_logs=True",
            "suggestion": "Provide a log search query or set include_logs=False"
        }

    if inputs.include_metrics and not inputs.metric_names:
        return {
            "status": "error",
            "error": "metric_names is required when include_metrics=True",
            "suggestion": "Provide a list of metric names or set include_metrics=False"
        }

    if inputs.include_commits and not inputs.commit_repo:
        return {
            "status": "error",
            "error": "commit_repo is required when include_commits=True",
            "suggestion": "Provide a repository name or set include_commits=False"
        }

    # Check if at least one source is enabled
    if not any([inputs.include_logs, inputs.include_metrics, inputs.include_traces, inputs.include_commits]):
        return {
            "status": "error",
            "error": "At least one data source must be enabled",
            "suggestion": "Set include_logs, include_metrics, include_traces, or include_commits to True"
        }

    try:
        results = {
            "time_range": inputs.time_range,
            "sources_requested": [],
            "sources_succeeded": [],
            "sources_failed": [],
            "data": {}
        }

        # Execute queries in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            # Submit log query
            if inputs.include_logs:
                results["sources_requested"].append("logs")
                futures["logs"] = executor.submit(
                    get_log_provider().query,
                    query=inputs.log_query,
                    time_range=inputs.time_range,
                    filters=inputs.log_filters,
                    limit=min(inputs.log_limit, 500)
                )

            # Submit metric queries
            if inputs.include_metrics:
                results["sources_requested"].append("metrics")
                # Query all metrics in parallel
                metric_futures = []
                for metric_name in inputs.metric_names:
                    metric_futures.append(executor.submit(
                        get_metric_provider().query,
                        metric_name=metric_name,
                        time_range=inputs.time_range,
                        dimensions=inputs.metric_dimensions
                    ))
                futures["metrics"] = metric_futures

            # Submit trace query
            if inputs.include_traces:
                results["sources_requested"].append("traces")
                futures["traces"] = executor.submit(
                    get_trace_provider().query,
                    service=inputs.trace_service,
                    time_range=inputs.time_range,
                    filters=inputs.trace_filters
                )

            # Submit commit query
            if inputs.include_commits:
                results["sources_requested"].append("commits")
                futures["commits"] = executor.submit(
                    get_code_provider().get_commits,
                    repo=inputs.commit_repo,
                    branch=inputs.commit_branch,
                    limit=min(inputs.commit_limit, 50),
                    since=inputs.time_range
                )

            # NEW: Collect results and save to files instead of returning inline
            file_paths = {}
            summaries = {}

            # Logs
            if "logs" in futures:
                try:
                    log_result = futures["logs"].result(timeout=30)
                    if log_result.success:
                        # Normalize log entries
                        normalized_logs = [
                            normalize_log_entry(entry, log_result.metadata.get("provider", "unknown"))
                            for entry in log_result.data
                        ]

                        # Save to file
                        log_file = _save_data_to_file(
                            {
                                "logs": normalized_logs,
                                "metadata": log_result.metadata,
                                "query": inputs.log_query,
                                "time_range": inputs.time_range
                            },
                            "investigation_logs",
                            inputs.log_query.replace(" ", "_")[:20] if inputs.log_query else "logs"
                        )
                        file_paths["logs"] = log_file
                        summaries["logs"] = _create_summary_for_logs(normalized_logs)
                        results["sources_succeeded"].append("logs")
                        print(f"Artifact available: {log_file}")
                    else:
                        results["sources_failed"].append("logs")
                        summaries["logs"] = {"error": log_result.error}
                        logger.warning(f"Log query failed: {log_result.error}")
                except Exception as e:
                    results["sources_failed"].append("logs")
                    summaries["logs"] = {"error": str(e)}
                    logger.error(f"Log query exception: {e}")

            # Metrics
            if "metrics" in futures:
                try:
                    metric_results = []
                    for idx, future in enumerate(futures["metrics"]):
                        metric_result = future.result(timeout=30)
                        if metric_result.success:
                            metric_results.append({
                                "metric_name": inputs.metric_names[idx],
                                "data": metric_result.data,
                                "metadata": metric_result.metadata
                            })

                    if metric_results:
                        # Save to file
                        metric_file = _save_data_to_file(
                            {
                                "series": metric_results,
                                "time_range": inputs.time_range,
                                "dimensions": inputs.metric_dimensions
                            },
                            "investigation_metrics",
                            "_".join(inputs.metric_names)[:30] if inputs.metric_names else "metrics"
                        )
                        file_paths["metrics"] = metric_file
                        summaries["metrics"] = {
                            "metric_count": len(metric_results),
                            "metric_names": [m["metric_name"] for m in metric_results]
                        }
                        results["sources_succeeded"].append("metrics")
                        print(f"Artifact available: {metric_file}")
                except Exception as e:
                    results["sources_failed"].append("metrics")
                    summaries["metrics"] = {"error": str(e)}
                    logger.error(f"Metric query exception: {e}")

            # Traces
            if "traces" in futures:
                try:
                    trace_result = futures["traces"].result(timeout=30)
                    if trace_result.success:
                        # Save to file
                        trace_file = _save_data_to_file(
                            {
                                "traces": trace_result.data if isinstance(trace_result.data, list) else [trace_result.data],
                                "metadata": trace_result.metadata,
                                "service": inputs.trace_service,
                                "time_range": inputs.time_range
                            },
                            "investigation_traces",
                            inputs.trace_service[:30] if inputs.trace_service else "traces"
                        )
                        file_paths["traces"] = trace_file
                        trace_count = len(trace_result.data) if isinstance(trace_result.data, list) else 1
                        summaries["traces"] = {
                            "trace_count": trace_count,
                            "sample": trace_result.data[0] if isinstance(trace_result.data, list) and trace_result.data else None
                        }
                        results["sources_succeeded"].append("traces")
                        print(f"Artifact available: {trace_file}")
                    else:
                        results["sources_failed"].append("traces")
                        summaries["traces"] = {"error": trace_result.error}
                        logger.warning(f"Trace query failed: {trace_result.error}")
                except Exception as e:
                    results["sources_failed"].append("traces")
                    summaries["traces"] = {"error": str(e)}
                    logger.error(f"Trace query exception: {e}")

            # Commits
            if "commits" in futures:
                try:
                    commit_result = futures["commits"].result(timeout=30)
                    if commit_result.success:
                        # Save to file
                        repo_name = inputs.commit_repo.replace("/", "_")[:30]
                        commit_file = _save_data_to_file(
                            {
                                "commits": commit_result.data if isinstance(commit_result.data, list) else [commit_result.data],
                                "metadata": commit_result.metadata,
                                "repo": inputs.commit_repo,
                                "branch": inputs.commit_branch,
                                "time_range": inputs.time_range
                            },
                            "investigation_commits",
                            repo_name
                        )
                        file_paths["commits"] = commit_file
                        commit_count = len(commit_result.data) if isinstance(commit_result.data, list) else 1
                        summaries["commits"] = {
                            "commit_count": commit_count,
                            "sample": commit_result.data[:3] if isinstance(commit_result.data, list) else commit_result.data
                        }
                        results["sources_succeeded"].append("commits")
                        print(f"Artifact available: {commit_file}")
                    else:
                        results["sources_failed"].append("commits")
                        summaries["commits"] = {"error": commit_result.error}
                        logger.warning(f"Commit query failed: {commit_result.error}")
                except Exception as e:
                    results["sources_failed"].append("commits")
                    summaries["commits"] = {"error": str(e)}
                    logger.error(f"Commit query exception: {e}")

        # Build summary message
        success_count = len(results["sources_succeeded"])
        total_count = len(results["sources_requested"])

        if success_count == 0:
            return {
                "status": "error",
                "error": "All data sources failed",
                "summaries": summaries
            }

        # Build descriptive summary
        summary_parts = []
        for source in results["sources_succeeded"]:
            if source in summaries:
                if source == "logs":
                    summary_parts.append(f"{summaries[source].get('total_logs', 0)} logs")
                elif source == "metrics":
                    summary_parts.append(f"{summaries[source].get('metric_count', 0)} metrics")
                elif source == "traces":
                    summary_parts.append(f"{summaries[source].get('trace_count', 0)} traces")
                elif source == "commits":
                    summary_parts.append(f"{summaries[source].get('commit_count', 0)} commits")

        return {
            "status": "success" if success_count == total_count else "partial_success",
            "file_paths": file_paths,
            "summaries": summaries,
            "metadata": {
                "time_range": inputs.time_range,
                "sources_requested": results["sources_requested"],
                "sources_succeeded": results["sources_succeeded"],
                "sources_failed": results["sources_failed"]
            },
            "message": f"Gathered {', '.join(summary_parts)} from {success_count}/{total_count} sources. All data saved to files. Use file_paths to process data or pass to visualization tools."
        }

    except Exception as e:
        logger.error(f"Error gathering investigation data: {e}", exc_info=True)
        return create_error_response(e, "Data gathering failed")


# ============================================================================
# File Validation Tools
# ============================================================================

class InspectJsonFileInput(UfInput):
    """Input for JSON file inspection"""
    file_path: str = Field(..., description="Path to JSON file to inspect")
    show_sample: bool = Field(default=True, description="Show sample data from the file")
    sample_size: int = Field(default=3, description="Number of items to show in sample")


@uf(name="inspect_json_file", version="1.0.0",
   description="Quick inspection of JSON file structure, size, and sample data. Use this to validate observability data files before passing to visualization tools. Returns structure info without loading full file into context.")
def inspect_json_file(inputs: InspectJsonFileInput) -> dict:
    """Inspect JSON file structure without loading all data"""
    try:
        from core.workspace_security import validate_workspace_path
        import os

        # Validate path
        file_path = validate_workspace_path(inputs.file_path, "JSON file inspection")

        if not os.path.exists(file_path):
            return {
                "status": "error",
                "error": f"File not found: {inputs.file_path}"
            }

        # Get file size
        file_size = os.path.getsize(file_path)

        # Load and inspect JSON
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Build inspection report
        inspection = {
            "file_path": inputs.file_path,
            "file_size_bytes": file_size,
            "file_size_kb": round(file_size / 1024, 2),
            "data_type": type(data).__name__
        }

        # Type-specific inspection
        if isinstance(data, dict):
            inspection["keys"] = list(data.keys())
            inspection["key_count"] = len(data.keys())

            # Check for common observability data structures
            if "logs" in data:
                log_count = len(data["logs"]) if isinstance(data["logs"], list) else 0
                inspection["logs_count"] = log_count
                if inputs.show_sample and log_count > 0:
                    inspection["logs_sample"] = data["logs"][:inputs.sample_size]

            if "series" in data:
                series_count = len(data["series"]) if isinstance(data["series"], list) else 0
                inspection["series_count"] = series_count
                if inputs.show_sample and series_count > 0:
                    inspection["series_sample"] = data["series"][:inputs.sample_size]

            if "traces" in data:
                trace_count = len(data["traces"]) if isinstance(data["traces"], list) else 0
                inspection["traces_count"] = trace_count
                if inputs.show_sample and trace_count > 0:
                    inspection["traces_sample"] = data["traces"][:inputs.sample_size]

            if "commits" in data:
                commit_count = len(data["commits"]) if isinstance(data["commits"], list) else 0
                inspection["commits_count"] = commit_count
                if inputs.show_sample and commit_count > 0:
                    inspection["commits_sample"] = data["commits"][:inputs.sample_size]

            if "matches" in data:
                match_count = len(data["matches"]) if isinstance(data["matches"], list) else 0
                inspection["matches_count"] = match_count
                if inputs.show_sample and match_count > 0:
                    inspection["matches_sample"] = data["matches"][:inputs.sample_size]

        elif isinstance(data, list):
            inspection["list_length"] = len(data)
            if inputs.show_sample and len(data) > 0:
                inspection["sample"] = data[:inputs.sample_size]

        return {
            "status": "success",
            "inspection": inspection,
            "message": f"File inspection complete. Size: {inspection['file_size_kb']}KB, Type: {inspection['data_type']}"
        }

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error": f"Invalid JSON file: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error inspecting JSON file: {e}", exc_info=True)
        return create_error_response(e, "File inspection failed")
