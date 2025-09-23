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

class FindFunctionInput(UfInput):
    filename: str = Field(..., description="The name of the file to search in.")
    function_name: str = Field(..., description="The name of the function or class to find (e.g., 'def my_function' or 'class MyClass').")
    match_type: str = Field("function", description="Type to match: 'function' (def), 'class', or 'any' (both def and class).")

class SearchFunctionsInput(UfInput):
    function_name: str = Field(..., description="JUST the function/class name pattern to search for (e.g., 'my_function', 'MyClass', or '.*' for all). Do NOT include 'def' or 'class' keywords - they are added automatically.")
    match_type: str = Field("function", description="Type to match: 'function' (def), 'class', or 'any' (both def and class).")
    file_extensions: list = Field(default=[".py"], description="File extensions to search in (default: ['.py']).")
    max_results: int = Field(10, description="Maximum number of results to return.")
    use_regex: bool = Field(False, description="If True, treat function_name as a regex pattern. If False, search for exact name match.")

class UserPromptInput(UfInput):
    question: str = Field(..., description="The question or request to ask the user.")

class UserConfirmInput(UfInput):
    message: str = Field(..., description="The action or permission to confirm with the user.")
    default_yes: bool = Field(True, description="Whether to default to 'Yes' when user just presses Enter.")

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

@uf(name="find_function", version="1.0.0", description="Finds the line number of a specific function or class definition in a file for targeted reading.")
def find_function(inputs: FindFunctionInput) -> dict:
    """Finds function/class definitions and returns their line numbers for targeted reading."""
    from core.workspace_security import validate_workspace_path
    import re

    # Validate path with file search
    validated_path = validate_workspace_path(inputs.filename, "file reading")

    # Read the file
    with open(validated_path, 'r') as f:
        lines = f.readlines()

    matches = []

    # Create regex patterns based on match type
    if inputs.match_type == "function":
        # Match function definitions (def function_name)
        pattern = rf'^\s*def\s+{re.escape(inputs.function_name)}\s*\('
    elif inputs.match_type == "class":
        # Match class definitions (class ClassName)
        pattern = rf'^\s*class\s+{re.escape(inputs.function_name)}\s*[\(:]'
    else:  # "any"
        # Match both function and class definitions
        pattern = rf'^\s*(def|class)\s+{re.escape(inputs.function_name)}\s*[\(:]'

    # Search through lines
    for i, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            line_num = i + 1
            matches.append({
                "file": inputs.filename,
                "line": line_num,
                "match": line.strip()
            })

    result = {
        "filename": inputs.filename,
        "search_term": inputs.function_name,
        "matches": matches,
        "total_matches": len(matches)
    }

    if matches:
        print(f"Found {len(matches)} match(es) for '{inputs.function_name}' in '{inputs.filename}':")
        for match in matches:
            print(f"  → Line {match['line']}: {match['match']}")
        print(f"💡 Use read_file with start_line={matches[0]['line']} and context_lines=10 for targeted analysis")
    else:
        print(f"No matches found for '{inputs.function_name}' in '{inputs.filename}'")
        print(f"💡 Try searching with match_type='any' or check the exact function/class name")

    return result

@uf(name="search_functions", version="1.0.0", description="Searches for function or class definitions across the entire codebase. Use this FIRST when you need to find where a function is defined. IMPORTANT: function_name should be just the name pattern (e.g., 'my_function' or '.*' for all), NOT 'def my_function' or 'class MyClass'. The tool automatically adds 'def'/'class' keywords.")
def search_functions(inputs: SearchFunctionsInput) -> dict:
    """Searches for function/class definitions across all files in the workspace."""
    from core.workspace_security import validate_workspace_path
    import re
    import os

    # Get workspace root
    try:
        workspace_root = validate_workspace_path(".", "directory search")
    except Exception as e:
        return {"error": f"Cannot access workspace: {e}", "matches": [], "total_matches": 0}

    matches = []

    # Defensive check for file_extensions
    file_extensions = inputs.file_extensions if inputs.file_extensions else [".py"]

    # Create regex patterns based on match type and regex setting
    name_pattern = inputs.function_name if inputs.use_regex else re.escape(inputs.function_name)

    if inputs.match_type == "function":
        pattern = rf'^\s*def\s+({name_pattern})\s*\('
    elif inputs.match_type == "class":
        pattern = rf'^\s*class\s+({name_pattern})\s*[\(:]'
    else:  # "any"
        pattern = rf'^\s*(def|class)\s+({name_pattern})\s*[\(:]'

    # Walk through workspace directory
    files_searched = 0
    for root, dirs, files in os.walk(workspace_root):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not _should_exclude_path(d)]

        for file in files:
            # Check file extension
            if not any(file.endswith(ext) for ext in file_extensions):
                continue

            # Skip excluded files
            if _should_exclude_path(file):
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, workspace_root)
            files_searched += 1

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            matches.append({
                                "file": relative_path,
                                "line": line_num,
                                "match": line.strip()
                            })

                            # Stop if we hit max results
                            if len(matches) >= inputs.max_results:
                                break

                if len(matches) >= inputs.max_results:
                    break
            except Exception as e:
                # Skip files that can't be read
                continue

        if len(matches) >= inputs.max_results:
            break

    result = {
        "search_term": inputs.function_name,
        "file_extensions": file_extensions,
        "matches": matches,
        "total_matches": len(matches),
        "files_searched": files_searched,
        "truncated": len(matches) >= inputs.max_results
    }

    if matches:
        print(f"🔍 Found {len(matches)} match(es) for '{inputs.function_name}' across {files_searched} files:")
        for match in matches[:5]:  # Show first 5 matches
            print(f"  → {match['file']}:{match['line']} - {match['match']}")

        if len(matches) > 5:
            print(f"  ... and {len(matches) - 5} more matches")

        if result['truncated']:
            print(f"  (Results truncated to {inputs.max_results} matches)")

        print(f"💡 Next steps:")
        print(f"   1. Choose a file from the results above")
        print(f"   2. Use: read_file('{matches[0]['file']}', start_line={matches[0]['line']}, context_lines=10)")
    else:
        print(f"❌ No matches found for '{inputs.function_name}' in {files_searched} {file_extensions} files")
        print(f"💡 Try:")
        print(f"   - Check spelling: '{inputs.function_name}'")
        print(f"   - Use '.*' to find all {inputs.match_type}s")
        print(f"   - Try match_type='any' to search both functions and classes")
        print(f"   - Remember: use JUST the name (not 'def name' or 'class Name')")
        print(f"   - Add more file extensions: ['.py', '.js', '.ts', etc.]")

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