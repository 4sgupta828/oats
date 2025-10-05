# uf_flow/tools/file_system.py
# Enhanced with targeted reading functionality for efficient code analysis

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field
from core.sdk import uf, UfInput

class CreateFileInput(UfInput):
    filename: str = Field(..., description="The name of the file to create. Use relative paths for proper placement.")
    content: str = Field(..., description="The content to write into the file.")
    is_temporary: bool = Field(False, description="Whether this is a temporary file (will be placed in tmp/ directory).")

class ReadFileInput(UfInput):
    filename: str = Field(..., description="The name of the file to read.")
    start_line: int = Field(None, description="Optional: Starting line number (1-based) for targeted reading. If provided, reads a range of lines instead of the entire file.")
    end_line: int = Field(None, description="Optional: Ending line number (1-based) for targeted reading. If not provided but start_line is set, reads 20 lines from start_line.")
    context_lines: int = Field(10, description="Optional: Number of context lines to include before and after when reading around a specific function/code block.")

class WriteFileInput(UfInput):
    filename: str = Field(..., description="The name of the file to write to. Use relative paths for proper placement.")
    content: str = Field(..., description="The content to write into the file.")
    is_temporary: bool = Field(False, description="Whether this is a temporary file (will be placed in tmp/ directory).")

class ListFilesInput(UfInput):
    path: str = Field(".", description="The directory path to list. Defaults to current directory.")
    recursive: bool = Field(False, description="Whether to list files recursively in subdirectories.")

class DeleteFileInput(UfInput):
    filename: str = Field(..., description="The name of the file to delete.")

class FileExistsInput(UfInput):
    filename: str = Field(..., description="The name of the file or directory to check.")

class UserPromptInput(UfInput):
    question: str = Field(..., description="The question or request to ask the user.")

class UserConfirmInput(UfInput):
    message: str = Field(..., description="The action or permission to confirm with the user.")
    default_yes: bool = Field(True, description="Whether to default to 'Yes' when user just presses Enter.")

class EditFileInput(UfInput):
    filename: str = Field(..., description="The path to the file that will be modified.")
    start_line: int = Field(..., description="The 1-based line number where the replacement should begin. The line at this number will be the first one replaced.")
    end_line: int = Field(..., description="The 1-based line number of the last line to be replaced. This line and all lines between start_line and end_line will be removed. To insert new lines, set end_line = start_line - 1.")
    new_content: str = Field(..., description="The new block of text to be inserted in place of the old lines. This can be a multi-line string. To simply delete lines, provide an empty string.")
    preview: bool = Field(False, description="If True, show what would change without modifying the file (dry-run mode for verification).")

@uf(name="create_file", version="1.0.0", description="Creates a new file with specified content.")
def create_file(inputs: CreateFileInput) -> dict:
    """Creates a file and returns its path and size."""
    # Use workspace security with temporary file detection
    from core.workspace_security import validate_workspace_path, secure_write_text

    # Validate path with temporary file information
    validated_path = validate_workspace_path(inputs.filename, "file creation", inputs.is_temporary)

    # Write the file securely
    secure_write_text(validated_path, inputs.content)

    size = os.path.getsize(validated_path)
    file_type = "temporary" if inputs.is_temporary else "permanent"

    print(f"{file_type.capitalize()} file '{inputs.filename}' created successfully, size: {size} bytes.")
    print(f"  → Location: {validated_path}")
    return {"filepath": validated_path, "size": size, "is_temporary": inputs.is_temporary}

