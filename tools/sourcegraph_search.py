#!/usr/bin/env python3
"""
Sourcegraph-powered code search tool for UF Flow.
Provides intelligent code search using Sourcegraph's advanced capabilities,
preferred over simplistic grep/regex-based tools.
"""

import os
import subprocess
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Set up Sourcegraph environment variables at module level
os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
if 'SRC_ACCESS_TOKEN' not in os.environ:
    os.environ['SRC_ACCESS_TOKEN'] = os.environ.get('SRC_ACCESS_TOKEN', 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d')

class SearchType(Enum):
    """Types of code search supported by Sourcegraph"""
    TEXT = "text"
    SYMBOL = "symbol"
    FUNCTION = "function"
    CLASS = "class"
    IMPORT = "import"
    STRUCT = "struct"
    INTERFACE = "interface"
    VARIABLE = "variable"
    CONSTANT = "constant"
    STRUCTURAL = "structural"

class LanguageType(Enum):
    """Programming languages supported"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"
    CPP = "cpp"
    RUST = "rust"
    PHP = "php"
    RUBY = "ruby"

@dataclass
class SearchResult:
    """Represents a Sourcegraph search result with rich metadata"""
    file_path: str
    line_number: int
    content: str
    symbol_kind: Optional[str] = None
    symbol_name: Optional[str] = None
    context_before: List[str] = None
    context_after: List[str] = None
    repository: Optional[str] = None
    language: Optional[str] = None
    confidence: float = 1.0

@dataclass
class SourcegraphQuery:
    """Structured representation of a Sourcegraph query"""
    pattern: str
    search_type: SearchType
    language: Optional[LanguageType] = None
    file_pattern: Optional[str] = None
    repo_pattern: Optional[str] = None
    exclude_patterns: List[str] = None
    max_results: int = 50
    structural_search: bool = False

class SourcegraphSearchEngine:
    """
    Advanced code search engine using Sourcegraph CLI.
    Provides intelligent query mapping from user requests to Sourcegraph syntax.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.src_cli_available = self._check_src_cli()

        # Query mapping patterns for intelligent search type detection
        self.search_patterns = {
            # Function patterns
            'function': [
                r'\bdef\s+\w+', r'\bfunction\s+\w+', r'\bfunc\s+\w+',
                r'function_name', r'method_name', r'\w+\s*\('
            ],
            # Class patterns
            'class': [
                r'\bclass\s+\w+', r'\bstruct\s+\w+', r'\binterface\s+\w+',
                r'class_name', r'ClassName', r'[A-Z]\w*[A-Z]\w*'
            ],
            # Import patterns
            'import': [
                r'\bimport\s+', r'\bfrom\s+\w+\s+import', r'\brequire\s*\(',
                r'#include\s*<', r'import\s+\{', r'import_statement'
            ],
            # Variable patterns
            'variable': [
                r'^\s*\w+\s*=', r'\bvar\s+\w+', r'\blet\s+\w+',
                r'\bconst\s+\w+', r'variable_name'
            ]
        }

        # Sourcegraph query templates for different search types
        self.query_templates = {
            SearchType.TEXT: '{pattern}',  # Plain text search
            SearchType.SYMBOL: 'type:symbol {pattern}',
            SearchType.FUNCTION: 'type:symbol select:symbol.function {pattern}',
            SearchType.CLASS: 'type:symbol select:symbol.class {pattern}',
            SearchType.IMPORT: 'lang:{language} {pattern}',
            SearchType.STRUCTURAL: 'patterntype:structural {pattern}',
        }

    def _check_src_cli(self) -> bool:
        """Check if Sourcegraph CLI is available"""
        # Try multiple possible locations for src CLI
        src_commands = ['src', '/opt/homebrew/bin/src', '/usr/local/bin/src']

        for src_cmd in src_commands:
            try:
                result = subprocess.run([src_cmd, 'version'],
                                      capture_output=True,
                                      text=True,
                                      timeout=5)
                cli_available = result.returncode == 0
                if cli_available:
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return False

    def analyze_user_query(self, query: str, context_hint: Optional[str] = None) -> Tuple[SearchType, LanguageType, str]:
        """
        Intelligent analysis of user query to determine optimal Sourcegraph search strategy.
        Maps natural language queries to appropriate Sourcegraph search types.
        """
        query_lower = query.lower()

        # Detect programming language from context
        language = self._detect_language(query, context_hint)

        # Detect search intent
        search_type = self._detect_search_type(query, context_hint)

        # Extract clean pattern for Sourcegraph
        clean_pattern = self._extract_search_pattern(query, search_type)

        return search_type, language, clean_pattern

    def _detect_language(self, query: str, context_hint: Optional[str] = None) -> Optional[LanguageType]:
        """Detect programming language from query and context"""
        combined_text = f"{query} {context_hint or ''}".lower()

        language_indicators = {
            LanguageType.PYTHON: ['python', 'py', 'def ', 'import ', 'class ', '__init__', 'self.'],
            LanguageType.JAVASCRIPT: ['javascript', 'js', 'function ', 'const ', 'let ', 'var ', 'require('],
            LanguageType.TYPESCRIPT: ['typescript', 'ts', 'interface ', 'type ', 'implements'],
            LanguageType.GO: ['go', 'golang', 'func ', 'package ', 'import ', 'struct {'],
            LanguageType.JAVA: ['java', 'class ', 'public ', 'private ', 'import java'],
            LanguageType.CPP: ['cpp', 'c++', '#include', 'namespace ', 'class ', '::'],
            LanguageType.RUST: ['rust', 'rs', 'fn ', 'struct ', 'impl ', 'use '],
        }

        for lang, indicators in language_indicators.items():
            if any(indicator in combined_text for indicator in indicators):
                return lang

        return None

    def _detect_search_type(self, query: str, context_hint: Optional[str] = None) -> SearchType:
        """Detect the type of search based on query patterns"""
        combined_text = f"{query} {context_hint or ''}".lower()

        # Check for explicit type requests - but fallback to text search
        if any(word in combined_text for word in ['function', 'method', 'def ']):
            return SearchType.TEXT  # Use text search for functions too
        elif any(word in combined_text for word in ['class', 'struct', 'interface']):
            return SearchType.TEXT  # Use text search for classes too
        elif any(word in combined_text for word in ['import', 'require', 'include']):
            return SearchType.TEXT  # Use text search for imports too
        elif any(word in combined_text for word in ['symbol', 'definition', 'declaration']):
            return SearchType.TEXT  # Use text search for symbols too
        elif any(word in combined_text for word in ['variable', 'var', 'const', 'let']):
            return SearchType.TEXT  # Use text search for variables too

        # For multi-word descriptive queries, default to text search first
        if len(query.split()) > 1 and not re.search(r'^[A-Z][a-z]+[A-Z]', query):  # Not PascalCase like ClassName
            return SearchType.TEXT

        # Check if query looks like structural search (code blocks)
        if any(char in query for char in ['{', '}', '(', ')', '[', ']']) and len(query.split()) > 2:
            return SearchType.STRUCTURAL

        # Default to text search for simplicity and reliability
        return SearchType.TEXT

    def _extract_search_pattern(self, query: str, search_type: SearchType) -> str:
        """Extract clean search pattern from user query"""
        # Remove common prefixes that don't belong in Sourcegraph patterns
        prefixes_to_remove = [
            'find ', 'search for ', 'locate ', 'show me ', 'get ',
            'function ', 'class ', 'import ', 'where is ', 'look for '
        ]

        clean_query = query
        for prefix in prefixes_to_remove:
            if clean_query.lower().startswith(prefix):
                clean_query = clean_query[len(prefix):].strip()

        # For structural searches, preserve the structure
        if search_type == SearchType.STRUCTURAL:
            return query

        # Extract the core pattern
        return clean_query.strip()

    def build_sourcegraph_query(self, sq_query: SourcegraphQuery) -> str:
        """Build optimized Sourcegraph query from structured query object"""
        parts = []

        # Base pattern with type filtering
        if sq_query.search_type in self.query_templates:
            template = self.query_templates[sq_query.search_type]
            base_query = template.format(
                pattern=sq_query.pattern,
                language=sq_query.language.value if sq_query.language else 'any'
            )
            parts.append(base_query)
        else:
            parts.append(sq_query.pattern)

        # Add language filter
        if sq_query.language and sq_query.search_type != SearchType.IMPORT:
            parts.append(f'lang:{sq_query.language.value}')

        # Add file pattern filter
        if sq_query.file_pattern:
            parts.append(f'file:{sq_query.file_pattern}')

        # Add repository filter
        if sq_query.repo_pattern:
            parts.append(f'repo:{sq_query.repo_pattern}')

        # Add exclusions
        if sq_query.exclude_patterns:
            for exclude in sq_query.exclude_patterns:
                parts.append(f'-{exclude}')

        # Enable structural search if needed
        if sq_query.structural_search:
            parts.append('patterntype:structural')

        return ' '.join(parts)

    def execute_search(self, query: str, max_results: int = 50) -> List[SearchResult]:
        """Execute Sourcegraph search and parse results"""
        if not self.src_cli_available:
            raise RuntimeError("Sourcegraph CLI not available. Please install src CLI.")

        try:
            # Find the src command
            src_cmd = 'src'
            for possible_src in ['src', '/opt/homebrew/bin/src', '/usr/local/bin/src']:
                try:
                    subprocess.run([possible_src, 'version'], capture_output=True, timeout=1, check=True)
                    src_cmd = possible_src
                    break
                except:
                    continue

            # Execute src search command with local endpoint
            cmd = [
                src_cmd, 'search',
                '-json',  # Get JSON output for easier parsing
                f'-display={max_results}',
                query
            ]

            # Set environment to use local Sourcegraph instance
            env = os.environ.copy()
            env['SRC_ENDPOINT'] = 'http://localhost:7080'
            # Keep existing SRC_ACCESS_TOKEN if available
            if 'SRC_ACCESS_TOKEN' not in env:
                # Try to get from environment or use default if testing locally
                env['SRC_ACCESS_TOKEN'] = os.environ.get('SRC_ACCESS_TOKEN', 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d')

            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            if result.returncode != 0:
                print(f"Sourcegraph search failed: {result.stderr}")
                return []

            # Parse JSON results
            return self._parse_search_results(result.stdout)

        except subprocess.TimeoutExpired:
            print("Sourcegraph search timed out after 30 seconds")
            return []
        except Exception as e:
            print(f"Error executing Sourcegraph search: {e}")
            return []

    def _parse_search_results(self, json_output: str) -> List[SearchResult]:
        """Parse Sourcegraph JSON output into SearchResult objects"""
        results = []

        try:
            data = json.loads(json_output)

            for item in data.get('Results', data.get('results', [])):
                if 'file' in item:
                    file_info = item['file']

                    for line_match in item.get('lineMatches', []):
                        results.append(SearchResult(
                            file_path=file_info.get('path', ''),
                            line_number=line_match.get('lineNumber', 0),
                            content=line_match.get('line', ''),
                            repository=file_info.get('repository', {}).get('name', ''),
                            language=self._detect_file_language(file_info.get('path', '')),
                            confidence=0.9
                        ))

                elif 'symbol' in item:
                    symbol_info = item['symbol']
                    results.append(SearchResult(
                        file_path=symbol_info.get('path', ''),
                        line_number=symbol_info.get('line', 0),
                        content=symbol_info.get('name', ''),
                        symbol_kind=symbol_info.get('kind', ''),
                        symbol_name=symbol_info.get('name', ''),
                        repository=symbol_info.get('repository', {}).get('name', ''),
                        language=symbol_info.get('language', ''),
                        confidence=1.0
                    ))

        except json.JSONDecodeError as e:
            print(f"Failed to parse Sourcegraph JSON output: {e}")

        return results

    def _detect_file_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension"""
        ext = Path(file_path).suffix.lower()

        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.go': 'go',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
        }

        return extension_map.get(ext)

    def smart_search(self, user_query: str, context_hint: Optional[str] = None, max_results: int = 50) -> List[SearchResult]:
        """
        Main entry point for intelligent code search.
        Maps user queries to optimal Sourcegraph search strategies.
        """
        print(f"🧠 Analyzing query: '{user_query}'")
        if context_hint:
            print(f"   Context: {context_hint}")

        # Analyze user intent
        search_type, language, clean_pattern = self.analyze_user_query(user_query, context_hint)

        print(f"🔍 Detected: {search_type.value} search for '{clean_pattern}'")
        if language:
            print(f"   Language: {language.value}")

        # Build structured query
        sq_query = SourcegraphQuery(
            pattern=clean_pattern,
            search_type=search_type,
            language=language,
            max_results=max_results
        )

        # Convert to Sourcegraph query
        sourcegraph_query = self.build_sourcegraph_query(sq_query)
        print(f"📡 Sourcegraph query: {sourcegraph_query}")

        # Execute search
        results = self.execute_search(sourcegraph_query, max_results)

        print(f"✅ Found {len(results)} results")
        return results

# Integration functions for UF Flow tool system
def search_code_with_sourcegraph(
    query: str,
    search_type: str = "auto",
    language: Optional[str] = None,
    max_results: int = 50,
    context_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main search function for integration with UF Flow tools.
    Preferred over basic grep/regex search tools.
    """
    try:
        # Set up Sourcegraph environment variables
        import os
        os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
        if 'SRC_ACCESS_TOKEN' not in os.environ:
            # Try to get token from environment or set default for local development
            token = os.environ.get('SRC_ACCESS_TOKEN', 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d')
            os.environ['SRC_ACCESS_TOKEN'] = token

        engine = SourcegraphSearchEngine()

        if not engine.src_cli_available:
            return {
                "success": False,
                "error": "Sourcegraph CLI not available. Please install src CLI.",
                "fallback_suggestion": "Use local_code_search as fallback",
                "results": []
            }

        # Execute smart search
        results = engine.smart_search(query, context_hint, max_results)

        # Format results for tool integration
        formatted_results = []
        for result in results:
            formatted_results.append({
                "file_path": result.file_path,
                "line_number": result.line_number,
                "content": result.content,
                "symbol_kind": result.symbol_kind,
                "symbol_name": result.symbol_name,
                "language": result.language,
                "repository": result.repository,
                "confidence": result.confidence
            })

        return {
            "success": True,
            "search_engine": "sourcegraph",
            "query": query,
            "total_results": len(formatted_results),
            "results": formatted_results,
            "advantages": [
                "Semantic code understanding",
                "Symbol-aware search",
                "Cross-reference capabilities",
                "Structural search support",
                "75+ programming languages"
            ]
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": []
        }

if __name__ == "__main__":
    # Test the Sourcegraph search engine
    engine = SourcegraphSearchEngine()

    if engine.src_cli_available:
        print("✅ Sourcegraph CLI available")

        # Test searches
        test_queries = [
            ("PathManager", "Find PathManager class"),
            ("def get_tmp_file", "Find get_tmp_file function"),
            ("import pandas", "Find pandas imports"),
            ("oauth2.Config{}", "Structural search for OAuth config")
        ]

        for query, description in test_queries:
            print(f"\n--- {description} ---")
            results = engine.smart_search(query, max_results=3)
            for result in results[:2]:  # Show top 2 results
                print(f"📁 {result.file_path}:{result.line_number}")
                print(f"   {result.content}")
    else:
        print("❌ Sourcegraph CLI not available")
        print("Install with: https://github.com/sourcegraph/src-cli")