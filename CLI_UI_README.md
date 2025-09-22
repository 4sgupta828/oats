# UFFLOW Framework CLI UI Component

A comprehensive, interactive command-line interface for exploring and debugging UFFLOW framework executions. This CLI UI provides detailed views of goals, plans, node execution, inputs/outputs, and comprehensive summaries with beautiful formatting and color coding.

## 🚀 Features

### ✨ **Interactive Navigation**
- **Simple Commands**: Easy-to-use commands for exploring execution data
- **Readline Support**: Full command history and tab completion
- **Contextual Help**: Built-in help system with examples

### 📊 **Comprehensive Data Display**
- **Goal Information**: Complete goal definitions and constraints
- **Execution Plans**: Visual representation of execution graphs and node relationships
- **Node Details**: Detailed input/output data for each execution step
- **Execution Summaries**: High-level overviews with performance metrics

### 🎨 **Beautiful Formatting**
- **Color-coded Status**: Visual indicators for success/failure states
- **Boxed Content**: Clean, organized display of complex data structures
- **Responsive Layout**: Adapts to terminal width for optimal display
- **Unicode Art**: Professional-looking borders and separators

### 🔍 **Debugging Capabilities**
- **Error Details**: Complete error information for failed executions
- **Input/Output Inspection**: Full visibility into data flow between nodes
- **Performance Metrics**: Cost and duration tracking for each step
- **Raw Data Access**: Full JSON data when detailed inspection is needed

## 📁 Files

- **`cli_ui.py`** - Main CLI UI component
- **`test_cli_ui.py`** - Test script with comprehensive sample data
- **`demo_cli.py`** - Demo script showing key features
- **`CLI_UI_README.md`** - This documentation

## 🏃 Quick Start

### **Interactive Mode (Sample Data)**
```bash
cd /Users/sgupta/moko/ufflow
python cli_ui.py
```

### **Load from File**
```bash
cd /Users/sgupta/moko/ufflow
python cli_ui.py execution_results.json
```

### **Demo Mode**
```bash
cd /Users/sgupta/moko/ufflow
python demo_cli.py
```

## 📋 Available Commands

| Command | Short | Description |
|---------|-------|-------------|
| `help` | `h` | Show help message and available commands |
| `goal` | `g` | Display goal information and constraints |
| `plan` | `p` | Display execution plan and node relationships |
| `nodes` | `n` | List all execution nodes with status |
| `node <id>` | - | Show detailed information for specific node |
| `summary` | `s` | Display execution summary and statistics |
| `raw` | `r` | Show raw JSON data for detailed inspection |
| `quit` | `q` | Exit the application |

## 🎯 Usage Examples

### **Basic Exploration**
```bash
ufflow> goal          # View goal definition
ufflow> plan          # View execution plan
ufflow> nodes         # List all nodes
ufflow> summary       # View execution summary
```

### **Detailed Node Inspection**
```bash
ufflow> nodes         # First, see available nodes
ufflow> node read-log-file  # Inspect specific node
ufflow> node extract-errors # Inspect another node
```

### **Debugging Failed Executions**
```bash
ufflow> plan          # See which nodes failed
ufflow> node failed-node-id  # Inspect failed node details
ufflow> raw           # View complete raw data
```

## 📊 Data Format

The CLI UI expects UFFLOW execution data in the following JSON format:

```json
{
  "goal": {
    "id": "goal-id",
    "description": "Goal description",
    "constraints": { ... }
  },
  "plan": {
    "id": "plan-id",
    "goal_id": "goal-id",
    "status": "succeeded|failed|running",
    "graph": { ... },
    "nodes": {
      "node-id": {
        "id": "node-id",
        "uf_name": "tool_name:version",
        "status": "success|failure|running|pending",
        "input_resolver": { ... },
        "result": {
          "status": "success|failure",
          "output": { ... },
          "error": "error message if failed",
          "cost": 0.001,
          "duration_ms": 150
        }
      }
    }
  },
  "execution_summary": {
    "total_nodes": 5,
    "successful_nodes": 4,
    "failed_nodes": 1,
    "total_cost": 0.027,
    "total_duration_ms": 2750,
    "final_status": "succeeded"
  }
}
```

