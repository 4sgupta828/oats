"""Base provider abstractions for universal data source access

This module defines the abstract interfaces that all provider implementations
must follow. This ensures consistent behavior across different data sources
while allowing for provider-specific optimizations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel


class ProviderResult(BaseModel):
    """Standardized result format across all providers"""
    success: bool
    data: Any  # Provider-specific data
    metadata: Dict[str, Any] = {}  # Provider info, query stats, etc.
    error: Optional[str] = None
    
    class Config:
        # Allow arbitrary types for data field
        arbitrary_types_allowed = True


class LogProvider(ABC):
    """Abstract interface for log providers (CloudWatch, Datadog, Splunk, etc.)"""
    
    @abstractmethod
    def query(self, query: str, time_range: str, 
              filters: Optional[Dict[str, str]] = None, 
              limit: int = 100) -> ProviderResult:
        """Execute log query and return standardized results"""
        pass
    
    @abstractmethod
    def translate_query(self, natural_query: str, 
                       filters: Optional[Dict[str, str]] = None) -> str:
        """Translate natural language to provider-specific syntax"""
        pass


class MetricProvider(ABC):
    """Abstract interface for metric providers (CloudWatch, Prometheus, Datadog, etc.)"""
    
    @abstractmethod
    def query(self, metric_name: str, 
              dimensions: Optional[Dict[str, str]] = None,
              time_range: str = "1h",
              aggregation: str = "avg") -> ProviderResult:
        """Query time-series metrics and return standardized results"""
        pass
    
    @abstractmethod
    def list_metrics(self, prefix: Optional[str] = None) -> List[str]:
        """List available metrics (useful for discovery)"""
        pass
    
    @abstractmethod
    def get_metric_metadata(self, metric_name: str) -> Dict[str, Any]:
        """Get metadata about a specific metric (dimensions, unit, etc.)"""
        pass


class TraceProvider(ABC):
    """Abstract interface for trace providers (X-Ray, Jaeger, Zipkin, Datadog APM, etc.)"""
    
    @abstractmethod
    def query(self, trace_id: Optional[str] = None,
              service: Optional[str] = None,
              operation: Optional[str] = None,
              time_range: str = "1h",
              filters: Optional[Dict[str, str]] = None) -> ProviderResult:
        """Query distributed traces and return standardized results"""
        pass
    
    @abstractmethod
    def get_trace_details(self, trace_id: str) -> ProviderResult:
        """Get detailed trace information including spans"""
        pass


class CodeProvider(ABC):
    """Abstract interface for code search providers (GitHub, GitLab, Bitbucket, etc.)"""

    @abstractmethod
    def search(self, query: str,
               repo: Optional[str] = None,
               file_patterns: Optional[List[str]] = None,
               branch: str = "main") -> ProviderResult:
        """Search source code repositories"""
        pass

    @abstractmethod
    def get_file_content(self, repo: str, path: str, branch: str = "main") -> str:
        """Retrieve specific file content"""
        pass

    @abstractmethod
    def list_repos(self) -> List[str]:
        """List available repositories"""
        pass

    @abstractmethod
    def get_commits(self, repo: str,
                    branch: str = "main",
                    limit: int = 20,
                    since: Optional[str] = None,
                    author: Optional[str] = None,
                    path: Optional[str] = None,
                    include_diffs: bool = True) -> ProviderResult:
        """Get commit history with optional diffs

        Args:
            repo: Repository name/path
            branch: Branch to get commits from
            limit: Maximum number of commits to return
            since: ISO timestamp or relative time (e.g., '24h') to get commits since
            author: Filter by commit author
            path: Filter commits that touched specific path
            include_diffs: Whether to include file diffs in the response

        Returns:
            ProviderResult with list of commits containing:
            - sha: Commit hash
            - author: Commit author info
            - message: Commit message
            - timestamp: Commit timestamp
            - stats: File change statistics
            - files: List of changed files (with diffs if include_diffs=True)
        """
        pass
