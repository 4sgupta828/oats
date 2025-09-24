# Sourcegraph Manager for UF Flow

A comprehensive script to manage Sourcegraph services for your repository.

## 🎯 How It Determines Which Repository

The manager automatically detects your repository using:

1. **Current Directory**: Uses the directory where you run the command
2. **Git Detection**: Checks if it's a git repository (`.git` folder exists)
3. **Repository Name**: Uses the directory name as the repository identifier
4. **Git Information**: Reads remote URL, current branch, commit count

### Repository Detection Logic

```python
# The manager detects:
repo_path = Path.cwd()  # Current working directory
repo_name = repo_path.name  # Directory name (e.g., "oats")
is_git_repo = (repo_path / '.git').exists()  # Git repository check
remote_url = git remote get-url origin  # Remote repository URL
current_branch = git branch --show-current  # Current branch
```

## 🚀 Usage

### Quick Commands

```bash
# Start all services
./sourcegraph start

# Stop all services  
./sourcegraph stop

# Check status
./sourcegraph status

# Restart all services
./sourcegraph restart
```

### Detailed Commands

```bash
# Using the Python script directly
python3 tools/sourcegraph_manager.py start
python3 tools/sourcegraph_manager.py stop
python3 tools/sourcegraph_manager.py status
python3 tools/sourcegraph_manager.py restart

# With specific repository path
python3 tools/sourcegraph_manager.py start --repo /path/to/other/repo
python3 tools/sourcegraph_manager.py status --repo /path/to/other/repo

# JSON output for scripting
python3 tools/sourcegraph_manager.py status --json
```

## 🔧 Services Managed

### 1. Git Server (`src serve-git`)
- **Purpose**: Serves your repository over HTTP for Sourcegraph
- **Port**: 3434 (default)
- **URL**: http://localhost:3434
- **Command**: `src serve-git -addr :3434 /path/to/repo`

### 2. Search UI (`simple_search_ui.py`)
- **Purpose**: Web-based code search interface
- **Port**: 8081 (default)
- **URL**: http://localhost:8081
- **Command**: `python3 tools/simple_search_ui.py 8081`

## 📊 Status Information

The status command shows:

```
📊 Sourcegraph Status for oats
==================================================
📁 Repository: oats
📍 Path: /Users/sgupta/oats
🌿 Branch: main
🔗 Remote: https://github.com/4sgupta828/oats.git
📊 Commits: 27
🔧 Git Repo: ✅ Yes

🔧 Services:
  ✅ Git Server
     PID: 30947
     URL: http://localhost:3434
  ✅ Search Ui
     PID: 30951
     URL: http://localhost:8081
```

## 🗂️ Process Management

### PID Files
- **Location**: `~/.sourcegraph_manager/`
- **Files**: `{repo_name}_git_server.pid`, `{repo_name}_search_ui.pid`
- **Purpose**: Track running processes for clean shutdown

### Process Lifecycle
1. **Start**: Launches services and saves PIDs
2. **Monitor**: Checks if processes are still running
3. **Stop**: Gracefully terminates processes using saved PIDs
4. **Cleanup**: Removes PID files after shutdown

## 🔄 Repository Switching

### Same Repository
```bash
# If you're in the same repo, just run commands
./sourcegraph start
./sourcegraph status
```

### Different Repository
```bash
# Option 1: Change directory first
cd /path/to/other/repo
./sourcegraph start

# Option 2: Specify repository path
./sourcegraph start --repo /path/to/other/repo
./sourcegraph status --repo /path/to/other/repo
```

### Multiple Repositories
Each repository gets its own:
- **PID files**: `repo1_git_server.pid`, `repo2_git_server.pid`
- **Process tracking**: Independent process management
- **Port conflicts**: Automatically handled (each repo can use same ports)

## 🛠️ Troubleshooting

### Services Won't Start
```bash
# Check if ports are in use
lsof -i :3434
lsof -i :8081

# Check if processes are already running
ps aux | grep "src serve-git"
ps aux | grep "simple_search_ui"

# Force stop all services
./sourcegraph stop
```

### Repository Not Detected
```bash
# Check if you're in a git repository
git status

# Check repository info
./sourcegraph status

# Verify git remote
git remote -v
```

### Process Cleanup
```bash
# Manual cleanup of PID files
rm -rf ~/.sourcegraph_manager/

# Kill all related processes
pkill -f "src serve-git"
pkill -f "simple_search_ui"
```

## 📝 Example Workflows

### Daily Development
```bash
# Start services when you begin work
./sourcegraph start

# Check status anytime
./sourcegraph status

# Stop when done
./sourcegraph stop
```

### Repository Switching
```bash
# Work on project A
cd /path/to/project-a
./sourcegraph start

# Switch to project B
cd /path/to/project-b
./sourcegraph start  # Stops A, starts B

# Check what's running
./sourcegraph status
```

### CI/CD Integration
```bash
# JSON output for scripts
STATUS=$(./sourcegraph status --json)
echo $STATUS | jq '.services.git_server.running'

# Start services for testing
./sourcegraph start
# ... run tests ...
./sourcegraph stop
```

## 🎉 Benefits

✅ **Automatic Repository Detection**: No configuration needed
✅ **Process Management**: Clean start/stop with PID tracking  
✅ **Multi-Repository Support**: Work with different repos easily
✅ **Status Monitoring**: Always know what's running
✅ **Easy Commands**: Simple `./sourcegraph start/stop/status`
✅ **Integration Ready**: JSON output for automation
✅ **Error Handling**: Graceful failure and cleanup

Your Sourcegraph services are now fully managed and repository-aware! 🚀
