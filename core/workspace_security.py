# core/workspace_security.py

import os
import sys
from pathlib import Path
from typing import Optional, List, Union, TextIO
import logging

logger = logging.getLogger(__name__)

# Import path manager for consistent file placement
from .path_manager import get_path_manager

class WorkspaceSecurity:
    """Manages workspace security and path validation for the ReAct framework."""

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize workspace security.

        Args:
            workspace_root: Root directory for workspace. Defaults to current git repo root.
        """
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
        else:
            self.workspace_root = self._find_repo_root()

        logger.info(f"Workspace security initialized with root: {self.workspace_root}")

    def _find_repo_root(self) -> Path:
        """Find the repository root directory."""
        current = Path.cwd()

        # Look for .git directory
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent

        # If no git repo found, use current working directory
        return Path.cwd()

    def _find_file_recursive(self, filename: str) -> Optional[str]:
        """
        Recursively search for a file starting from workspace root.
        If multiple files are found, consult user to choose, unless it's a specific path.

        Args:
            filename: Name of file to search for (can be relative path)

        Returns:
            Absolute path to chosen file, or None if not found
        """
        import os
        from pathlib import Path

        # If filename contains path separators, treat it as an explicit path
        # This respects the ReAct agent's file disambiguation decisions
        if os.path.sep in filename or '/' in filename:
            # Agent specified a path - check if it exists directly
            potential_path = Path(self.workspace_root) / filename
            if potential_path.exists():
                print(f"🤖 Using agent-specified path: {filename}")
                return str(potential_path)
            else:
                # Path specified but doesn't exist
                return None

        # Find all matches for simple filenames
        matches = self._find_all_files_recursive(filename)

        if not matches:
            return None
        elif len(matches) == 1:
            return matches[0]
        else:
            # Multiple matches found - consult user or use LLM
            return self._consult_user_for_file_choice(filename, matches)

    def _find_all_files_recursive(self, filename: str) -> List[str]:
        """
        Find all files matching the name recursively from workspace root.

        Args:
            filename: Name of file to search for

        Returns:
            List of absolute paths to all matches
        """
        import os
        from pathlib import Path

        matches = []
        target = Path(filename)

        # If it's a complex path (has directories), search for the exact structure
        if len(target.parts) > 1:
            for root, dirs, files in os.walk(self.workspace_root):
                # Skip hidden directories and common exclusions
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'node_modules', '.git'}]

                current_path = Path(root)
                potential_path = current_path / filename
                if potential_path.exists():
                    matches.append(str(potential_path))
        else:
            # Simple filename - search recursively
            for root, dirs, files in os.walk(self.workspace_root):
                # Skip hidden directories and common exclusions
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'node_modules', '.git'}]

                if filename in files:
                    found_path = Path(root) / filename
                    matches.append(str(found_path))

        return matches

    def _consult_user_for_file_choice(self, filename: str, matches: List[str]) -> Optional[str]:
        """
        Present user with multiple file choices and get their selection.
        Use intelligent context-aware selection when possible.

        Args:
            filename: Original filename requested
            matches: List of absolute paths to matching files

        Returns:
            User's chosen file path, or None if cancelled
        """
        # The ReAct agent should have provided a specific path,
        # but if we get here with multiple matches, ask the user

        print(f"\n🤔 Multiple '{filename}' files found:")

        # Show relative paths from workspace root for clarity
        relative_matches = []
        for i, match in enumerate(matches, 1):
            try:
                rel_path = Path(match).relative_to(self.workspace_root)
                relative_matches.append(str(rel_path))
                print(f"  {i}. {rel_path}")
            except ValueError:
                # Fallback to absolute path if relative fails
                relative_matches.append(match)
                print(f"  {i}. {match}")

        print("  0. Cancel operation")

        # Check if we can get user input
        try:
            choice = input(f"\n👤 Which '{filename}' file do you want to use? (0-{len(matches)}): ").strip()

            if choice == '0' or choice.lower() in ['cancel', 'c']:
                print("Operation cancelled by user.")
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(matches):
                selected = matches[choice_num - 1]
                print(f"✅ Using: {relative_matches[choice_num - 1]}")
                return selected
            else:
                print(f"Please enter a number between 0 and {len(matches)}")
                return self._consult_user_for_file_choice(filename, matches)  # Retry

        except (EOFError, KeyboardInterrupt):
            # Non-interactive mode - use intelligent defaults
            print("\n🤖 Non-interactive mode detected. Using intelligent default...")

            # Use simple fallback - closest to root
            fallback_choice = min(matches, key=lambda x: len(Path(x).relative_to(self.workspace_root).parts))
            try:
                rel_path = Path(fallback_choice).relative_to(self.workspace_root)
                print(f"✅ Auto-selected: {rel_path} (intelligent selection)")
            except ValueError:
                print(f"✅ Auto-selected: {fallback_choice}")

            return fallback_choice

        except ValueError:
            print("Please enter a valid number")
            return self._consult_user_for_file_choice(filename, matches)  # Retry


    def validate_path(self, path: str, operation: str = "access", is_temporary: bool = None) -> str:
        """
        Validate that a path is within the workspace boundaries.

        Args:
            path: Path to validate
            operation: Operation being performed (for logging)
            is_temporary: Whether this is a temporary file (auto-detected if None)

        Returns:
            Validated absolute path

        Raises:
            ValueError: If path is outside workspace
        """
        try:
            # Auto-detect if this is a temporary file based on operation or path
            if is_temporary is None:
                is_temporary = (
                    'temp' in operation.lower() or
                    'tmp' in operation.lower() or
                    'temporary' in path.lower() or
                    'tmp' in path.lower() or
                    path.endswith('.tmp')
                )

            # Use path manager for consistent path resolution
            path_manager = get_path_manager()

            # For relative paths, decide based on operation
            if not os.path.isabs(path):
                # Special handling for directory operations
                if operation == "directory listing":
                    if path == ".":
                        # Current directory - use current working directory
                        abs_path = Path.cwd().resolve()
                    else:
                        # Other directory paths - search or resolve normally
                        found_path = self._find_file_recursive(path)
                        if found_path:
                            abs_path = Path(found_path).resolve()
                        else:
                            # Try standard path resolution for directories
                            abs_path = (Path.cwd() / path).resolve()
                # For file operations, search recursively from repo root
                elif operation in ["existence check", "file reading"]:
                    found_path = self._find_file_recursive(path)
                    if found_path:
                        abs_path = Path(found_path).resolve()
                    else:
                        # For file_exists, we need to return a path even if file doesn't exist
                        # For other read operations, we can fail
                        if operation == "existence check":
                            # Return the most logical path for existence check
                            abs_path = (self.workspace_root / path).resolve()
                        else:
                            raise FileNotFoundError(f"File '{path}' not found in workspace")
                else:
                    # For write operations, use path manager for consistent placement
                    resolved_path = path_manager.resolve_path(path, is_temporary)
                    abs_path = Path(resolved_path).resolve()
            else:
                # For absolute paths, validate directly
                abs_path = Path(path).resolve()

            # Check if path is within workspace
            try:
                abs_path.relative_to(self.workspace_root)
            except ValueError:
                raise ValueError(
                    f"Path '{path}' is outside workspace boundary. "
                    f"Workspace root: {self.workspace_root}"
                )

            # Additional security checks
            path_str = str(abs_path)

            # Block dangerous directories
            dangerous_dirs = [
                '/etc', '/usr/bin', '/usr/sbin', '/sbin', '/bin',
                '/System', '/private', '/var/log', '/var/run'
            ]

            for dangerous_dir in dangerous_dirs:
                if path_str.startswith(dangerous_dir):
                    raise ValueError(f"Access to system directory '{dangerous_dir}' is not allowed")

            # Block access to parent directories outside workspace
            if '..' in Path(path).parts:
                # Re-check after resolution to ensure we're still in workspace
                try:
                    abs_path.relative_to(self.workspace_root)
                except ValueError:
                    raise ValueError(f"Path traversal outside workspace is not allowed: {path}")

            logger.debug(f"Path validated for {operation}: {path} -> {abs_path} (temporary: {is_temporary})")
            return str(abs_path)

        except Exception as e:
            logger.error(f"Path validation failed for {operation}: {path} - {e}")
            raise

    def validate_command(self, command: str) -> str:
        """
        Validate shell command for security.

        Args:
            command: Command to validate

        Returns:
            Validated command

        Raises:
            ValueError: If command is dangerous
        """
        # Forbidden commands
        forbidden_commands = [
            'sudo', 'su', 'chmod 777', 'rm -rf /', 'rm -rf *',
            'dd', 'mkfs', 'fdisk', 'mount', 'umount',
            'systemctl', 'service', 'passwd', 'useradd', 'userdel'
        ]

        command_lower = command.lower()
        for forbidden in forbidden_commands:
            if forbidden in command_lower:
                raise ValueError(f"Command '{forbidden}' is not allowed for security reasons")

        # Check for attempts to access system files/directories
        system_paths = [
            '/etc/', '/usr/', '/var/log/', '/System/', '/private/',
            '/bin/', '/sbin/', '/usr/bin/', '/usr/sbin/'
        ]

        for sys_path in system_paths:
            if sys_path in command:
                raise ValueError(f"Access to system path '{sys_path}' is not allowed")

        # Additional check for absolute paths in commands
        parts = command.split()
        for part in parts:
            if part.startswith('/'):
                for sys_path in system_paths:
                    if part.startswith(sys_path.rstrip('/')):
                        raise ValueError(f"Access to system path '{sys_path}' is not allowed")

        # Prevent path traversal in commands
        if '../' in command or '/..' in command:
            # Check if the resolved paths would escape workspace
            parts = command.split()
            for part in parts:
                if os.path.sep in part and ('..' in part or part.startswith('/')):
                    try:
                        self.validate_path(part, "command argument")
                    except ValueError:
                        raise ValueError(f"Command contains path outside workspace: {part}")

        # Check for commands that try to copy/move system files
        copy_commands = ['cp', 'mv', 'rsync']
        for copy_cmd in copy_commands:
            if command.strip().startswith(copy_cmd + ' '):
                parts = command.split()
                for part in parts[1:]:  # Skip the command itself
                    if part.startswith('/'):
                        for sys_path in system_paths:
                            if part.startswith(sys_path):
                                raise ValueError(f"Copying from system path '{sys_path}' is not allowed")

        return command

    def get_allowed_directories(self) -> List[str]:
        """Get list of directories that are allowed for operations."""
        return [
            str(self.workspace_root),
            str(self.workspace_root / 'tools'),
            str(self.workspace_root / 'logs'),
            str(self.workspace_root / 'temp'),
            str(self.workspace_root / 'output'),
        ]

    def create_safe_working_directory(self, subdir: str = "temp") -> str:
        """
        Create a safe working directory within the workspace.

        Args:
            subdir: Subdirectory name within workspace

        Returns:
            Path to safe working directory
        """
        safe_dir = self.workspace_root / subdir
        safe_dir.mkdir(exist_ok=True)
        return str(safe_dir)

    def get_tmp_file_path(self, filename: str, suffix: str = "") -> str:
        """
        Get a temporary file path using the path manager.

        Args:
            filename: Base filename
            suffix: Optional file suffix

        Returns:
            Path to temporary file
        """
        from .path_manager import get_tmp_file
        return get_tmp_file(filename, suffix)

    def get_permanent_file_path(self, filename: str) -> str:
        """
        Get a permanent file path using the path manager.

        Args:
            filename: Filename

        Returns:
            Path to permanent file
        """
        from .path_manager import get_permanent_file
        return get_permanent_file(filename)

    def secure_open(self, path: str, mode: str = 'r', **kwargs):
        """Securely open a file within the workspace."""
        validated_path = self.validate_path(path, f"file {mode}")
        return open(validated_path, mode, **kwargs)

    def secure_read_text(self, path: str) -> str:
        """Securely read text from a file within the workspace."""
        with self.secure_open(path, 'r') as f:
            return f.read()

    def secure_write_text(self, path: str, content: str) -> None:
        """Securely write text to a file within the workspace."""
        with self.secure_open(path, 'w') as f:
            f.write(content)

# Global instance
_workspace_security = None

def get_workspace_security(workspace_root: Optional[str] = None) -> WorkspaceSecurity:
    """Get the global workspace security instance."""
    global _workspace_security
    if _workspace_security is None:
        _workspace_security = WorkspaceSecurity(workspace_root)
    return _workspace_security

def validate_workspace_path(path: str, operation: str = "access", is_temporary: bool = None) -> str:
    """Convenience function to validate workspace path."""
    return get_workspace_security().validate_path(path, operation, is_temporary)

# Secure file operations - use these instead of open()
def secure_open(path: str, mode: str = 'r', **kwargs):
    """Securely open a file within the workspace."""
    return get_workspace_security().secure_open(path, mode, **kwargs)

def secure_read_text(path: str) -> str:
    """Securely read text from a file within the workspace."""
    return get_workspace_security().secure_read_text(path)

def secure_write_text(path: str, content: str) -> None:
    """Securely write text to a file within the workspace."""
    return get_workspace_security().secure_write_text(path, content)

def validate_workspace_command(command: str) -> str:
    """Convenience function to validate workspace command."""
    return get_workspace_security().validate_command(command)