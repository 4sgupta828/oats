#!/usr/bin/env python3
"""
Minimal Sourcegraph search enhancement for UF Flow.
Adds ONE new UF tool that provides Sourcegraph semantic search capabilities
while preserving all existing search tools unchanged.
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

# Set up Sourcegraph environment variables at module level
os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
if 'SRC_ACCESS_TOKEN' not in os.environ:
    os.environ['SRC_ACCESS_TOKEN'] = os.environ.get('SRC_ACCESS_TOKEN', 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d')

from pydantic import Field
from typing import Optional
from core.sdk import uf, UfInput

class SourcegraphSearchInput(UfInput):
    query: str = Field(..., description="Search query - supports natural language (e.g., 'find PathManager class', 'locate login function')")
    language: Optional[str] = Field(None, description="Programming language filter (python, javascript, go, etc.)")
    max_results: int = Field(20, description="Maximum number of results to return")

@uf(name="sourcegraph_search", version="1.0.0",
   description="Semantic code search using Sourcegraph - understands functions, classes, symbols vs just text matching. Complements existing search tools.")
def sourcegraph_search(inputs: SourcegraphSearchInput) -> dict:
    """
    Advanced semantic code search using Sourcegraph CLI.

    Advantages over existing search tools:
    - Understands code semantics (functions, classes, symbols)
    - Cross-language symbol resolution
    - Natural language query mapping
    - Precise symbol definitions vs text matching

    Falls back to existing search tools if Sourcegraph unavailable.
    """
    from core.workspace_security import get_workspace_security

    workspace_security = get_workspace_security()
    workspace_root = str(workspace_security.workspace_root)

    print(f"🔍 Sourcegraph search: '{inputs.query}'")

    try:
        # Always ensure Sourcegraph environment variables are set
        import os
        os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
        # Always set the access token to ensure it's available
        os.environ['SRC_ACCESS_TOKEN'] = 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d'

        # Try Sourcegraph first
        from sourcegraph_search import SourcegraphSearchEngine

        engine = SourcegraphSearchEngine(workspace_root)

        if engine.src_cli_available:
            print("🚀 Using Sourcegraph semantic search...")

            results = engine.smart_search(
                user_query=inputs.query,
                max_results=inputs.max_results
            )

            formatted_results = []
            if results:
                for result in results:
                    formatted_results.append({
                        "file": result.file_path,
                        "line": result.line_number,
                        "content": result.content.strip()[:100] + ("..." if len(result.content.strip()) > 100 else ""),
                        "symbol_kind": result.symbol_kind,
                        "language": result.language,
                        "confidence": result.confidence
                    })

            return {
                "success": True,
                "search_engine": "sourcegraph",
                "query": inputs.query,
                "total_results": len(formatted_results),
                "results": formatted_results,
                "advantages": [
                    "Semantic code understanding vs text matching",
                    "Symbol-aware search with precise definitions",
                    "Cross-language symbol resolution"
                ]
            }

        print("⚠️  Sourcegraph CLI not available, use existing search tools")

        return {
            "success": False,
            "error": "Sourcegraph CLI not available",
            "fallback_suggestion": "Use smart_search, find_files_by_name, or content_search from existing tools",
            "install_instructions": [
                "curl -L https://sourcegraph.com/.api/src-cli/src_linux_amd64 -o src",
                "chmod +x src && sudo mv src /usr/local/bin/"
            ],
            "results": []
        }

    except ImportError:
        print("⚠️  Sourcegraph engine not available, use existing search tools")
        return {
            "success": False,
            "error": "Sourcegraph engine not available",
            "fallback_suggestion": "Use existing search tools: smart_search, find_files_by_name, content_search",
            "results": []
        }
    except Exception as e:
        print(f"⚠️  Sourcegraph search failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback_suggestion": "Use existing search tools for reliable results",
            "results": []
        }

if __name__ == "__main__":
    # Quick test
    test_input = SourcegraphSearchInput(query="PathManager", max_results=3)
    result = sourcegraph_search(test_input)
    print(f"Test result: {result.get('success', False)}")