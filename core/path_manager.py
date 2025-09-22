# core/path_manager.py

import os
import uuid
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PathManager:
    """Manages consistent file path creation for the UF Flow system."""

    def __init__(self, repo_root: Optional[str] = None, current_subdir: Optional[str] = None):
        """
        Initialize path manager.

        Args:
            repo_root: Repository root directory (auto-detected if not provided)
            current_subdir: Current subdirectory relative to repo root (auto-detected if not provided)
        """
        self.repo_root = Path(repo_root) if repo_root else self._find_repo_root()
        self.current_subdir = Path(current_subdir) if current_subdir else self._get_current_subdir()
        self.session_id = self._generate_session_id()

        # Ensure paths are absolute and resolved
        self.repo_root = self.repo_root.resolve()

        logger.info(f"PathManager initialized:")
        logger.info(f"  - repo_root: {self.repo_root}")
        logger.info(f"  - current_subdir: {self.current_subdir}")
        logger.info(f"  - session_id: {self.session_id}")

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

    def _get_current_subdir(self) -> Path:
        """Get current subdirectory relative to repo root."""
        cwd = Path.cwd().resolve()
        try:
            return cwd.relative_to(self.repo_root)
        except ValueError:
            # Current directory is outside repo, use "."
            return Path(".")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique_id}"

    def get_tmp_dir(self) -> Path:
        """Get the temporary directory path: {repo_root}/{current_subdir}/tmp/{session_id}"""
        tmp_dir = self.repo_root / self.current_subdir / "tmp" / self.session_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir

    def get_permanent_dir(self) -> Path:
        """Get the permanent files directory path: {repo_root}/{current_subdir}"""
        perm_dir = self.repo_root / self.current_subdir
        perm_dir.mkdir(parents=True, exist_ok=True)
        return perm_dir

    def get_tmp_file(self, filename: str, suffix: str = "") -> str:
        """
        Get a temporary file path.

        Args:
            filename: Base filename
            suffix: Optional file suffix/extension

        Returns:
            Absolute path string for temporary file
        """
        if suffix and not suffix.startswith('.'):
            suffix = '.' + suffix

        full_filename = f"{filename}{suffix}"
        return str(self.get_tmp_dir() / full_filename)

    def get_permanent_file(self, filename: str) -> str:
        """
        Get a permanent file path in current subdirectory.

        Args:
            filename: Filename (can include subdirectories)

        Returns:
            Absolute path string for permanent file
        """
        return str(self.get_permanent_dir() / filename)

    def resolve_path(self, path: str, is_temporary: bool = False) -> str:
        """
        Resolve a path according to the file placement strategy.

        Args:
            path: Input path (can be relative or absolute)
            is_temporary: Whether this is a temporary file

        Returns:
            Resolved absolute path
        """
        path_obj = Path(path)

        # If absolute path, validate it's within repo
        if path_obj.is_absolute():
            try:
                path_obj.relative_to(self.repo_root)
                return str(path_obj)
            except ValueError:
                raise ValueError(f"Absolute path '{path}' is outside repository root")

        # For relative paths, apply our strategy
        if is_temporary:
            return str(self.get_tmp_dir() / path)
        else:
            return str(self.get_permanent_dir() / path)

    def cleanup_session(self) -> None:
        """Clean up temporary files for this session."""
        tmp_dir = self.repo_root / self.current_subdir / "tmp" / self.session_id
        if tmp_dir.exists():
            import shutil
            try:
                shutil.rmtree(tmp_dir)
                logger.info(f"Cleaned up session temporary directory: {tmp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup session directory {tmp_dir}: {e}")

    def get_info(self) -> Dict[str, Any]:
        """Get path manager information."""
        return {
            "repo_root": str(self.repo_root),
            "current_subdir": str(self.current_subdir),
            "session_id": self.session_id,
            "tmp_dir": str(self.get_tmp_dir()),
            "permanent_dir": str(self.get_permanent_dir())
        }

# Global instance
_path_manager = None

def get_path_manager(repo_root: Optional[str] = None, current_subdir: Optional[str] = None) -> PathManager:
    """Get the global path manager instance."""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager(repo_root, current_subdir)
    return _path_manager

def reset_path_manager():
    """Reset the global path manager (useful for testing)."""
    global _path_manager
    if _path_manager:
        _path_manager.cleanup_session()
    _path_manager = None

# Convenience functions
def get_tmp_file(filename: str, suffix: str = "") -> str:
    """Get a temporary file path."""
    return get_path_manager().get_tmp_file(filename, suffix)

def get_permanent_file(filename: str) -> str:
    """Get a permanent file path."""
    return get_path_manager().get_permanent_file(filename)

def resolve_file_path(path: str, is_temporary: bool = False) -> str:
    """Resolve a file path according to placement strategy."""
    return get_path_manager().resolve_path(path, is_temporary)