"""CloudWatch Metrics provider implementation"""

import boto3
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from core.logging_config import get_logger
from ..base_provider import MetricProvider, ProviderResult

logger = get_logger('cloudwatch_metrics_provider')


class CloudWatchMetricProvider(MetricProvider):
    """CloudWatch Metrics provider implementation"""
    
    def __init__(self, config: Dict):
        self.region = config.get('region', 'us-east-1')
        self.namespace = config.get('namespace', 'AWS/EC2')
        self.role_arn = config.get('credentials', {}).get('role_arn')
        
        # Initialize boto3 client
        if self.role_arn:
            # Assume role if provided
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=self.role_arn,
                RoleSessionName='oats-agent-session'
            )
            credentials = assumed_role['Credentials']
            
            self.client = boto3.client(
                'cloudwatch',
                region_name=self.region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            # Use default credentials
            self.client = boto3.client('cloudwatch', region_name=self.region)
        
        logger.info(f"Initialized CloudWatch metrics provider for region {self.region}")
    
    def query(self, metric_name: str, 
              dimensions: Optional[Dict[str, str]] = None,
              time_range: str = "1h",
              aggregation: str = "avg") -> ProviderResult:
        """Query CloudWatch metrics"""
        
        try:
            # Parse time range
            end_time = datetime.utcnow()
            start_time, _ = self._parse_time_range(time_range, end_time)
            
            # Build dimensions
            dimension_list = []
            if dimensions:
                for key, value in dimensions.items():
                    dimension_list.append({
                        'Name': key,
                        'Value': value
                    })
            
            # Map aggregation function
            stat_map = {
                'avg': 'Average',
                'sum': 'Sum',
                'min': 'Minimum',
                'max': 'Maximum',
                'p95': 'p95',
                'p99': 'p99'
            }
            statistic = stat_map.get(aggregation, 'Average')
            
            # Query metrics
            response = self.client.get_metric_statistics(
                Namespace=self.namespace,
                MetricName=metric_name,
                Dimensions=dimension_list,
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5-minute periods
                Statistics=[statistic]
            )
            
            # Format results
            datapoints = response.get('Datapoints', [])
            formatted_data = []
            
            for point in datapoints:
                formatted_data.append({
                    'timestamp': point['Timestamp'].isoformat(),
                    'value': point[statistic],
                    'unit': point.get('Unit', 'None')
                })
            
            # Sort by timestamp
            formatted_data.sort(key=lambda x: x['timestamp'])
            
            return ProviderResult(
                success=True,
                data=formatted_data,
                metadata={
                    "provider": "cloudwatch",
                    "metric_name": metric_name,
                    "namespace": self.namespace,
                    "statistic": statistic,
                    "datapoint_count": len(formatted_data)
                }
            )
            
        except Exception as e:
            logger.error(f"CloudWatch metrics query failed: {e}")
            return ProviderResult(
                success=False,
                data=None,
                metadata={"provider": "cloudwatch"},
                error=str(e)
            )
    
    def list_metrics(self, prefix: Optional[str] = None) -> List[str]:
        """List available metrics"""
        try:
            kwargs = {'Namespace': self.namespace}
            if prefix:
                kwargs['MetricName'] = prefix
            
            paginator = self.client.get_paginator('list_metrics')
            metrics = []
            
            for page in paginator.paginate(**kwargs):
                for metric in page['Metrics']:
                    metrics.append(metric['MetricName'])
            
            return list(set(metrics))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Failed to list metrics: {e}")
            return []
    
    def get_metric_metadata(self, metric_name: str) -> Dict[str, str]:
        """Get metadata about a specific metric"""
        try:
            response = self.client.list_metrics(
                Namespace=self.namespace,
                MetricName=metric_name
            )
            
            metadata = {
                'namespace': self.namespace,
                'metric_name': metric_name
            }
            
            if response['Metrics']:
                # Get dimensions from first metric
                metric = response['Metrics'][0]
                metadata['dimensions'] = [dim['Name'] for dim in metric.get('Dimensions', [])]
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get metric metadata: {e}")
            return {'error': str(e)}
    
    def _parse_time_range(self, time_range: str, end_time: datetime) -> tuple[datetime, datetime]:
        """Parse time range string to datetime objects"""
        
        if time_range.endswith('m'):
            minutes = int(time_range[:-1])
            start_time = end_time - timedelta(minutes=minutes)
        elif time_range.endswith('h'):
            hours = int(time_range[:-1])
            start_time = end_time - timedelta(hours=hours)
        elif time_range.endswith('d'):
            days = int(time_range[:-1])
            start_time = end_time - timedelta(days=days)
        else:
            # Default to 1 hour
            start_time = end_time - timedelta(hours=1)
        
        return start_time, end_time
