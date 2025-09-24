#!/usr/bin/env python3
"""
Local code search tool for UF Flow coding agent.
Provides fast code search and analysis without requiring external services.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Represents a search result."""
    file_path: str
    line_number: int
    content: str
    context_before: List[str]
    context_after: List[str]
    match_type: str  # 'exact', 'regex', 'fuzzy'

class LocalCodeSearch:
    """Local code search engine for the UF Flow codebase."""

    def __init__(self, root_path: str = None):
        """
        Initialize the local code search.

        Args:
            root_path: Root directory to search (defaults to current directory)
        """
        self.root_path = Path(root_path) if root_path else Path.cwd()
        self.excluded_dirs = {
            '.git', '__pycache__', 'node_modules', '.pytest_cache',
            'tmp', 'logs', '.vscode', '.idea', 'build', 'dist'
        }
        self.code_extensions = {
            '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.c',
            '.h', '.hpp', '.go', '.rs', '.rb', '.php', '.swift', '.kt'
        }

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if a file is a code file."""
        return file_path.suffix.lower() in self.code_extensions

    def _should_exclude_dir(self, dir_path: Path) -> bool:
        """Check if a directory should be excluded from search."""
        return dir_path.name in self.excluded_dirs or dir_path.name.startswith('.')

    def _get_file_content(self, file_path: Path) -> List[str]:
        """Get file content as list of lines."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return []

    def search_text(
        self,
        query: str,
        case_sensitive: bool = False,
        regex: bool = False,
        file_pattern: Optional[str] = None,
        max_results: int = 50
    ) -> List[SearchResult]:
        """
        Search for text in code files.

        Args:
            query: Text to search for
            case_sensitive: Whether search should be case sensitive
            regex: Whether query is a regex pattern
            file_pattern: File pattern to match (e.g., "*.py")
            max_results: Maximum number of results

        Returns:
            List of search results
        """
        results = []
        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            if regex:
                pattern = re.compile(query, flags)
            else:
                # Escape special regex characters for literal search
                escaped_query = re.escape(query)
                pattern = re.compile(escaped_query, flags)
        except re.error as e:
            logger.error(f"Invalid regex pattern: {e}")
            return []

        for file_path in self._get_code_files(file_pattern):
            if len(results) >= max_results:
                break

            lines = self._get_file_content(file_path)
            for line_num, line in enumerate(lines, 1):
                if pattern.search(line):
                    context_before = lines[max(0, line_num-3):line_num-1]
                    context_after = lines[line_num:line_num+3]

                    results.append(SearchResult(
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        content=line.rstrip(),
                        context_before=[l.rstrip() for l in context_before],
                        context_after=[l.rstrip() for l in context_after],
                        match_type='regex' if regex else 'exact'
                    ))

        return results

    def search_functions(
        self,
        function_name: Optional[str] = None,
        file_pattern: Optional[str] = None,
        max_results: int = 50
    ) -> List[SearchResult]:
        """
        Search for function definitions.

        Args:
            function_name: Specific function name to search for
            file_pattern: File pattern to match
            max_results: Maximum number of results

        Returns:
            List of function definition results
        """
        if function_name:
            # Search for specific function
            query = rf'\bdef\s+{re.escape(function_name)}\s*\('
            return self.search_text(query, regex=True, file_pattern=file_pattern, max_results=max_results)
        else:
            # Search for all function definitions
            return self.search_text(r'^\s*def\s+\w+\s*\(', regex=True, file_pattern=file_pattern, max_results=max_results)

    def search_classes(
        self,
        class_name: Optional[str] = None,
        file_pattern: Optional[str] = None,
        max_results: int = 50
    ) -> List[SearchResult]:
        """
        Search for class definitions.

        Args:
            class_name: Specific class name to search for
            file_pattern: File pattern to match
            max_results: Maximum number of results

        Returns:
            List of class definition results
        """
        if class_name:
            # Search for specific class
            query = rf'\bclass\s+{re.escape(class_name)}\s*[\(:]'
            return self.search_text(query, regex=True, file_pattern=file_pattern, max_results=max_results)
        else:
            # Search for all class definitions
            return self.search_text(r'^\s*class\s+\w+\s*[\(:]', regex=True, file_pattern=file_pattern, max_results=max_results)

    def search_imports(
        self,
        module_name: Optional[str] = None,
        file_pattern: Optional[str] = None,
        max_results: int = 50
    ) -> List[SearchResult]:
        """
        Search for import statements.

        Args:
            module_name: Specific module name to search for
            file_pattern: File pattern to match
            max_results: Maximum number of results

        Returns:
            List of import statement results
        """
        if module_name:
            # Search for specific import
            query = rf'\b(import|from)\s+{re.escape(module_name)}\b'
            return self.search_text(query, regex=True, file_pattern=file_pattern, max_results=max_results)
        else:
            # Search for all imports
            return self.search_text(r'^\s*(import|from)\s+', regex=True, file_pattern=file_pattern, max_results=max_results)

    def search_symbols(
        self,
        symbol_name: str,
        file_pattern: Optional[str] = None,
        max_results: int = 50
    ) -> List[SearchResult]:
        """
        Search for symbol usage (functions, classes, variables).

        Args:
            symbol_name: Symbol name to search for
            file_pattern: File pattern to match
            max_results: Maximum number of results

        Returns:
            List of symbol usage results
        """
        # Search for symbol usage (not definitions)
        escaped_name = re.escape(symbol_name)

        # Patterns that indicate usage rather than definition
        usage_patterns = [
            rf'\b{escaped_name}\s*\(',  # Function call
            rf'\b{escaped_name}\.',     # Method/property access
            rf'=\s*{escaped_name}\b',   # Assignment
            rf'\b{escaped_name}\b',     # General usage
        ]

        all_results = []
        for pattern in usage_patterns:
            results = self.search_text(pattern, regex=True, file_pattern=file_pattern, max_results=max_results)
            all_results.extend(results)

        # Remove duplicates and sort by file and line
        seen = set()
        unique_results = []
        for result in all_results:
            key = (result.file_path, result.line_number)
            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        return sorted(unique_results, key=lambda x: (x.file_path, x.line_number))[:max_results]

    def find_file(self, filename: str) -> List[Path]:
        """
        Find files by name.

        Args:
            filename: Filename or pattern to search for

        Returns:
            List of matching file paths
        """
        results = []
        pattern = re.compile(filename.replace('*', '.*'), re.IGNORECASE)

        for file_path in self._get_code_files():
            if pattern.search(file_path.name):
                results.append(file_path.relative_to(self.root_path))

        return results

    def _get_code_files(self, file_pattern: Optional[str] = None) -> List[Path]:
        """Get all code files in the project."""
        files = []

        for file_path in self.root_path.rglob('*'):
            if file_path.is_file() and self._is_code_file(file_path):
                # Check if any parent directory should be excluded
                if any(self._should_exclude_dir(p) for p in file_path.parents):
                    continue

                # Check file pattern if provided
                if file_pattern:
                    if not file_path.match(file_pattern):
                        continue

                files.append(file_path)

        return files

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get information about a specific file.

        Args:
            file_path: Path to the file

        Returns:
            File information dictionary
        """
        full_path = self.root_path / file_path

        if not full_path.exists():
            return {"error": "File not found"}

        try:
            content = self._get_file_content(full_path)
            stats = full_path.stat()

            return {
                "path": str(full_path.relative_to(self.root_path)),
                "size": stats.st_size,
                "lines": len(content),
                "modified": stats.st_mtime,
                "extension": full_path.suffix,
                "exists": True
            }
        except Exception as e:
            return {"error": str(e)}

def search_code(
    query: str,
    search_type: str = "text",
    file_pattern: Optional[str] = None,
    max_results: int = 20,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Main search function for the coding agent.

    Args:
        query: Search query
        search_type: Type of search (text, function, class, import, symbol)
        file_pattern: File pattern to match
        max_results: Maximum number of results
        case_sensitive: Whether search should be case sensitive

    Returns:
        Search results dictionary
    """
    searcher = LocalCodeSearch()

    try:
        if search_type == "text":
            results = searcher.search_text(query, case_sensitive=case_sensitive, file_pattern=file_pattern, max_results=max_results)
        elif search_type == "function":
            results = searcher.search_functions(query, file_pattern=file_pattern, max_results=max_results)
        elif search_type == "class":
            results = searcher.search_classes(query, file_pattern=file_pattern, max_results=max_results)
        elif search_type == "import":
            results = searcher.search_imports(query, file_pattern=file_pattern, max_results=max_results)
        elif search_type == "symbol":
            results = searcher.search_symbols(query, file_pattern=file_pattern, max_results=max_results)
        else:
            return {"error": f"Unknown search type: {search_type}"}

        # Convert results to dictionaries
        result_dicts = []
        for result in results:
            result_dicts.append({
                "file_path": result.file_path,
                "line_number": result.line_number,
                "content": result.content,
                "context_before": result.context_before,
                "context_after": result.context_after,
                "match_type": result.match_type
            })

        return {
            "success": True,
            "search_type": search_type,
            "query": query,
            "results": result_dicts,
            "total_results": len(result_dicts),
            "message": f"Found {len(result_dicts)} results for '{query}' ({search_type} search)"
        }

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "total_results": 0
        }

