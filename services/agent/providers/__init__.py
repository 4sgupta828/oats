"""Universal Data Source Abstraction Layer for OATS Agent

This module provides a provider abstraction layer that allows the agent to work with
different data sources (logs, metrics, traces, code) through universal interfaces
while delegating to customer-specific provider implementations.

Architecture:
- Universal Tools: LLM sees consistent interfaces (query_logs, query_metrics, etc.)
- Provider Abstractions: Abstract base classes for each data source type
- Provider Implementations: Customer-specific implementations (CloudWatch, Datadog, etc.)
- Provider Factory: Instantiates providers based on customer configuration
"""

from typing import Optional, Dict, Any
from .base_provider import LogProvider, MetricProvider, TraceProvider, CodeProvider, ProviderResult
from .provider_factory import ProviderFactory
from core.logging_config import get_logger

logger = get_logger('providers')

# Global provider instances (initialized once per customer)
_log_provider: Optional[LogProvider] = None
_metric_provider: Optional[MetricProvider] = None
_trace_provider: Optional[TraceProvider] = None
_code_provider: Optional[CodeProvider] = None
_providers_initialized = False

def initialize_providers(customer_config: Dict[str, Any]):
    """Initialize providers from customer config (safe to call multiple times)

    Args:
        customer_config: Customer configuration dictionary with 'observability' section

    Note:
        This function is idempotent - calling it multiple times will only initialize once.
        Failed provider initialization will log errors but not prevent other providers from loading.
    """
    global _log_provider, _metric_provider, _trace_provider, _code_provider
    global _providers_initialized

    if _providers_initialized:
        logger.info("Providers already initialized, skipping")
        return

    logger.info("Initializing observability providers...")

    observability = customer_config.get('observability', {})

    if not observability:
        logger.warning("No observability configuration found")
        _providers_initialized = True
        return

    # Initialize each provider with error handling
    if 'logs' in observability:
        try:
            _log_provider = ProviderFactory.create_log_provider(observability['logs'])
            logger.info(f"✓ Log provider initialized: {observability['logs'].get('provider')}")
        except Exception as e:
            logger.error(f"✗ Failed to initialize log provider: {e}")
            _log_provider = None

    if 'metrics' in observability:
        try:
            _metric_provider = ProviderFactory.create_metric_provider(observability['metrics'])
            logger.info(f"✓ Metric provider initialized: {observability['metrics'].get('provider')}")
        except Exception as e:
            logger.error(f"✗ Failed to initialize metric provider: {e}")
            _metric_provider = None

    if 'traces' in observability:
        try:
            _trace_provider = ProviderFactory.create_trace_provider(observability['traces'])
            logger.info(f"✓ Trace provider initialized: {observability['traces'].get('provider')}")
        except Exception as e:
            logger.error(f"✗ Failed to initialize trace provider: {e}")
            _trace_provider = None

    if 'code' in observability:
        try:
            _code_provider = ProviderFactory.create_code_provider(observability['code'])
            logger.info(f"✓ Code provider initialized: {observability['code'].get('provider')}")
        except Exception as e:
            logger.error(f"✗ Failed to initialize code provider: {e}")
            _code_provider = None

    _providers_initialized = True

    # Summary
    initialized_count = sum(1 for p in [_log_provider, _metric_provider, _trace_provider, _code_provider] if p is not None)
    logger.info(f"Provider initialization complete: {initialized_count}/4 providers active")

def get_log_provider() -> LogProvider:
    if not _log_provider:
        raise RuntimeError("Log provider not initialized. Call initialize_providers() first.")
    return _log_provider

def get_metric_provider() -> MetricProvider:
    if not _metric_provider:
        raise RuntimeError("Metric provider not initialized. Call initialize_providers() first.")
    return _metric_provider

def get_trace_provider() -> TraceProvider:
    if not _trace_provider:
        raise RuntimeError("Trace provider not initialized. Call initialize_providers() first.")
    return _trace_provider

def get_code_provider() -> CodeProvider:
    if not _code_provider:
        raise RuntimeError("Code provider not initialized. Call initialize_providers() first.")
    return _code_provider

# Export key classes for external use
__all__ = [
    'LogProvider', 'MetricProvider', 'TraceProvider', 'CodeProvider', 'ProviderResult',
    'ProviderFactory', 'initialize_providers',
    'get_log_provider', 'get_metric_provider', 'get_trace_provider', 'get_code_provider'
]
