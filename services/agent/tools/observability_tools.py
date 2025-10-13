"""Universal Observability Tools for OATS Agent

These tools provide a consistent interface for the LLM to interact with different
data sources (logs, metrics, traces, code) regardless of the underlying provider.
The LLM only needs to know about these 4 universal tools, not 20+ provider-specific ones.
"""

from pydantic import Field
from typing import Optional, Dict, List
from core.sdk import uf, UfInput
from core.logging_config import get_logger
import re

logger = get_logger('observability_tools')


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


@uf(name="query_logs", version="1.0.0",
   description="Search logs across configured log backends. Supports natural language queries that are translated to provider-specific syntax. Use this for investigating errors, warnings, and application behavior.")
def query_logs(inputs: QueryLogsInput) -> dict:
    """Search logs using the configured log provider"""
    try:
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


@uf(name="query_metrics", version="1.0.0",
   description="Query time-series metrics from monitoring systems. Use this to check resource utilization, request rates, error rates, latency percentiles.")
def query_metrics(inputs: QueryMetricsInput) -> dict:
    """Query metrics using the configured metric provider"""
    try:
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


@uf(name="query_traces", version="1.0.0",
   description="Search distributed traces. Use trace_id for specific trace lookup, or service+operation+filters to find problematic traces.")
def query_traces(inputs: QueryTracesInput) -> dict:
    """Query traces using the configured trace provider"""
    try:
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


@uf(name="search_code", version="1.0.0",
   description="Search source code repositories. Use this to find where errors are logged, how services are configured, or locate specific code patterns.")
def search_code(inputs: SearchCodeInput) -> dict:
    """Search code using the configured code provider"""
    try:
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


@uf(name="query_commits", version="1.0.0",
   description="Get recent commit history from code repositories with diffs. Use this to investigate recent code changes that may have caused issues, understand what changed in a specific file, or review deployment history.")
def query_commits(inputs: QueryCommitsInput) -> dict:
    """Query commit history using the configured code provider"""
    try:
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


@uf(name="gather_investigation_data", version="1.0.0",
   description="Efficiently gather observability signals (logs, metrics, traces, commits) in parallel for a time window. Returns raw timestamped data for LLM to analyze and correlate. Use during Phase 3 (CORRELATE) of RCA to build timeline.")
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

            # Collect results with timeout
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
                        results["data"]["logs"] = {
                            "entries": normalized_logs,
                            "count": len(normalized_logs),
                            "metadata": log_result.metadata
                        }
                        results["sources_succeeded"].append("logs")
                    else:
                        results["data"]["logs"] = {"error": log_result.error}
                        results["sources_failed"].append("logs")
                        logger.warning(f"Log query failed: {log_result.error}")
                except Exception as e:
                    results["data"]["logs"] = {"error": str(e)}
                    results["sources_failed"].append("logs")
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

                    results["data"]["metrics"] = {
                        "series": metric_results,
                        "count": len(metric_results)
                    }
                    results["sources_succeeded"].append("metrics")
                except Exception as e:
                    results["data"]["metrics"] = {"error": str(e)}
                    results["sources_failed"].append("metrics")
                    logger.error(f"Metric query exception: {e}")

            # Traces
            if "traces" in futures:
                try:
                    trace_result = futures["traces"].result(timeout=30)
                    if trace_result.success:
                        results["data"]["traces"] = {
                            "traces": trace_result.data,
                            "count": len(trace_result.data) if trace_result.data else 0,
                            "metadata": trace_result.metadata
                        }
                        results["sources_succeeded"].append("traces")
                    else:
                        results["data"]["traces"] = {"error": trace_result.error}
                        results["sources_failed"].append("traces")
                        logger.warning(f"Trace query failed: {trace_result.error}")
                except Exception as e:
                    results["data"]["traces"] = {"error": str(e)}
                    results["sources_failed"].append("traces")
                    logger.error(f"Trace query exception: {e}")

            # Commits
            if "commits" in futures:
                try:
                    commit_result = futures["commits"].result(timeout=30)
                    if commit_result.success:
                        results["data"]["commits"] = {
                            "commits": commit_result.data,
                            "count": len(commit_result.data) if commit_result.data else 0,
                            "metadata": commit_result.metadata
                        }
                        results["sources_succeeded"].append("commits")
                    else:
                        results["data"]["commits"] = {"error": commit_result.error}
                        results["sources_failed"].append("commits")
                        logger.warning(f"Commit query failed: {commit_result.error}")
                except Exception as e:
                    results["data"]["commits"] = {"error": str(e)}
                    results["sources_failed"].append("commits")
                    logger.error(f"Commit query exception: {e}")

        # Build summary message
        success_count = len(results["sources_succeeded"])
        total_count = len(results["sources_requested"])

        if success_count == 0:
            return {
                "status": "error",
                "error": "All data sources failed",
                "details": results
            }

        summary_parts = []
        if "logs" in results["data"] and "entries" in results["data"]["logs"]:
            summary_parts.append(f"{results['data']['logs']['count']} log entries")
        if "metrics" in results["data"] and "series" in results["data"]["metrics"]:
            summary_parts.append(f"{results['data']['metrics']['count']} metrics")
        if "traces" in results["data"] and "traces" in results["data"]["traces"]:
            summary_parts.append(f"{results['data']['traces']['count']} traces")
        if "commits" in results["data"] and "commits" in results["data"]["commits"]:
            summary_parts.append(f"{results['data']['commits']['count']} commits")

        return {
            "status": "success" if success_count == total_count else "partial_success",
            "data": results["data"],
            "metadata": {
                "time_range": inputs.time_range,
                "sources_requested": results["sources_requested"],
                "sources_succeeded": results["sources_succeeded"],
                "sources_failed": results["sources_failed"]
            },
            "message": f"Gathered {', '.join(summary_parts)} from {success_count}/{total_count} sources"
        }

    except Exception as e:
        logger.error(f"Error gathering investigation data: {e}", exc_info=True)
        return create_error_response(e, "Data gathering failed")