# Tool definition for integration with UF Flow
LOCAL_SEARCH_TOOL_DEFINITION = {
    "name": "local_code_search",
    "description": "Search and analyze code in the local codebase. Fast, offline code search without external dependencies.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query or pattern to find in code"
            },
            "search_type": {
                "type": "string",
                "enum": ["text", "function", "class", "import", "symbol"],
                "description": "Type of search to perform"
            },
            "file_pattern": {
                "type": "string",
                "description": "File pattern to match (e.g., '*.py', '*.js')"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 20)",
                "default": 20
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether search should be case sensitive (default: false)",
                "default": False
            }
        },
        "required": ["query", "search_type"]
    }
}

if __name__ == "__main__":
    # Test the local search tool
    print("Testing local code search...")

    # Test text search
    result = search_code("PathManager", "text", "*.py", max_results=5)
    print(f"Text search result: {result['message']}")

    # Test function search
    result = search_code("get_tmp_file", "function", "*.py", max_results=3)
    print(f"Function search result: {result['message']}")

    # Test class search
    result = search_code("PathManager", "class", "*.py", max_results=3)
    print(f"Class search result: {result['message']}")

    # Show sample results
    if result.get('success') and result.get('results'):
        print(f"\nSample result:")
        sample = result['results'][0]
        print(f"  File: {sample['file_path']}")
        print(f"  Line {sample['line_number']}: {sample['content']}")