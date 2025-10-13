"""AWS X-Ray provider implementation"""

import boto3
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from core.logging_config import get_logger
from ..base_provider import TraceProvider, ProviderResult

logger = get_logger('xray_provider')


class XRayTraceProvider(TraceProvider):
    """AWS X-Ray provider implementation"""
    
    def __init__(self, config: Dict):
        self.region = config.get('region', 'us-east-1')
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
                'xray',
                region_name=self.region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            # Use default credentials
            self.client = boto3.client('xray', region_name=self.region)
        
        logger.info(f"Initialized X-Ray provider for region {self.region}")
    
    def query(self, trace_id: Optional[str] = None,
              service: Optional[str] = None,
              operation: Optional[str] = None,
              time_range: str = "1h",
              filters: Optional[Dict[str, str]] = None) -> ProviderResult:
        """Query X-Ray traces"""
        
        try:
            if trace_id:
                # Get specific trace
                return self._get_trace_by_id(trace_id)
            else:
                # Search for traces
                return self._search_traces(service, operation, time_range, filters)
                
        except Exception as e:
            logger.error(f"X-Ray query failed: {e}")
            return ProviderResult(
                success=False,
                data=None,
                metadata={"provider": "xray"},
                error=str(e)
            )
    
    def get_trace_details(self, trace_id: str) -> ProviderResult:
        """Get detailed trace information including spans"""
        return self._get_trace_by_id(trace_id)
    
    def _get_trace_by_id(self, trace_id: str) -> ProviderResult:
        """Get trace by ID"""
        try:
            response = self.client.batch_get_traces(TraceIds=[trace_id])
            
            if not response['Traces']:
                return ProviderResult(
                    success=False,
                    data=None,
                    metadata={"provider": "xray"},
                    error=f"Trace {trace_id} not found"
                )
            
            trace = response['Traces'][0]
            
            # Format trace data
            trace_data = {
                'trace_id': trace['Id'],
                'duration': trace.get('Duration', 0),
                'start_time': trace.get('StartTime', 0),
                'segments': []
            }
            
            for segment in trace.get('Segments', []):
                segment_data = {
                    'id': segment['Id'],
                    'name': segment.get('Name', ''),
                    'start_time': segment.get('StartTime', 0),
                    'end_time': segment.get('EndTime', 0),
                    'duration': segment.get('Duration', 0)
                }
                trace_data['segments'].append(segment_data)
            
            return ProviderResult(
                success=True,
                data=trace_data,
                metadata={
                    "provider": "xray",
                    "trace_id": trace_id,
                    "segment_count": len(trace_data['segments'])
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get trace {trace_id}: {e}")
            return ProviderResult(
                success=False,
                data=None,
                metadata={"provider": "xray"},
                error=str(e)
            )
    
    def _search_traces(self, service: Optional[str], operation: Optional[str], 
                      time_range: str, filters: Optional[Dict[str, str]]) -> ProviderResult:
        """Search for traces"""
        try:
            # Parse time range
            end_time = datetime.utcnow()
            start_time, _ = self._parse_time_range(time_range, end_time)
            
            # Build filter expression
            filter_expression = ""
            if service:
                filter_expression += f"service(\"{service}\")"
            if operation:
                if filter_expression:
                    filter_expression += " && "
                filter_expression += f"name(\"{operation}\")"
            
            # Add additional filters
            if filters:
                for key, value in filters.items():
                    if filter_expression:
                        filter_expression += " && "
                    filter_expression += f"{key}(\"{value}\")"
            
            logger.info(f"X-Ray filter expression: {filter_expression}")
            
            # Search for trace summaries
            response = self.client.get_trace_summaries(
                StartTime=start_time,
                EndTime=end_time,
                FilterExpression=filter_expression if filter_expression else None,
                TimeRangeType='TraceId'
            )
            
            # Format results
            traces = []
            for summary in response.get('TraceSummaries', []):
                traces.append({
                    'trace_id': summary['Id'],
                    'duration': summary.get('Duration', 0),
                    'has_error': summary.get('HasError', False),
                    'has_fault': summary.get('HasFault', False),
                    'has_throttle': summary.get('HasThrottle', False),
                    'response_time': summary.get('ResponseTime', 0)
                })
            
            return ProviderResult(
                success=True,
                data=traces,
                metadata={
                    "provider": "xray",
                    "result_count": len(traces),
                    "filter_expression": filter_expression,
                    "time_range": time_range
                }
            )
            
        except Exception as e:
            logger.error(f"X-Ray search failed: {e}")
            return ProviderResult(
                success=False,
                data=None,
                metadata={"provider": "xray"},
                error=str(e)
            )
    
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
