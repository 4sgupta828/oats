# Commit History Investigation Tool

## Overview

The `query_commits` tool allows the infra copilot to examine recent commit history from GitHub repositories, including full diffs. This is useful for investigating recent code changes that may have caused issues.

## Features

- **Retrieve commit history** with flexible filtering options
- **View full diffs** for each commit to understand what changed
- **Filter by time range** (e.g., "24h", "7d")
- **Filter by author** to see specific developer's commits
- **Filter by path** to see commits that touched specific files/directories
- **Branch support** to examine any branch

## Tool Definition

```python
@uf(name="query_commits", version="1.0.0",
   description="Get recent commit history from code repositories with diffs. Use this to investigate recent code changes that may have caused issues, understand what changed in a specific file, or review deployment history.")
def query_commits(inputs: QueryCommitsInput) -> dict:
    """Query commit history using the configured code provider"""
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | str | **required** | Repository name/path (e.g., 'owner/repo') |
| `branch` | str | "main" | Branch to get commits from |
| `limit` | int | 20 | Maximum number of commits to return (max 50) |
| `since` | str | None | Get commits since this time ('24h', '7d', or ISO timestamp) |
| `author` | str | None | Filter by commit author |
| `path` | str | None | Filter commits that touched specific file/directory path |
| `include_diffs` | bool | True | Include file diffs in the response |

## Response Format

```json
{
  "status": "success",
  "data": [
    {
      "sha": "abc123...",
      "author": {
        "name": "John Doe",
        "email": "john@example.com",
        "date": "2025-10-13T12:00:00Z"
      },
      "message": "Fix authentication bug",
      "timestamp": "2025-10-13T12:00:00Z",
      "url": "https://github.com/owner/repo/commit/abc123",
      "stats": {
        "total": 45,
        "additions": 30,
        "deletions": 15
      },
      "files": [
        {
          "filename": "auth/login.py",
          "status": "modified",
          "additions": 15,
          "deletions": 10,
          "changes": 25,
          "diff": "@@ -10,7 +10,10 @@\n def authenticate(user, password):\n-    if check_password(password):\n+    if check_password_hash(password):\n..."
        }
      ]
    }
  ],
  "metadata": {
    "provider": "github",
    "repo": "owner/repo",
    "branch": "main",
    "commit_count": 1,
    "include_diffs": true,
    "duration_seconds": 1.23
  }
}
```

## Use Cases

### 1. Investigate Recent Deployments

When investigating a production issue, check what was recently deployed:

```python
query_commits(QueryCommitsInput(
    repo="company/backend-api",
    branch="production",
    limit=10,
    since="24h",
    include_diffs=True
))
```

### 2. Find Changes to Specific Files

When a specific file or module is causing issues, see its recent history:

```python
query_commits(QueryCommitsInput(
    repo="company/backend-api",
    path="services/payment/processor.py",
    since="7d",
    limit=20
))
```

### 3. Review Developer's Changes

To understand what a specific developer changed:

```python
query_commits(QueryCommitsInput(
    repo="company/backend-api",
    author="jane@company.com",
    since="7d",
    limit=30
))
```

### 4. Quick Recent Changes Overview

Get a summary without diffs for faster response:

```python
query_commits(QueryCommitsInput(
    repo="company/backend-api",
    limit=50,
    since="24h",
    include_diffs=False
))
```

## Integration with Investigation Workflow

The infra copilot can now correlate:

1. **Logs** showing errors (`query_logs`)
2. **Metrics** showing performance degradation (`query_metrics`)
3. **Traces** showing distributed system issues (`query_traces`)
4. **Code changes** that may have caused the issues (`query_commits`)
5. **Code search** to understand implementation details (`search_code`)

## Example Investigation Workflow

```python
# 1. Detect error spike in logs
logs = query_logs(QueryLogsInput(
    query="error payment processing",
    time_range="1h",
    limit=100
))

# 2. Check metrics for the payment service
metrics = query_metrics(QueryMetricsInput(
    metric_name="payment_errors",
    time_range="1h",
    dimensions={"service": "payment"}
))

# 3. Review recent commits to payment service
commits = query_commits(QueryCommitsInput(
    repo="company/backend-api",
    path="services/payment",
    since="24h",
    include_diffs=True
))

# 4. Search for relevant code
code = search_code(SearchCodeInput(
    query="payment_processor.process",
    repo="company/backend-api"
))
```

## Implementation Details

### Base Provider Interface

The `get_commits` method was added to the `CodeProvider` abstract base class in `/Users/sgupta/oats/services/agent/providers/base_provider.py`:

```python
@abstractmethod
def get_commits(self, repo: str,
                branch: str = "main",
                limit: int = 20,
                since: Optional[str] = None,
                author: Optional[str] = None,
                path: Optional[str] = None,
                include_diffs: bool = True) -> ProviderResult:
    """Get commit history with optional diffs"""
    pass
```

### GitHub Implementation

The GitHub provider implementation uses PyGithub to fetch commit history:

- Location: `/Users/sgupta/oats/services/agent/providers/code/github_provider.py:167`
- Supports relative time formats ("24h", "7d") and ISO timestamps
- Includes comprehensive error handling
- Returns structured commit data with diffs

## Testing

A test script is available at `/Users/sgupta/oats/services/agent/test_commit_history.py`:

```bash
cd /Users/sgupta/oats/services/agent
source /Users/sgupta/oats/venv/bin/activate
python3 test_commit_history.py
```

## Configuration

The GitHub provider requires a valid GitHub token in the configuration:

```yaml
code:
  provider: "github"
  config:
    token: "ghp_your_token_here"
    org: "your-org"  # optional
    repos: ["repo1", "repo2"]  # optional filter
```

## Future Enhancements

Potential improvements:
- Add support for comparing two commits
- Add support for pull request information
- Add blame information (who last modified each line)
- Support for other providers (GitLab, Bitbucket)
- Add commit search by message content
