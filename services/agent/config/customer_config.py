"""Customer configuration management for provider initialization"""

import os
import yaml
from typing import Dict, Any, Optional
from core.logging_config import get_logger

logger = get_logger('customer_config')


class CustomerConfig:
    """Manages customer-specific provider configurations"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.environ.get('CUSTOMER_CONFIG_PATH', 'config/customer-config.yaml')
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load customer configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = yaml.safe_load(f)
                logger.info(f"Loaded customer config from {self.config_path}")
            else:
                # Use default configuration for development
                self.config = self._get_default_config()
                logger.warning(f"Config file {self.config_path} not found, using default config")
        except Exception as e:
            logger.error(f"Failed to load customer config: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for development/testing"""
        return {
            'customer_id': 'default',
            'environment': 'development',
            'observability': {
                'logs': {
                    'provider': 'cloudwatch',
                    'config': {
                        'region': 'us-east-1',
                        'log_groups': ['/aws/ecs/api-service', '/aws/lambda/checkout'],
                        'credentials': {
                            'role_arn': None  # Will use default AWS credentials
                        }
                    }
                },
                'metrics': {
                    'provider': 'cloudwatch',
                    'config': {
                        'region': 'us-east-1',
                        'namespace': 'AWS/EC2',
                        'credentials': {
                            'role_arn': None
                        }
                    }
                },
                'traces': {
                    'provider': 'xray',
                    'config': {
                        'region': 'us-east-1',
                        'credentials': {
                            'role_arn': None
                        }
                    }
                },
                'code': {
                    'provider': 'github',
                    'config': {
                        'token': os.environ.get('GITHUB_TOKEN'),
                        'org': 'your-org',
                        'repos': ['your-repo']
                    }
                }
            }
        }
    
    def get_customer_id(self) -> str:
        """Get customer ID"""
        return self.config.get('customer_id', 'default')
    
    def get_environment(self) -> str:
        """Get environment"""
        return self.config.get('environment', 'development')
    
    def get_observability_config(self) -> Dict[str, Any]:
        """Get observability configuration"""
        return self.config.get('observability', {})
    
    def get_log_config(self) -> Dict[str, Any]:
        """Get log provider configuration"""
        return self.get_observability_config().get('logs', {})
    
    def get_metric_config(self) -> Dict[str, Any]:
        """Get metric provider configuration"""
        return self.get_observability_config().get('metrics', {})
    
    def get_trace_config(self) -> Dict[str, Any]:
        """Get trace provider configuration"""
        return self.get_observability_config().get('traces', {})
    
    def get_code_config(self) -> Dict[str, Any]:
        """Get code provider configuration"""
        return self.get_observability_config().get('code', {})
    
    def validate_config(self) -> bool:
        """Validate that all required configuration is present"""
        try:
            obs_config = self.get_observability_config()
            
            # Check that at least one provider is configured
            if not any(obs_config.get(key) for key in ['logs', 'metrics', 'traces', 'code']):
                logger.warning("No observability providers configured")
                return False
            
            # Validate individual provider configs
            for provider_type in ['logs', 'metrics', 'traces', 'code']:
                provider_config = obs_config.get(provider_type)
                if provider_config:
                    if 'provider' not in provider_config:
                        logger.error(f"{provider_type} provider missing 'provider' field")
                        return False
                    if 'config' not in provider_config:
                        logger.error(f"{provider_type} provider missing 'config' field")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Config validation failed: {e}")
            return False
    
    def get_provider_credentials(self, provider_type: str) -> Dict[str, str]:
        """Get credentials for a specific provider type"""
        provider_config = self.get_observability_config().get(provider_type, {})
        config = provider_config.get('config', {})
        credentials = config.get('credentials', {})
        
        # Replace environment variable references
        resolved_credentials = {}
        for key, value in credentials.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var = value[2:-1]  # Remove ${ and }
                resolved_credentials[key] = os.environ.get(env_var, value)
            else:
                resolved_credentials[key] = value
        
        return resolved_credentials


# Global customer config instance
_customer_config: Optional[CustomerConfig] = None


def get_customer_config() -> CustomerConfig:
    """Get the global customer config instance"""
    global _customer_config
    if _customer_config is None:
        _customer_config = CustomerConfig()
    return _customer_config


def initialize_customer_config(config_path: Optional[str] = None) -> CustomerConfig:
    """Initialize customer configuration"""
    global _customer_config
    _customer_config = CustomerConfig(config_path)
    return _customer_config