@uf(name="read_file", version="1.0.0", description="Reads the content of a specified file. Supports targeted reading with line ranges for efficient analysis of specific functions or code sections.")
def read_file(inputs: ReadFileInput) -> str:
    """Reads a file and returns its content as a string. Can read entire file or targeted line ranges."""
    # Use workspace security with file search
    from core.workspace_security import validate_workspace_path

    # Validate path with file search (this will use recursive search)
    validated_path = validate_workspace_path(inputs.filename, "file reading")

    # Read the file
    with open(validated_path, 'r') as f:
        lines = f.readlines()

    # Handle targeted reading with line ranges
    if inputs.start_line is not None:
        # Convert to 0-based indexing
        start_idx = inputs.start_line - 1

        # Determine end line
        if inputs.end_line is not None:
            end_idx = inputs.end_line - 1
        else:
            # Default to 20 lines from start if end_line not specified
            end_idx = start_idx + 19

        # Add context lines if specified
        if inputs.context_lines > 0:
            start_idx = max(0, start_idx - inputs.context_lines)
            end_idx = min(len(lines) - 1, end_idx + inputs.context_lines)

        # Ensure valid bounds
        start_idx = max(0, start_idx)
        end_idx = min(len(lines) - 1, end_idx)

        # Extract the targeted lines
        targeted_lines = lines[start_idx:end_idx + 1]
        content = ''.join(targeted_lines)

        # Create helpful output message
        actual_start = start_idx + 1
        actual_end = end_idx + 1
        total_lines_read = len(targeted_lines)

        print(f"Read {total_lines_read} lines ({actual_start}-{actual_end}) from '{inputs.filename}' ({len(content)} characters).")
        if inputs.context_lines > 0:
            print(f"  → Included {inputs.context_lines} context lines before/after the target range")
        print(f"  → Location: {validated_path}")

        # Optionally prepend line numbers for better context in analysis
        if total_lines_read <= 50:  # Only for reasonably small snippets
            numbered_lines = []
            for i, line in enumerate(targeted_lines):
                line_num = start_idx + i + 1
                numbered_lines.append(f"{line_num:4d}: {line.rstrip()}")
            content = '\n'.join(numbered_lines)

        return content
    else:
        # Read entire file (original behavior)
        content = ''.join(lines)
        print(f"Read entire file '{inputs.filename}' ({len(content)} characters, {len(lines)} lines).")
        print(f"  → Location: {validated_path}")
        return content

@uf(name="write_file", version="1.0.0", description="Writes content to an existing file, overwriting its contents.")
def write_file(inputs: WriteFileInput) -> dict:
    """Writes content to an existing file and returns file info."""
    # Use workspace security with temporary file detection
    from core.workspace_security import validate_workspace_path, secure_write_text

    # Validate path with temporary file information
    validated_path = validate_workspace_path(inputs.filename, "file writing", inputs.is_temporary)

    # Write the file securely
    secure_write_text(validated_path, inputs.content)

    size = os.path.getsize(validated_path)
    file_type = "temporary" if inputs.is_temporary else "permanent"

    print(f"{file_type.capitalize()} file '{inputs.filename}' updated successfully, size: {size} bytes.")
    print(f"  → Location: {validated_path}")
    return {"filepath": validated_path, "size": size, "is_temporary": inputs.is_temporary}

def _should_exclude_path(name):
    """Check if a path should be excluded based on gitignore-style patterns."""
    # Directories that start with . (hidden directories)
    if name.startswith('.'):
        return True

    # Common exclusions based on gitignore patterns
    exclude_patterns = {
        # Python
        '__pycache__', 'build', 'dist', 'downloads', 'eggs', '.eggs',
        'lib', 'lib64', 'parts', 'sdist', 'var', 'wheels',
        'develop-eggs', '.installed.cfg',

        # Virtual environments
        'venv', 'env', 'ENV', '.venv', '.env',
        'env.bak', 'venv.bak',

        # IDE and editor files
        '.vscode', '.idea',

        # OS files
        '.DS_Store', 'Thumbs.db',

        # Jupyter
        '.ipynb_checkpoints',

        # Package managers
        '__pypackages__', 'node_modules',

        # Documentation builds
        'site',

        # Type checkers
        '.mypy_cache', '.pyre',

        # Logs
        'logs',
    }

    # File extensions to exclude
    exclude_extensions = {
        '.pyc', '.pyo', '.pyd', '.so', '.egg',
        '.swp', '.swo', '.tmp', '.log'
    }

    # Check directory/file name patterns
    if name in exclude_patterns:
        return True

    # Check file extensions
    _, ext = os.path.splitext(name)
    if ext in exclude_extensions:
        return True

    # Check for specific patterns
    if name.endswith(('.egg-info', '.dist-info')):
        return True

    # Check for compiled Python files
    if name.endswith(('.py[cod]', '$py.class')):
        return True

    # Check for versioned virtual environments (venv312, venv3.11, env39, etc.)
    import re
    venv_pattern = r'^(venv|env)\d+(\.\d+)*$'
    if re.match(venv_pattern, name, re.IGNORECASE):
        return True

    return False

