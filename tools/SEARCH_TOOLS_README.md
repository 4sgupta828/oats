# UF Flow Code Search Tools

This directory contains the local code search tools for the UF Flow system.

## Available Tools

### 🔍 Core Search Engine
- **`local_code_search.py`** - Main search engine with multiple search types
  - Text search, function definitions, class definitions, import statements, symbol usage
  - Context-aware results with surrounding code lines
  - Fast, offline search of the entire codebase

### 🌐 Web Interface
- **`simple_search_ui.py`** - Clean web-based search interface
  - URL: http://localhost:8081
  - Real-time search with instant results
  - Multiple search types and file pattern filtering
  - Beautiful, responsive UI

### 💻 Command Line Interface
- **`cli_search.py`** - Interactive terminal-based search
  - Interactive mode: `python3 tools/cli_search.py`
  - Direct mode: `python3 tools/cli_search.py "query" "search_type"`
  - Formatted output with context

### 🔧 Integration Tools
- **`smart_search.py`** - Used by workspace security for file finding
- **`file_system.py`** - File system operations
- **`shell_tools.py`** - Shell command execution
- **`system_tools.py`** - System-level operations

## Usage Examples

### Web Interface
1. Start: `python3 tools/simple_search_ui.py`
2. Open: http://localhost:8081
3. Search for: `PathManager`, `def get_tmp_file`, `class WorkingMemory`

### Command Line
```bash
# Interactive mode
python3 tools/cli_search.py

# Direct searches
python3 tools/cli_search.py PathManager class
python3 tools/cli_search.py "def " function
python3 tools/cli_search.py pandas import
```

### Programmatic Usage
```python
from tools.local_code_search import search_code

# Search for classes
result = search_code("PathManager", "class", "*.py", 10)

# Search for functions
result = search_code("get_tmp_file", "function", "*.py", 5)

# Text search
result = search_code("import pandas", "text", "*.py", 20)
```

## Search Types

- **text** - Search for any text in files
- **function** - Find function definitions
- **class** - Find class definitions
- **import** - Find import statements
- **symbol** - Find symbol usage

## Removed Files

The following files were removed during cleanup as they were not needed:
- `sourcegraph_integration.py` - Remote Sourcegraph integration (not needed for local search)
- `sourcegraph_tool.py` - Sourcegraph CLI wrapper (replaced by local search)
- `search_ui.py` - Broken web UI (replaced by simple_search_ui.py)
- `code_search_tool.py` - Duplicate wrapper (functionality in local_code_search.py)
- `search_integration.py` - Unused integration layer
- `robust_search.py` - Unused alternative implementation

## Current Status

✅ **Working**: Local code search with web UI and CLI
✅ **Fast**: Offline search with context-aware results
✅ **Clean**: Removed all unused Sourcegraph installation code
✅ **Integrated**: Works with existing UF Flow tools
