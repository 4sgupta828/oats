# tools/search_integration.py

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import Field
from typing import List, Optional
from core.sdk import uf, UfInput
from .smart_search import SmartSearchEngine

class SmartSearchInput(UfInput):
    pattern: str = Field(..., description="The search pattern or text to find.")
    file_types: Optional[List[str]] = Field(None, description="List of file extensions to search in (without dots, e.g., ['csv', 'json']). If not specified, will search all relevant file types.")
    context_hint: Optional[str] = Field(None, description="Optional context hint about the type of data being searched (e.g., 'csv data', 'config file', 'log data').")
    max_results: int = Field(50, description="Maximum number of results to return.")

class FindFilesByNameInput(UfInput):
    filename_pattern: str = Field(..., description="Pattern to match in filenames (e.g., 'gpa', 'config', '.csv').")
    max_results: int = Field(20, description="Maximum number of results to return.")

class ContentSearchInput(UfInput):
    pattern: str = Field(..., description="Text pattern to search for within files.")
    file_types: Optional[List[str]] = Field(None, description="File extensions to search in (e.g., ['csv', 'txt']).")
    case_sensitive: bool = Field(False, description="Whether to perform case-sensitive search.")
    whole_words: bool = Field(False, description="Whether to match whole words only.")

@uf(name="smart_search", version="1.0.0", description="Intelligent search that efficiently finds content across files using pattern-first approach with progressive refinement.")
def smart_search(inputs: SmartSearchInput) -> dict:
    """
    Performs intelligent search using pattern-first approach instead of reading files individually.
    Uses ripgrep/grep for efficient searching and progressive refinement to find relevant results.
    """
    from core.workspace_security import get_workspace_security

    # Get workspace root for search engine
    workspace_security = get_workspace_security()
    workspace_root = str(workspace_security.workspace_root)

    # Initialize search engine
    search_engine = SmartSearchEngine(workspace_root)

    print(f"🔍 Smart searching for '{inputs.pattern}'...")
    if inputs.file_types:
        print(f"   Targeting file types: {inputs.file_types}")
    if inputs.context_hint:
        print(f"   Context hint: {inputs.context_hint}")

    # Perform smart search
    results = search_engine.smart_search(inputs.pattern, inputs.context_hint)

    # Limit results
    if len(results) > inputs.max_results:
        results = results[:inputs.max_results]
        print(f"   Limited to first {inputs.max_results} results")

    # Convert to return format
    formatted_results = []
    for result in results:
        # Get relative path from workspace root
        try:
            rel_path = os.path.relpath(result.file_path, workspace_root)
        except ValueError:
            rel_path = result.file_path

        formatted_result = {
            "file_path": rel_path,
            "absolute_path": result.file_path,
            "confidence": result.confidence,
            "search_scope": result.search_scope.value,
        }

        if result.match_line:
            formatted_result["line_number"] = result.match_line
        if result.match_content:
            formatted_result["preview"] = result.match_content[:200] + "..." if len(result.match_content) > 200 else result.match_content

        formatted_results.append(formatted_result)

    # Group results by file type for better presentation
    file_type_groups = {}
    for result in formatted_results:
        ext = os.path.splitext(result["file_path"])[1][1:] or "no_extension"
        if ext not in file_type_groups:
            file_type_groups[ext] = []
        file_type_groups[ext].append(result)

    print(f"✅ Found {len(formatted_results)} matches across {len(file_type_groups)} file types")
    for file_type, type_results in file_type_groups.items():
        print(f"   {file_type}: {len(type_results)} files")

    return {
        "pattern": inputs.pattern,
        "total_matches": len(formatted_results),
        "results": formatted_results,
        "file_type_breakdown": {ft: len(results) for ft, results in file_type_groups.items()},
        "search_strategy": "progressive_pattern_first"
    }