## 🎨 Display Features

### **Color Coding**
- 🟢 **Green**: Success states, positive metrics
- 🔴 **Red**: Failure states, errors, warnings
- 🟡 **Yellow**: Warnings, pending states
- 🔵 **Blue**: Information, data structures
- 🟣 **Magenta**: Raw data, technical details
- ⚪ **White**: Default text, neutral information

### **Boxed Content**
- **Clean Borders**: Unicode box-drawing characters
- **Titled Sections**: Clear section headers
- **Responsive Width**: Adapts to terminal size
- **Proper Wrapping**: Long content wrapped appropriately

### **Status Indicators**
- **SUCCESS**: ✅ Green, bold
- **FAILURE**: ❌ Red, bold
- **RUNNING**: ⏳ Yellow, bold
- **PENDING**: ⏸️ Cyan, bold

## 🔧 Technical Details

### **Dependencies**
- Python 3.7+
- `readline` (built-in)
- `json` (built-in)
- `textwrap` (built-in)
- `shutil` (built-in)

### **Terminal Compatibility**
- **ANSI Colors**: Full color support
- **Unicode**: Box-drawing characters
- **Width Detection**: Automatic terminal width detection
- **Cross-platform**: Works on Linux, macOS, Windows

### **Performance**
- **Fast Loading**: Efficient JSON parsing
- **Memory Efficient**: Streams large data appropriately
- **Responsive**: Quick command execution

## 🐛 Troubleshooting

### **Common Issues**

**No colors displayed:**
- Ensure terminal supports ANSI colors
- Check `TERM` environment variable

**Boxes not displaying properly:**
- Ensure terminal supports Unicode characters
- Check terminal font supports box-drawing characters

**Data not loading:**
- Verify JSON file format matches expected structure
- Check file permissions and path

**Commands not working:**
- Ensure you're in the correct directory
- Check Python path includes UFFLOW modules

### **Debug Mode**
```bash
python cli_ui.py --help  # Show all options
python cli_ui.py data.json --verbose  # Enable verbose output
```

## 🚀 Integration with UFFLOW

### **From UFFLOW Scripts**
```python
from cli_ui import UFFLOWCLI

# After UFFLOW execution
execution_data = {
    "goal": goal_data,
    "plan": plan_data,
    "execution_summary": summary_data
}

# Save data
with open("execution_results.json", "w") as f:
    json.dump(execution_data, f, indent=2)

# Launch CLI UI
cli = UFFLOWCLI("execution_results.json")
cli.run_interactive()
```

### **Real-time Integration**
```python
# In your UFFLOW execution script
def run_with_cli_ui():
    # ... UFFLOW execution ...
    
    # Save results
    save_execution_data(final_state)
    
    # Launch CLI UI
    subprocess.run(["python", "cli_ui.py", "execution_results.json"])
```

## 📈 Future Enhancements

- **Export Capabilities**: Save formatted reports to files
- **Filtering**: Filter nodes by status, tool type, etc.
- **Search**: Search through execution data
- **Timeline View**: Visual timeline of execution
- **Performance Analysis**: Detailed performance metrics
- **Comparison Mode**: Compare multiple executions
- **Web Interface**: Browser-based version

## 🤝 Contributing

The CLI UI is designed to be extensible. Key areas for contribution:

1. **New Display Formats**: Add new ways to visualize data
2. **Additional Commands**: Add new interactive commands
3. **Export Features**: Add data export capabilities
4. **Performance Improvements**: Optimize for large datasets
5. **UI Enhancements**: Improve visual design and layout

## 📄 License

Part of the UFFLOW Framework project. See main project license for details.

---

**Ready to explore your UFFLOW executions interactively!** 🎉

Run `python cli_ui.py` to get started, or `python demo_cli.py` to see a demonstration.
