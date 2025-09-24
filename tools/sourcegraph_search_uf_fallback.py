#!/usr/bin/env python3
"""
Fallback-enabled Sourcegraph search enhancement for UF Flow.
Always returns useful results even if Sourcegraph CLI is not available.
"""

import os
import sys
# Ensure we use the correct oats directory and tools directory
oats_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tools_dir = os.path.dirname(os.path.abspath(__file__))
if oats_root not in sys.path:
    sys.path.insert(0, oats_root)
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from pydantic import Field
from typing import Optional
from core.sdk import uf, UfInput

class SourcegraphSearchInput(UfInput):
    query: str = Field(..., description="Search query - supports natural language (e.g., 'find PathManager class', 'locate login function')")
    language: Optional[str] = Field(None, description="Programming language filter (python, javascript, go, etc.)")
    max_results: int = Field(20, description="Maximum number of results to return")

@uf(name="sourcegraph_search_fallback", version="1.0.0",
   description="Semantic code search using Sourcegraph with smart fallbacks - always works!")
def sourcegraph_search_fallback(inputs: SourcegraphSearchInput) -> dict:
    """
    Advanced semantic code search with bulletproof fallbacks.
    """
    from core.workspace_security import get_workspace_security

    workspace_security = get_workspace_security()
    workspace_root = str(workspace_security.workspace_root)

    print(f"🔍 Sourcegraph search with fallback: '{inputs.query}'")

    # Always ensure Sourcegraph environment variables are set
    os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
    os.environ['SRC_ACCESS_TOKEN'] = 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d'

    # Try Sourcegraph first
    try:
        from sourcegraph_search import SourcegraphSearchEngine
        engine = SourcegraphSearchEngine(workspace_root)

        if engine.src_cli_available:
            print("🚀 Using Sourcegraph semantic search...")
            results = engine.smart_search(
                user_query=inputs.query,
                max_results=inputs.max_results
            )

            if results:
                formatted_results = []
                for result in results:
                    formatted_results.append({
                        "file": result.file_path,
                        "line": result.line_number,
                        "content": result.content.strip()[:100] + ("..." if len(result.content.strip()) > 100 else ""),
                        "symbol_kind": result.symbol_kind,
                        "language": result.language,
                        "confidence": result.confidence,
                        "source": "sourcegraph"
                    })

                return {
                    "success": True,
                    "search_engine": "sourcegraph",
                    "query": inputs.query,
                    "total_results": len(formatted_results),
                    "results": formatted_results,
                }

    except Exception as e:
        print(f"🔧 Sourcegraph failed: {e}")

    # Fallback to local grep-based search
    print("📁 Falling back to local grep search...")
    try:
        import subprocess
        import json
        from pathlib import Path

        # Use ripgrep for fast searching
        cmd = ['rg', '--json', '--max-count', str(inputs.max_results)]

        if inputs.language:
            if inputs.language == 'python':
                cmd.extend(['--type', 'py'])
            elif inputs.language == 'javascript':
                cmd.extend(['--type', 'js'])
            elif inputs.language in ['typescript', 'ts']:
                cmd.extend(['--type', 'ts'])

        cmd.append(inputs.query)
        cmd.append(workspace_root)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        fallback_results = []
        if result.returncode == 0:
            for line in result.stdout.strip().split('\\n'):
                if not line:
                    continue
                try:
                    match_data = json.loads(line)
                    if match_data.get('type') == 'match':
                        data = match_data.get('data', {})
                        path = data.get('path', {}).get('text', '')
                        line_num = data.get('line_number', 0)
                        content = data.get('lines', {}).get('text', '').strip()

                        fallback_results.append({
                            "file": path,
                            "line": line_num,
                            "content": content[:100] + ("..." if len(content) > 100 else ""),
                            "source": "ripgrep"
                        })
                except:
                    continue

        if fallback_results:
            return {
                "success": True,
                "search_engine": "ripgrep_fallback",
                "query": inputs.query,
                "total_results": len(fallback_results),
                "results": fallback_results,
                "note": "Using ripgrep fallback - Sourcegraph CLI not available"
            }

    except Exception as e:
        print(f"🔧 Ripgrep fallback failed: {e}")

    # Final fallback - return helpful info
    return {
        "success": False,
        "search_engine": "none",
        "query": inputs.query,
        "total_results": 0,
        "results": [],
        "error": "Both Sourcegraph and ripgrep fallback failed",
        "suggestion": "Try using other search tools like find_files_by_name or content_search",
        "debug_info": {
            "working_directory": workspace_root,
            "src_endpoint": os.environ.get('SRC_ENDPOINT'),
            "has_rg": subprocess.run(['which', 'rg'], capture_output=True).returncode == 0,
            "has_src": subprocess.run(['which', 'src'], capture_output=True).returncode == 0,
        }
    }

if __name__ == "__main__":
    # Quick test
    test_input = SourcegraphSearchInput(query="PathManager", max_results=3)
    result = sourcegraph_search_fallback(test_input)
    print(f"Test result: {result.get('success', False)}")