@uf(name="list_files", version="1.0.0", description="Lists files and directories in a specified path, with optional recursive listing, excluding common non-source files.")
def list_files(inputs: ListFilesInput) -> dict:
    """Lists files and directories with workspace security validation and intelligent filtering."""
    from core.workspace_security import validate_workspace_path

    validated_path = validate_workspace_path(inputs.path, "directory listing")

    files = []
    directories = []

    if inputs.recursive:
        for root, dirs, filenames in os.walk(validated_path):
            # Filter directories in-place to prevent walking into excluded dirs
            dirs[:] = [d for d in dirs if not _should_exclude_path(d)]

            # Add non-excluded directories
            for dir_name in dirs:
                rel_path = os.path.relpath(os.path.join(root, dir_name), validated_path)
                directories.append(rel_path if rel_path != "." else dir_name)

            # Add non-excluded files
            for filename in filenames:
                if not _should_exclude_path(filename):
                    rel_path = os.path.relpath(os.path.join(root, filename), validated_path)
                    files.append(rel_path if rel_path != "." else filename)
    else:
        items = os.listdir(validated_path)
        for item in items:
            if _should_exclude_path(item):
                continue

            item_path = os.path.join(validated_path, item)
            if os.path.isdir(item_path):
                directories.append(item)
            else:
                files.append(item)

    result = {
        "path": validated_path,
        "files": sorted(files),
        "directories": sorted(directories),
        "recursive": inputs.recursive,
        "total_files": len(files),
        "total_directories": len(directories)
    }

    print(f"Listed {len(files)} files and {len(directories)} directories in '{inputs.path}'" +
          (" (recursive)" if inputs.recursive else ""))
    return result

@uf(name="delete_file", version="1.0.0", description="Deletes a specified file with workspace security validation.")
def delete_file(inputs: DeleteFileInput) -> dict:
    """Deletes a file and returns confirmation."""
    from core.workspace_security import validate_workspace_path

    validated_path = validate_workspace_path(inputs.filename, "file deletion")

    if not os.path.exists(validated_path):
        raise FileNotFoundError(f"File '{inputs.filename}' does not exist.")

    if os.path.isdir(validated_path):
        raise IsADirectoryError(f"'{inputs.filename}' is a directory, not a file.")

    # Get file size before deletion for reporting
    file_size = os.path.getsize(validated_path)

    os.remove(validated_path)

    print(f"File '{inputs.filename}' deleted successfully (was {file_size} bytes).")
    return {"deleted_file": validated_path, "size_freed": file_size}

@uf(name="file_exists", version="1.0.0", description="Checks if a file or directory exists with workspace security validation.")
def file_exists(inputs: FileExistsInput) -> dict:
    """Checks if a file or directory exists and returns detailed info."""
    from core.workspace_security import validate_workspace_path

    try:
        validated_path = validate_workspace_path(inputs.filename, "existence check")
        exists = os.path.exists(validated_path)

        result = {"path": validated_path, "exists": exists}

        if exists:
            result["is_file"] = os.path.isfile(validated_path)
            result["is_directory"] = os.path.isdir(validated_path)
            if result["is_file"]:
                result["size"] = os.path.getsize(validated_path)

        print(f"'{inputs.filename}' {'exists' if exists else 'does not exist'}")
        return result

    except Exception as e:
        # If path validation fails, it doesn't exist within workspace
        result = {"path": inputs.filename, "exists": False, "error": str(e)}
        print(f"'{inputs.filename}' does not exist or is outside workspace")
        return result

@uf(name="user_prompt", version="1.0.0", description="Prompts the user for input, advice, or feedback when the agent needs clarification or guidance.")
def user_prompt(inputs: UserPromptInput) -> dict:
    """Prompts the user with a question and returns their response with flow control info."""
    print(f"\n🤖 Agent Question: {inputs.question}")
    print("👤 Please provide your response (or type 'stop', 'cancel', 'skip', 'abort'):")

    try:
        user_response = input("> ").strip()

        # Handle special control commands
        control_commands = {
            'stop', 'cancel', 'abort', 'quit', 'exit', 'halt'
        }

        skip_commands = {
            'skip', 'next', 'continue', 'pass'
        }

        response_lower = user_response.lower()

        if response_lower in control_commands:
            print(f"User requested to {response_lower}. Stopping current operation.")
            return {
                "response": user_response,
                "action": "stop",
                "message": f"User requested to {response_lower} the operation"
            }
        elif response_lower in skip_commands:
            print(f"User requested to {response_lower}. Skipping current step.")
            return {
                "response": user_response,
                "action": "skip",
                "message": f"User requested to {response_lower} this step"
            }
        else:
            print(f"User responded: {user_response}")
            return {
                "response": user_response,
                "action": "continue",
                "message": "Normal user response"
            }

    except KeyboardInterrupt:
        print("\n🛑 User interrupted with Ctrl+C")
        return {
            "response": "",
            "action": "abort",
            "message": "User interrupted with Ctrl+C"
        }
    except EOFError:
        print("\n📝 No response provided (EOF)")
        return {
            "response": "",
            "action": "continue",
            "message": "No response provided"
        }

