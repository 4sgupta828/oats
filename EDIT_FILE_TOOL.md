# edit_file Tool Documentation

## Overview

The `edit_file` tool atomically replaces a specific range of lines in a text file with new content. It's designed for targeted code modifications, refactoring, and bug fixes with safety guarantees.

## Location

- **Implementation**: `/tools/file_system.py`
- **Function**: `edit_file()`
- **Input Schema**: `EditFileInput`

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `filename` | string | Yes | The path to the file that will be modified |
| `start_line` | integer | Yes | The 1-based line number where the replacement should begin |
| `end_line` | integer | Yes | The 1-based line number of the last line to be replaced |
| `new_content` | string | Yes | The new block of text to be inserted. Use empty string to delete lines |
| `preview` | boolean | No | If True, shows what would change without modifying the file (default: False) |

## Special Cases

1. **Replace a block of lines**: Set `start_line` and `end_line` to the boundaries of the block and provide `new_content`

2. **Delete a block of lines**: Set `start_line` and `end_line` to the boundaries and provide `new_content = ""`

3. **Insert new lines**: Set `end_line = start_line - 1`. The `new_content` will be inserted before the original `start_line`

## Core Features

### 1. Atomic Writes
- Uses temporary file + `os.replace()` for atomic operations
- Prevents data loss if operation is interrupted
- No partial writes or corruption

### 2. Preview Mode
- Set `preview=True` to see changes without applying them
- Returns detailed information about what would change
- Perfect for verification before committing

### 3. Comprehensive Validation
- Validates file existence
- Checks line numbers are within bounds
- Validates workspace security
- Clear error messages

### 4. Detailed Feedback
Returns dict with:
```python
{
    "filepath": str,           # Absolute path to file
    "success": bool,           # Operation status
    "changes": {
        "start_line": int,
        "end_line": int,
        "lines_removed": int,
        "lines_added": int,
        "net_change": int,     # positive or negative
        "operation": str       # "insert", "replace", or "append"
    },
    "total_lines_before": int,
    "total_lines_after": int,
    "file_size": int
}
```

## Safety Pattern: Read-Modify-Verify

⚠️ **CRITICAL**: Always use this pattern to prevent errors from stale line numbers

### Pattern Steps:

1. **READ**: Use `read_file` to get fresh content and current line numbers
2. **PLAN**: Calculate exact `start_line` and `end_line` based on fresh content
3. **MODIFY**: Execute `edit_file` with calculated parameters
4. **VERIFY**: Use `read_file` again on the modified section to confirm changes

### Example:

```python
from tools.file_system import edit_file, read_file
from tools.file_system import EditFileInput, ReadFileInput

# STEP 1: READ - Get fresh content
content = read_file(ReadFileInput(filename="myfile.py"))
print(content)  # Examine and identify lines to modify

# STEP 2: PLAN - Based on what you just read
start_line = 10
end_line = 15
new_content = "def new_function():\n    pass\n"

# STEP 3: MODIFY - Execute the edit
result = edit_file(EditFileInput(
    filename="myfile.py",
    start_line=start_line,
    end_line=end_line,
    new_content=new_content
))

# STEP 4: VERIFY - Confirm changes
updated = read_file(ReadFileInput(
    filename="myfile.py",
    start_line=start_line,
    end_line=start_line + result['changes']['lines_added']
))
print(updated)
```

## Usage Examples

### Example 1: Replace Lines
```python
edit_file(EditFileInput(
    filename="code.py",
    start_line=5,
    end_line=7,
    new_content="# New implementation\nreturn True\n"
))
```

### Example 2: Insert Lines
```python
# Insert before line 10
edit_file(EditFileInput(
    filename="code.py",
    start_line=10,
    end_line=9,  # end_line = start_line - 1
    new_content="import logging\nimport sys\n"
))
```

### Example 3: Delete Lines
```python
edit_file(EditFileInput(
    filename="code.py",
    start_line=20,
    end_line=25,
    new_content=""  # Empty string = delete
))
```

### Example 4: Preview Changes
```python
preview = edit_file(EditFileInput(
    filename="code.py",
    start_line=5,
    end_line=10,
    new_content="# Refactored code\n",
    preview=True  # Don't apply changes yet
))

print(f"Would remove {preview['changes']['lines_removed']} lines")
print(f"Would add {preview['changes']['lines_added']} lines")
print(f"Old content: {preview['old_content']}")
```

## Error Handling

The tool raises specific errors:

- **`FileNotFoundError`**: If the specified file doesn't exist
- **`ValueError`**: If line numbers are invalid (e.g., `start_line < 1`, `end_line > total_lines`)
- **`IOError`**: For file permission issues, disk space problems, etc.

## Integration with UFDescriptor

The tool's description includes agent guidance:

```python
description="Atomically replaces a specific range of lines in a text file with new content. "
            "IMPORTANT: Always use a Read-Modify-Verify pattern: (1) Read the file to get current line numbers, "
            "(2) Calculate start_line and end_line based on fresh content, (3) Execute edit_file, "
            "(4) Read the modified section to verify the change. This prevents errors from stale line numbers. "
            "Special cases: To insert lines, set end_line = start_line - 1. To delete lines, provide empty new_content."
```

This guidance is automatically visible to any agent that searches for available tools, ensuring safe usage.

## Testing

Comprehensive test suite in `test_edit_file.py` covers:
- ✅ Replace lines
- ✅ Insert lines
- ✅ Delete lines
- ✅ Replace single line
- ✅ Preview mode
- ✅ Insert at beginning
- ✅ Error handling (invalid line numbers)
- ✅ Error handling (file not found)

Run tests:
```bash
python test_edit_file.py
```

## Workspace Security

The tool integrates with your workspace security system:
- All file paths are validated against workspace boundaries
- Only files within the workspace can be modified
- Prevents accidental modification of system files
- Uses `validate_workspace_path()` for all path operations

## Benefits Over write_file

| Feature | edit_file | write_file |
|---------|-----------|------------|
| Modify specific lines | ✅ | ❌ (must rewrite entire file) |
| Atomic operations | ✅ | ✅ |
| Preview mode | ✅ | ❌ |
| Line-level precision | ✅ | ❌ |
| Detailed change tracking | ✅ | ❌ |
| Insert/delete operations | ✅ | ❌ |

## Summary

The `edit_file` tool provides:
- ✅ **Safety**: Atomic writes, validation, preview mode
- ✅ **Precision**: Line-level targeting for surgical edits
- ✅ **Guidance**: Built-in Read-Modify-Verify pattern documentation
- ✅ **Flexibility**: Replace, insert, delete operations
- ✅ **Transparency**: Detailed change tracking and reporting
- ✅ **Integration**: Works with workspace security and path management

Perfect for targeted code modifications without rewriting entire files!
