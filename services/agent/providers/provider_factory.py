"""Provider factory for instantiating customer-specific provider implementations

This factory pattern allows us to dynamically create provider instances based on
customer configuration without hardcoding provider types in the universal tools.
"""

from typing import Dict, Type, Any, List
from .base_provider import LogProvider, MetricProvider, TraceProvider, CodeProvider

# Import provider implementations
try:
    from .logs.cloudwatch_provider import CloudWatchLogProvider
    from .logs.datadog_provider import DatadogLogProvider
    from .metrics.cloudwatch_provider import CloudWatchMetricProvider
    from .traces.xray_provider import XRayTraceProvider
    from .code.github_provider import GitHubCodeProvider
    _REAL_PROVIDERS_AVAILABLE = True
except ImportError:
    # Fall back to mock providers if dependencies are not available
    from .mock_provider import MockLogProvider, MockMetricProvider, MockTraceProvider, MockCodeProvider
    _REAL_PROVIDERS_AVAILABLE = False


class ProviderFactory:
    """Factory to instantiate providers based on customer config"""
    
    # Registry of available provider implementations
    if _REAL_PROVIDERS_AVAILABLE:
        LOG_PROVIDERS: Dict[str, Type[LogProvider]] = {
            "cloudwatch": CloudWatchLogProvider,
            "datadog": DatadogLogProvider,
        }
        
        METRIC_PROVIDERS: Dict[str, Type[MetricProvider]] = {
            "cloudwatch": CloudWatchMetricProvider,
        }
        
        TRACE_PROVIDERS: Dict[str, Type[TraceProvider]] = {
            "xray": XRayTraceProvider,
        }
        
        CODE_PROVIDERS: Dict[str, Type[CodeProvider]] = {
            "github": GitHubCodeProvider,
        }
    else:
        # Use mock providers when real dependencies are not available
        LOG_PROVIDERS: Dict[str, Type[LogProvider]] = {
            "mock": MockLogProvider,
        }
        
        METRIC_PROVIDERS: Dict[str, Type[MetricProvider]] = {
            "mock": MockMetricProvider,
        }
        
        TRACE_PROVIDERS: Dict[str, Type[TraceProvider]] = {
            "mock": MockTraceProvider,
        }
        
        CODE_PROVIDERS: Dict[str, Type[CodeProvider]] = {
            "mock": MockCodeProvider,
        }
    
    @classmethod
    def register_log_provider(cls, name: str, provider_class: Type[LogProvider]):
        """Register a log provider implementation"""
        cls.LOG_PROVIDERS[name] = provider_class
    
    @classmethod
    def register_metric_provider(cls, name: str, provider_class: Type[MetricProvider]):
        """Register a metric provider implementation"""
        cls.METRIC_PROVIDERS[name] = provider_class
    
    @classmethod
    def register_trace_provider(cls, name: str, provider_class: Type[TraceProvider]):
        """Register a trace provider implementation"""
        cls.TRACE_PROVIDERS[name] = provider_class
    
    @classmethod
    def register_code_provider(cls, name: str, provider_class: Type[CodeProvider]):
        """Register a code provider implementation"""
        cls.CODE_PROVIDERS[name] = provider_class
    
    @classmethod
    def create_log_provider(cls, config: Dict[str, Any]) -> LogProvider:
        """Create a log provider instance from config"""
        provider_name = config.get('provider')
        if not provider_name:
            raise ValueError("Log provider config missing 'provider' field")
        
        provider_class = cls.LOG_PROVIDERS.get(provider_name)
        if not provider_class:
            available = list(cls.LOG_PROVIDERS.keys())
            raise ValueError(f"Unknown log provider: {provider_name}. Available: {available}")
        
        provider_config = config.get('config', {})
        return provider_class(provider_config)
    
    @classmethod
    def create_metric_provider(cls, config: Dict[str, Any]) -> MetricProvider:
        """Create a metric provider instance from config"""
        provider_name = config.get('provider')
        if not provider_name:
            raise ValueError("Metric provider config missing 'provider' field")
        
        provider_class = cls.METRIC_PROVIDERS.get(provider_name)
        if not provider_class:
            available = list(cls.METRIC_PROVIDERS.keys())
            raise ValueError(f"Unknown metric provider: {provider_name}. Available: {available}")
        
        provider_config = config.get('config', {})
        return provider_class(provider_config)
    
    @classmethod
    def create_trace_provider(cls, config: Dict[str, Any]) -> TraceProvider:
        """Create a trace provider instance from config"""
        provider_name = config.get('provider')
        if not provider_name:
            raise ValueError("Trace provider config missing 'provider' field")
        
        provider_class = cls.TRACE_PROVIDERS.get(provider_name)
        if not provider_class:
            available = list(cls.TRACE_PROVIDERS.keys())
            raise ValueError(f"Unknown trace provider: {provider_name}. Available: {available}")
        
        provider_config = config.get('config', {})
        return provider_class(provider_config)
    
    @classmethod
    def create_code_provider(cls, config: Dict[str, Any]) -> CodeProvider:
        """Create a code provider instance from config"""
        provider_name = config.get('provider')
        if not provider_name:
            raise ValueError("Code provider config missing 'provider' field")
        
        provider_class = cls.CODE_PROVIDERS.get(provider_name)
        if not provider_class:
            available = list(cls.CODE_PROVIDERS.keys())
            raise ValueError(f"Unknown code provider: {provider_name}. Available: {available}")
        
        provider_config = config.get('config', {})
        return provider_class(provider_config)
    
    @classmethod
    def list_available_providers(cls) -> Dict[str, List[str]]:
        """List all available provider implementations"""
        return {
            'logs': list(cls.LOG_PROVIDERS.keys()),
            'metrics': list(cls.METRIC_PROVIDERS.keys()),
            'traces': list(cls.TRACE_PROVIDERS.keys()),
            'code': list(cls.CODE_PROVIDERS.keys())
        }