@uf(
    name="edit_file",
    version="1.0.0",
    description="Atomically replaces a specific range of lines in a text file with new content. "
                "IMPORTANT: Always use a Read-Modify-Verify pattern: (1) Read the file to get current line numbers, "
                "(2) Calculate start_line and end_line based on fresh content, (3) Execute edit_file, "
                "(4) Read the modified section to verify the change. This prevents errors from stale line numbers. "
                "Special cases: To insert lines, set end_line = start_line - 1. To delete lines, provide empty new_content."
)
def edit_file(inputs: EditFileInput) -> dict:
    """
    Atomically replaces a specific range of lines in a file.

    Returns dict with file info and change summary.

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If line numbers are invalid or out of bounds
        IOError: For file permission or disk space issues
    """
    import tempfile
    from core.workspace_security import validate_workspace_path

    # Validate the file path
    validated_path = validate_workspace_path(inputs.filename, "file editing")

    # Check if file exists
    if not os.path.exists(validated_path):
        raise FileNotFoundError(f"File '{inputs.filename}' does not exist at {validated_path}")

    # Validate line numbers
    if inputs.start_line < 1:
        raise ValueError(f"start_line must be >= 1, got {inputs.start_line}")

    if inputs.end_line < inputs.start_line - 1:
        raise ValueError(f"end_line ({inputs.end_line}) must be >= start_line - 1 ({inputs.start_line - 1})")

    # Read all lines from the file
    with open(validated_path, 'r') as f:
        lines = f.readlines()

    total_lines = len(lines)

    # Validate bounds
    if inputs.start_line > total_lines + 1:
        raise ValueError(
            f"start_line ({inputs.start_line}) is beyond file end (file has {total_lines} lines). "
            f"Maximum valid start_line is {total_lines + 1} (for appending)."
        )

    if inputs.end_line > total_lines:
        raise ValueError(
            f"end_line ({inputs.end_line}) is beyond file end (file has {total_lines} lines)"
        )

    # Convert to 0-based indices
    start_idx = inputs.start_line - 1
    end_idx = inputs.end_line - 1

    # Handle insertion case (end_line = start_line - 1)
    is_insertion = inputs.end_line == inputs.start_line - 1

    # Prepare new content lines (preserve line endings)
    if inputs.new_content:
        # Split by newline but preserve the structure
        new_lines = inputs.new_content.split('\n')
        # Add newline to each line except potentially the last one
        new_lines = [line + '\n' for line in new_lines[:-1]] + ([new_lines[-1] + '\n'] if new_lines[-1] else [])
        # If new_content ends with newline, it's already handled
        if inputs.new_content.endswith('\n') and new_lines and new_lines[-1] == '\n':
            new_lines = new_lines[:-1]  # Remove the extra empty line
        elif inputs.new_content and not inputs.new_content.endswith('\n') and new_lines:
            # Ensure last line has newline for consistency
            new_lines[-1] = new_lines[-1].rstrip('\n') + '\n'
    else:
        new_lines = []

    # Calculate what the new file will look like
    if is_insertion:
        # Insert before start_line
        new_file_lines = lines[:start_idx] + new_lines + lines[start_idx:]
    else:
        # Replace lines from start_idx to end_idx (inclusive)
        new_file_lines = lines[:start_idx] + new_lines + lines[end_idx + 1:]

    # Calculate statistics
    lines_removed = 0 if is_insertion else (end_idx - start_idx + 1)
    lines_added = len(new_lines)
    net_change = lines_added - lines_removed

    # Preview mode - show changes without applying
    if inputs.preview:
        preview_info = {
            "filepath": validated_path,
            "preview_mode": True,
            "changes": {
                "start_line": inputs.start_line,
                "end_line": inputs.end_line,
                "lines_removed": lines_removed,
                "lines_added": lines_added,
                "net_change": net_change,
                "operation": "insert" if is_insertion else "replace" if lines_removed > 0 else "append"
            },
            "old_content": ''.join(lines[start_idx:end_idx + 1]) if not is_insertion else "",
            "new_content": inputs.new_content,
            "total_lines_before": total_lines,
            "total_lines_after": len(new_file_lines)
        }

        print(f"🔍 PREVIEW MODE - No changes made to '{inputs.filename}'")
        print(f"  → Would {'insert' if is_insertion else 'replace'} lines {inputs.start_line}-{inputs.end_line}")
        print(f"  → Lines removed: {lines_removed}, Lines added: {lines_added}, Net: {net_change:+d}")
        print(f"  → Total lines: {total_lines} → {len(new_file_lines)}")

        return preview_info

    # Atomic write: write to temp file first, then replace
    try:
        # Create temp file in the same directory as target (ensures same filesystem)
        dir_path = os.path.dirname(validated_path)
        with tempfile.NamedTemporaryFile(mode='w', dir=dir_path, delete=False, suffix='.tmp') as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.writelines(new_file_lines)

        # Atomic replace (on same filesystem, this is atomic)
        os.replace(tmp_path, validated_path)

    except Exception as e:
        # Clean up temp file if it exists
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise IOError(f"Failed to write file '{inputs.filename}': {e}")

    # Get final file size
    file_size = os.path.getsize(validated_path)

    result = {
        "filepath": validated_path,
        "success": True,
        "changes": {
            "start_line": inputs.start_line,
            "end_line": inputs.end_line,
            "lines_removed": lines_removed,
            "lines_added": lines_added,
            "net_change": net_change,
            "operation": "insert" if is_insertion else "replace" if lines_removed > 0 else "append"
        },
        "total_lines_before": total_lines,
        "total_lines_after": len(new_file_lines),
        "file_size": file_size
    }

    operation_desc = "Inserted" if is_insertion else "Replaced" if lines_removed > 0 else "Appended"
    print(f"{operation_desc} lines {inputs.start_line}-{inputs.end_line} in '{inputs.filename}'")
    print(f"  → Lines removed: {lines_removed}, Lines added: {lines_added}, Net change: {net_change:+d}")
    print(f"  → Total lines: {total_lines} → {len(new_file_lines)}")
    print(f"  → Location: {validated_path}")

    return result

