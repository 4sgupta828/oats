"""GitHub provider implementation for code search"""

from typing import Dict, Optional, List
from core.logging_config import get_logger
from ..base_provider import CodeProvider, ProviderResult

logger = get_logger('github_provider')


class GitHubCodeProvider(CodeProvider):
    """GitHub provider implementation for code search"""
    
    def __init__(self, config: Dict):
        self.token = config.get('token')
        self.org = config.get('org')
        self.repos = config.get('repos', [])
        
        if not self.token or self.token == 'ghp_test_token':
            logger.warning("GitHub token not provided or invalid - GitHub provider will be disabled")
            self.client = None
            return
        
        # Initialize GitHub client
        try:
            from github import Github
            
            self.client = Github(self.token)
            
            # Verify access
            try:
                user = self.client.get_user()
                logger.info(f"Initialized GitHub provider for user {user.login}")
            except Exception as e:
                logger.error(f"Failed to verify GitHub credentials: {e}")
                self.client = None
                
        except ImportError:
            raise ImportError("PyGithub package is required for GitHub provider")
    
    def search(self, query: str, 
               repo: Optional[str] = None,
               file_patterns: Optional[List[str]] = None,
               branch: str = "main") -> ProviderResult:
        """Search code using GitHub API"""
        
        if not self.client:
            return ProviderResult(
                success=False,
                data=None,
                metadata={'provider': 'github'},
                error="GitHub client not initialized - check token configuration"
            )
        
        try:
            # Build search query
            search_query = query
            
            # Add repository filter
            if repo:
                search_query += f" repo:{repo}"
            elif self.repos:
                repo_filter = " repo:" + " repo:".join(self.repos)
                search_query += repo_filter
            
            # Add organization filter
            if self.org and not repo:
                search_query += f" org:{self.org}"
            
            # Add file pattern filters
            if file_patterns:
                for pattern in file_patterns:
                    search_query += f" extension:{pattern.replace('*', '')}"
            
            logger.info(f"GitHub search query: {search_query}")
            
            # Execute search
            results = self.client.search_code(search_query)
            
            # Format results
            search_results = []
            for item in results[:50]:  # Limit to 50 results
                search_results.append({
                    'name': item.name,
                    'path': item.path,
                    'repository': item.repository.full_name,
                    'url': item.html_url,
                    'score': item.score
                })
            
            return ProviderResult(
                success=True,
                data=search_results,
                metadata={
                    "provider": "github",
                    "query": search_query,
                    "result_count": len(search_results),
                    "total_results": results.totalCount
                }
            )
            
        except Exception as e:
            logger.error(f"GitHub search failed: {e}")
            return ProviderResult(
                success=False,
                data=None,
                metadata={"provider": "github"},
                error=str(e)
            )
    
    def get_file_content(self, repo: str, path: str, branch: str = "main") -> str:
        """Retrieve specific file content"""
        if not self.client:
            raise RuntimeError("GitHub client not initialized - check token configuration")
        
        try:
            repository = self.client.get_repo(repo)
            file_content = repository.get_contents(path, ref=branch)
            
            if isinstance(file_content, list):
                # Directory listing
                return f"Directory listing for {path}:\n" + "\n".join([item.name for item in file_content])
            else:
                # File content
                import base64
                content = base64.b64decode(file_content.content).decode('utf-8')
                return content
                
        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            raise
    
    def list_repos(self) -> List[str]:
        """List available repositories"""
        if not self.client:
            return []
        
        try:
            if self.org:
                org = self.client.get_organization(self.org)
                repos = [repo.full_name for repo in org.get_repos()]
            else:
                user = self.client.get_user()
                repos = [repo.full_name for repo in user.get_repos()]
            
            # Filter by configured repos if specified
            if self.repos:
                repos = [repo for repo in repos if any(config_repo in repo for config_repo in self.repos)]
            
            return repos
            
        except Exception as e:
            logger.error(f"Failed to list repositories: {e}")
            return []
