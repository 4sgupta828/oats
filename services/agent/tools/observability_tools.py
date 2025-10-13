"""Universal Observability Tools for OATS Agent

These tools provide a consistent interface for the LLM to interact with different
data sources (logs, metrics, traces, code) regardless of the underlying provider.
The LLM only needs to know about these 4 universal tools, not 20+ provider-specific ones.
"""

from pydantic import Field
from typing import Optional, Dict, List
from core.sdk import uf, UfInput
from core.logging_config import get_logger

logger = get_logger('observability_tools')


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
        from providers import get_log_provider
        
        provider = get_log_provider()
        result = provider.query(
            query=inputs.query,
            time_range=inputs.time_range,
            filters=inputs.filters,
            limit=inputs.limit
        )
        
        if result.success:
            return {
                "status": "success",
                "data": result.data,
                "metadata": result.metadata,
                "provider": result.metadata.get("provider", "unknown")
            }
        else:
            return {
                "status": "error",
                "error": result.error,
                "provider": result.metadata.get("provider", "unknown")
            }
            
    except Exception as e:
        logger.error(f"Error querying logs: {e}")
        return {
            "status": "error",
            "error": f"Failed to query logs: {str(e)}"
        }


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
            return {
                "status": "error",
                "error": result.error,
                "provider": result.metadata.get("provider", "unknown")
            }
            
    except Exception as e:
        logger.error(f"Error querying metrics: {e}")
        return {
            "status": "error",
            "error": f"Failed to query metrics: {str(e)}"
        }


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
            return {
                "status": "error",
                "error": result.error,
                "provider": result.metadata.get("provider", "unknown")
            }
            
    except Exception as e:
        logger.error(f"Error querying traces: {e}")
        return {
            "status": "error",
            "error": f"Failed to query traces: {str(e)}"
        }


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
            return {
                "status": "error",
                "error": result.error,
                "provider": result.metadata.get("provider", "unknown")
            }
            
    except Exception as e:
        logger.error(f"Error searching code: {e}")
        return {
            "status": "error",
            "error": f"Failed to search code: {str(e)}"
        }


class CorrelateSignalsInput(UfInput):
    """Input for correlating signals across multiple data sources"""
    time_range: str = Field(..., description="Time range for correlation analysis")
    error_pattern: str = Field(..., description="Error pattern to search for in logs")
    metric_name: str = Field(..., description="Metric to correlate with errors")
    service: Optional[str] = Field(None, description="Service name to focus correlation on")


@uf(name="correlate_signals", version="1.0.0",
   description="Correlate data across logs, metrics, and traces for a specific time window. Use this to find relationships between errors, performance degradation, and code changes.")
def correlate_signals(inputs: CorrelateSignalsInput) -> dict:
    """Execute queries across all data sources and correlate results"""
    try:
        import concurrent.futures
        from providers import get_log_provider, get_metric_provider, get_trace_provider
        
        results = {
            "time_window": inputs.time_range,
            "correlation_score": 0.0,
            "findings": {}
        }
        
        # Execute queries in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submit all queries
            log_future = executor.submit(
                get_log_provider().query,
                query=inputs.error_pattern,
                time_range=inputs.time_range,
                limit=50
            )
            
            metric_future = executor.submit(
                get_metric_provider().query,
                metric_name=inputs.metric_name,
                time_range=inputs.time_range
            )
            
            if inputs.service:
                trace_future = executor.submit(
                    get_trace_provider().query,
                    service=inputs.service,
                    time_range=inputs.time_range
                )
            else:
                trace_future = None
            
            # Collect results
            try:
                log_result = log_future.result(timeout=30)
                results['findings']['logs'] = log_result.data if log_result.success else None
            except Exception as e:
                results['findings']['logs'] = None
                logger.warning(f"Log query failed: {e}")
            
            try:
                metric_result = metric_future.result(timeout=30)
                results['findings']['metrics'] = metric_result.data if metric_result.success else None
            except Exception as e:
                results['findings']['metrics'] = None
                logger.warning(f"Metric query failed: {e}")
            
            if trace_future:
                try:
                    trace_result = trace_future.result(timeout=30)
                    results['findings']['traces'] = trace_result.data if trace_result.success else None
                except Exception as e:
                    results['findings']['traces'] = None
                    logger.warning(f"Trace query failed: {e}")
        
        # Calculate simple correlation score based on data availability
        available_sources = sum(1 for v in results['findings'].values() if v is not None)
        results['correlation_score'] = available_sources / len(results['findings'])
        
        return {
            "status": "success",
            "data": results
        }
        
    except Exception as e:
        logger.error(f"Error correlating signals: {e}")
        return {
            "status": "error",
            "error": f"Failed to correlate signals: {str(e)}"
        }