@uf(name="user_confirm", version="1.0.0", description="Asks user for Y/N confirmation with easy defaults for permissions.")
def user_confirm(inputs: UserConfirmInput) -> dict:
    """Prompts user for Y/N confirmation with streamlined UX for permissions."""

    default_indicator = "[Y/n]" if inputs.default_yes else "[y/N]"
    print(f"\n🤖 {inputs.message}")
    print(f"👤 Confirm? {default_indicator} (just press Enter for default): ", end="", flush=True)

    try:
        user_input = input().strip().lower()

        # Handle empty input (just Enter pressed)
        if not user_input:
            confirmed = inputs.default_yes
            action_word = "allowed" if confirmed else "denied"
            print(f"Using default: {'Yes' if confirmed else 'No'} - {action_word}")
        else:
            # Parse various forms of yes/no
            yes_responses = {'y', 'yes', 'yeah', 'yep', 'ok', 'okay', 'sure', '1', 'true'}
            no_responses = {'n', 'no', 'nope', 'nah', '0', 'false'}

            if user_input in yes_responses:
                confirmed = True
                print("Yes - allowed")
            elif user_input in no_responses:
                confirmed = False
                print("No - denied")
            else:
                # Ambiguous input, use default
                confirmed = inputs.default_yes
                print(f"Unclear response '{user_input}', using default: {'Yes' if confirmed else 'No'}")

        return {
            "confirmed": confirmed,
            "user_input": user_input,
            "action": "proceed" if confirmed else "deny",
            "message": f"User {'confirmed' if confirmed else 'denied'} the action"
        }

    except KeyboardInterrupt:
        print("\n🛑 User interrupted - treating as 'No'")
        return {
            "confirmed": False,
            "user_input": "",
            "action": "abort",
            "message": "User interrupted with Ctrl+C - denied"
        }
    except EOFError:
        # No input available, use default
        confirmed = inputs.default_yes
        print(f"No input available, using default: {'Yes' if confirmed else 'No'}")
        return {
            "confirmed": confirmed,
            "user_input": "",
            "action": "proceed" if confirmed else "deny",
            "message": f"No input available, used default: {'Yes' if confirmed else 'No'}"
        }