@uf(name="find_files_by_name", version="1.0.0", description="Efficiently find files by filename pattern using ripgrep/find instead of recursive directory walking.")
def find_files_by_name(inputs: FindFilesByNameInput) -> dict:
    """
    Find files by filename pattern using efficient command-line tools.
    Much faster than Python's os.walk for name-based searches.
    """
    from core.workspace_security import get_workspace_security

    # Get workspace root
    workspace_security = get_workspace_security()
    workspace_root = str(workspace_security.workspace_root)

    # Initialize search engine
    search_engine = SmartSearchEngine(workspace_root)

    print(f"📂 Finding files matching pattern '{inputs.filename_pattern}'...")

    # Find files
    file_paths = search_engine.find_files_by_name(inputs.filename_pattern)

    # Limit results
    if len(file_paths) > inputs.max_results:
        file_paths = file_paths[:inputs.max_results]
        print(f"   Limited to first {inputs.max_results} results")

    # Format results
    formatted_results = []
    for file_path in file_paths:
        try:
            rel_path = os.path.relpath(file_path, workspace_root)
        except ValueError:
            rel_path = file_path

        # Get file info
        file_info = {
            "file_path": rel_path,
            "absolute_path": file_path,
        }

        # Add file stats if accessible
        try:
            stat_result = os.stat(file_path)
            file_info["size"] = stat_result.st_size
            file_info["modified"] = stat_result.st_mtime
        except (OSError, IOError):
            pass

        formatted_results.append(file_info)

    # Group by file type
    file_type_groups = {}
    for result in formatted_results:
        ext = os.path.splitext(result["file_path"])[1][1:] or "no_extension"
        if ext not in file_type_groups:
            file_type_groups[ext] = []
        file_type_groups[ext].append(result)

    print(f"✅ Found {len(formatted_results)} files matching '{inputs.filename_pattern}'")
    for file_type, type_results in file_type_groups.items():
        print(f"   .{file_type}: {len(type_results)} files")

    return {
        "pattern": inputs.filename_pattern,
        "total_files": len(formatted_results),
        "files": formatted_results,
        "file_type_breakdown": {ft: len(results) for ft, results in file_type_groups.items()},
        "search_method": "efficient_filename_search"
    }

@uf(name="content_search", version="1.0.0", description="Search for specific content patterns within files using efficient grep-based approach.")
def content_search(inputs: ContentSearchInput) -> dict:
    """
    Search for content within files using ripgrep/grep for efficiency.
    """
    from core.workspace_security import get_workspace_security
    from .smart_search import SearchQuery

    # Get workspace root
    workspace_security = get_workspace_security()
    workspace_root = str(workspace_security.workspace_root)

    # Initialize search engine
    search_engine = SmartSearchEngine(workspace_root)

    print(f"🔎 Content searching for '{inputs.pattern}'...")
    if inputs.file_types:
        print(f"   In file types: {inputs.file_types}")

    # Build search query
    query = SearchQuery(
        pattern=inputs.pattern,
        file_types=inputs.file_types or [],
        exclude_patterns=[],
        directories=[],
        case_sensitive=inputs.case_sensitive,
        whole_words=inputs.whole_words
    )

    # Execute search
    results = search_engine.search_with_query(query)

    # Format results
    formatted_results = []
    for result in results:
        try:
            rel_path = os.path.relpath(result.file_path, workspace_root)
        except ValueError:
            rel_path = result.file_path

        formatted_result = {
            "file_path": rel_path,
            "absolute_path": result.file_path,
        }

        if result.match_line:
            formatted_result["line_number"] = result.match_line
        if result.match_content:
            formatted_result["match_content"] = result.match_content

        formatted_results.append(formatted_result)

    # Group by file
    file_groups = {}
    for result in formatted_results:
        file_path = result["file_path"]
        if file_path not in file_groups:
            file_groups[file_path] = []
        file_groups[file_path].append(result)

    print(f"✅ Found {len(formatted_results)} matches in {len(file_groups)} files")

    return {
        "pattern": inputs.pattern,
        "total_matches": len(formatted_results),
        "files_with_matches": len(file_groups),
        "results": formatted_results,
        "search_options": {
            "case_sensitive": inputs.case_sensitive,
            "whole_words": inputs.whole_words,
            "file_types": inputs.file_types
        }
    }