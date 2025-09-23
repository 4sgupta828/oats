# tools/smart_search.py

import os
import subprocess
from typing import List, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

class SearchScope(Enum):
    """Defines the scope of search operations"""
    EXACT_MATCH = "exact"
    FUZZY_PATTERN = "fuzzy"
    RELATED_TYPES = "related"
    BROAD_SEARCH = "broad"

@dataclass
class SearchResult:
    """Represents a search result with metadata"""
    file_path: str
    match_line: Optional[int] = None
    match_content: Optional[str] = None
    confidence: float = 1.0
    search_scope: SearchScope = SearchScope.EXACT_MATCH

@dataclass
class SearchQuery:
    """Encapsulates a search query with all parameters"""
    pattern: str
    file_types: List[str]
    exclude_patterns: List[str]
    directories: List[str]
    case_sensitive: bool = False
    whole_words: bool = False
    multiline: bool = False

@dataclass
class QueryAnalysis:
    """Results from LLM query analysis"""
    search_type: str  # "filename", "content", "extension", "mixed"
    likely_filename_patterns: List[str]
    likely_content_patterns: List[str]
    likely_file_types: List[str]
    confidence: float
    reasoning: str

class SmartSearchEngine:
    """
    Efficient search engine that uses ripgrep/grep for pattern-first searches
    instead of file-by-file reading.
    """

    def __init__(self, workspace_root: str = None):
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()

        # Common file type mappings for progressive search
        self.file_type_groups = {
            'data': ['csv', 'tsv', 'json', 'xml', 'yaml', 'yml'],
            'text': ['txt', 'md', 'rst', 'log'],
            'spreadsheet': ['xlsx', 'xls', 'ods'],
            'config': ['ini', 'cfg', 'conf', 'toml'],
            'code': ['py', 'js', 'ts', 'java', 'cpp', 'c', 'h'],
            'web': ['html', 'css', 'scss', 'less'],
        }

        # Pattern variations for fuzzy matching
        self.pattern_variations = {
            'gpa': ['gpa', 'grade.*point', 'academic.*score', 'cumulative.*average'],
            'email': ['email', 'e-mail', 'mail', '@'],
            'phone': ['phone', 'tel', 'mobile', 'contact'],
            'address': ['address', 'addr', 'location', 'street'],
        }

        # Standard exclusion patterns (similar to .gitignore)
        self.default_exclusions = [
            '.git', '__pycache__', 'node_modules', '.vscode', '.idea',
            'build', 'dist', '.env', 'venv', '*.pyc', '*.log',
            '.DS_Store', 'Thumbs.db', '.pytest_cache', '.mypy_cache'
        ]

    def _analyze_query_with_llm(self, query_text: str, context_hint: str = None) -> QueryAnalysis:
        """
        Use LLM to intelligently analyze the search query and determine the best search strategy.
        """
        try:
            from tools.llm_integration import call_llm

            analysis_prompt = f"""Analyze this search query to determine the optimal search strategy.

QUERY: "{query_text}"
CONTEXT HINT: {context_hint or "None provided"}

Determine:
1. Is this primarily a FILENAME search, CONTENT search, EXTENSION search, or MIXED?
2. What filename patterns should be tried?
3. What content patterns should be searched for?
4. What file types are most likely relevant?

Examples:
- "student" + context "csv data" → FILENAME search for files with "student" in name, type csv
- "api_key" → CONTENT search for "api_key" in configuration files
- "error logs" → CONTENT search for "error" in .log files
- "config.json" → FILENAME search for "config" files with .json extension

Respond in this exact JSON format:
{{
    "search_type": "filename|content|extension|mixed",
    "likely_filename_patterns": ["pattern1", "pattern2"],
    "likely_content_patterns": ["pattern1", "pattern2"],
    "likely_file_types": ["ext1", "ext2"],
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of decision"
}}"""

            response = call_llm(analysis_prompt, max_tokens=500)

            # Parse JSON response
            import json
            try:
                analysis_data = json.loads(response.strip())
                return QueryAnalysis(
                    search_type=analysis_data.get("search_type", "mixed"),
                    likely_filename_patterns=analysis_data.get("likely_filename_patterns", []),
                    likely_content_patterns=analysis_data.get("likely_content_patterns", []),
                    likely_file_types=analysis_data.get("likely_file_types", []),
                    confidence=analysis_data.get("confidence", 0.5),
                    reasoning=analysis_data.get("reasoning", "LLM analysis completed")
                )
            except json.JSONDecodeError as e:
                print(f"⚠️  LLM response parsing failed: {e}")
                return self._fallback_query_analysis(query_text, context_hint)

        except Exception as e:
            print(f"⚠️  LLM query analysis failed: {e}")
            return self._fallback_query_analysis(query_text, context_hint)

    def _fallback_query_analysis(self, query_text: str, context_hint: str = None) -> QueryAnalysis:
        """
        Fallback heuristic analysis if LLM is unavailable.
        """
        # Existing heuristic logic as fallback
        filename_indicators = ['student', 'config', 'log', 'data', 'test', 'main', 'index']

        if query_text.lower() in filename_indicators:
            search_type = "filename"
            filename_patterns = [query_text]
            content_patterns = []
        elif any(char in query_text for char in ['=', ':', '"', "'", '<', '>', '@']):
            search_type = "content"
            filename_patterns = []
            content_patterns = [query_text]
        else:
            search_type = "mixed"
            filename_patterns = [query_text]
            content_patterns = [query_text]

        # Infer file types from context
        file_types = []
        if context_hint:
            context_lower = context_hint.lower()
            if any(word in context_lower for word in ['csv', 'spreadsheet', 'data']):
                file_types.extend(['csv', 'tsv'])
            elif any(word in context_lower for word in ['json', 'api']):
                file_types.extend(['json'])
            elif any(word in context_lower for word in ['config', 'setting']):
                file_types.extend(['ini', 'cfg', 'conf', 'toml', 'yaml', 'yml'])

        return QueryAnalysis(
            search_type=search_type,
            likely_filename_patterns=filename_patterns,
            likely_content_patterns=content_patterns,
            likely_file_types=file_types,
            confidence=0.7,
            reasoning="Fallback heuristic analysis"
        )

    def _has_ripgrep(self) -> bool:
        """Check if ripgrep (rg) is available"""
        try:
            subprocess.run(['rg', '--version'],
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _build_ripgrep_command(self, query: SearchQuery) -> List[str]:
        """Build ripgrep command with appropriate flags"""
        cmd = ['rg']

        # Add pattern first (required position)
        cmd.append(query.pattern)

        # Add case sensitivity
        if not query.case_sensitive:
            cmd.append('-i')

        if query.whole_words:
            cmd.append('-w')

        if query.multiline:
            cmd.extend(['-U', '--multiline-dotall'])

        # Add file type filters
        for file_type in query.file_types:
            if not file_type.startswith('.'):
                file_type = '.' + file_type
            cmd.extend(['--glob', f'*{file_type}'])

        # Add exclusions
        all_exclusions = self.default_exclusions + query.exclude_patterns
        for exclusion in all_exclusions:
            cmd.extend(['--glob', f'!{exclusion}'])

        # Output format - show filename and line numbers
        cmd.extend(['--with-filename', '--line-number'])

        # Search directories
        if query.directories:
            cmd.extend(query.directories)
        else:
            cmd.append(str(self.workspace_root))

        return cmd

    def _build_grep_command(self, query: SearchQuery) -> List[str]:
        """Fallback to standard grep if ripgrep unavailable"""
        cmd = ['grep', '-r', '-n']  # recursive, line numbers

        if not query.case_sensitive:
            cmd.append('-i')

        if query.whole_words:
            cmd.append('-w')

        # Build include pattern for file types
        if query.file_types:
            include_patterns = []
            for ft in query.file_types:
                if not ft.startswith('.'):
                    ft = '.' + ft
                include_patterns.append(f'*{ft}')
            cmd.extend(['--include=' + pattern for pattern in include_patterns])

        # Build exclude patterns
        all_exclusions = self.default_exclusions + query.exclude_patterns
        for exclusion in all_exclusions:
            cmd.append(f'--exclude-dir={exclusion}' if '.' not in exclusion else f'--exclude={exclusion}')

        # Add pattern
        cmd.append(query.pattern)

        # Search directories
        if query.directories:
            cmd.extend(query.directories)
        else:
            cmd.append(str(self.workspace_root))

        return cmd

    def _execute_search_command(self, cmd: List[str]) -> List[SearchResult]:
        """Execute search command and parse results"""
        try:
            result = subprocess.run(cmd,
                                  capture_output=True,
                                  text=True,
                                  check=False,
                                  cwd=str(self.workspace_root))

            if result.returncode == 0:
                return self._parse_search_output(result.stdout)
            elif result.returncode == 1:
                # No matches found (normal for grep/rg)
                return []
            else:
                # Actual error
                print(f"Search command failed: {' '.join(cmd)}")
                print(f"Error: {result.stderr}")
                return []

        except Exception as e:
            print(f"Error executing search: {e}")
            return []

    def _parse_search_output(self, output: str) -> List[SearchResult]:
        """Parse grep/ripgrep output into SearchResult objects"""
        results = []

        for line in output.strip().split('\n'):
            if not line:
                continue

            # Parse format: filename:line_number:match_content
            parts = line.split(':', 2)
            if len(parts) >= 2:
                file_path = parts[0]
                try:
                    line_number = int(parts[1])
                    match_content = parts[2] if len(parts) > 2 else ""
                except ValueError:
                    # Sometimes filenames contain colons
                    file_path = ':'.join(parts[:-1])
                    match_content = parts[-1]
                    line_number = None

                # Convert to absolute path
                if not os.path.isabs(file_path):
                    file_path = str(self.workspace_root / file_path)

                results.append(SearchResult(
                    file_path=file_path,
                    match_line=line_number,
                    match_content=match_content.strip()
                ))

        return results

    def _get_pattern_variations(self, pattern: str) -> List[str]:
        """Get pattern variations for fuzzy matching"""
        pattern_lower = pattern.lower()

        # Check if we have predefined variations
        if pattern_lower in self.pattern_variations:
            return self.pattern_variations[pattern_lower]

        # Generate automatic variations
        variations = [pattern]

        # Add case variations
        variations.extend([
            pattern.upper(),
            pattern.capitalize(),
            pattern.lower()
        ])

        # Add underscore/dash variations
        if '_' in pattern:
            variations.append(pattern.replace('_', '-'))
            variations.append(pattern.replace('_', ' '))
        elif '-' in pattern:
            variations.append(pattern.replace('-', '_'))
            variations.append(pattern.replace('-', ' '))
        elif ' ' in pattern:
            variations.append(pattern.replace(' ', '_'))
            variations.append(pattern.replace(' ', '-'))

        # Add partial match patterns (for fuzzy search)
        if len(pattern) > 3:
            variations.append(f".*{pattern}.*")
            variations.append(f"{pattern}.*")
            variations.append(f".*{pattern}")

        return list(set(variations))  # Remove duplicates

    def _get_related_file_types(self, file_types: List[str]) -> List[str]:
        """Get related file types for progressive search"""
        related_types = set(file_types)

        for file_type in file_types:
            for group_name, group_types in self.file_type_groups.items():
                if file_type in group_types:
                    related_types.update(group_types)

        return list(related_types)

    def search_progressive(self, pattern: str, initial_file_types: List[str] = None) -> List[SearchResult]:
        """
        Progressive search that starts narrow and expands scope as needed.

        1. Exact match in target file types
        2. Fuzzy patterns in same file types
        3. Expand to related file types
        4. Broaden pattern variations
        """
        all_results = []

        # Stage 1: Exact match in target file types
        if initial_file_types:
            query = SearchQuery(
                pattern=pattern,
                file_types=initial_file_types,
                exclude_patterns=[],
                directories=[]
            )

            results = self.search_with_query(query)
            if results:
                for result in results:
                    result.search_scope = SearchScope.EXACT_MATCH
                    result.confidence = 1.0
                all_results.extend(results)
                print(f"✅ Found {len(results)} exact matches in {initial_file_types}")
                return all_results

        # Stage 2: Fuzzy patterns in same file types
        pattern_variations = self._get_pattern_variations(pattern)
        for variant_pattern in pattern_variations[1:]:  # Skip the first (exact) pattern
            query = SearchQuery(
                pattern=variant_pattern,
                file_types=initial_file_types or [],
                exclude_patterns=[],
                directories=[]
            )

            results = self.search_with_query(query)
            if results:
                for result in results:
                    result.search_scope = SearchScope.FUZZY_PATTERN
                    result.confidence = 0.8
                all_results.extend(results)
                print(f"✅ Found {len(results)} fuzzy matches with pattern '{variant_pattern}'")
                return all_results

        # Stage 3: Expand to related file types
        if initial_file_types:
            related_types = self._get_related_file_types(initial_file_types)
            if len(related_types) > len(initial_file_types):
                query = SearchQuery(
                    pattern=pattern,
                    file_types=related_types,
                    exclude_patterns=[],
                    directories=[]
                )

                results = self.search_with_query(query)
                if results:
                    for result in results:
                        result.search_scope = SearchScope.RELATED_TYPES
                        result.confidence = 0.6
                    all_results.extend(results)
                    print(f"✅ Found {len(results)} matches in related file types {related_types}")
                    return all_results

        # Stage 4: Broad search across all files
        query = SearchQuery(
            pattern=pattern,
            file_types=[],  # Search all file types
            exclude_patterns=[],
            directories=[]
        )

        results = self.search_with_query(query)
        if results:
            for result in results:
                result.search_scope = SearchScope.BROAD_SEARCH
                result.confidence = 0.4
            all_results.extend(results)
            print(f"✅ Found {len(results)} matches in broad search")

        return all_results

    def search_with_query(self, query: SearchQuery) -> List[SearchResult]:
        """Execute a search with the given query"""
        # Choose search tool (ripgrep preferred)
        if self._has_ripgrep():
            cmd = self._build_ripgrep_command(query)
        else:
            cmd = self._build_grep_command(query)

        # Execute search
        return self._execute_search_command(cmd)

    def search_files_by_pattern(self, pattern: str, file_types: List[str] = None) -> List[SearchResult]:
        """
        Main entry point for efficient file search.

        Args:
            pattern: The search pattern (can be regex)
            file_types: List of file extensions (without dots)

        Returns:
            List of SearchResult objects sorted by confidence
        """
        results = self.search_progressive(pattern, file_types)

        # Sort by confidence (highest first)
        results.sort(key=lambda r: r.confidence, reverse=True)

        return results

    def find_files_by_name(self, filename_pattern: str) -> List[str]:
        """
        Find files by filename pattern using efficient tools.
        Much faster than os.walk for name-based searches.
        """
        try:
            if self._has_ripgrep():
                # Use ripgrep for filename search
                cmd = ['rg', '--files', '--glob', f'*{filename_pattern}*', str(self.workspace_root)]
            else:
                # Fallback to find command
                cmd = ['find', str(self.workspace_root), '-name', f'*{filename_pattern}*', '-type', 'f']

            # Add standard exclusions
            for exclusion in self.default_exclusions:
                if self._has_ripgrep():
                    cmd.extend(['--glob', f'!{exclusion}'])

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                files = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                return files
            else:
                return []

        except Exception as e:
            print(f"Error in filename search: {e}")
            return []

    def smart_search(self, query_text: str, context_hint: str = None) -> List[SearchResult]:
        """
        LLM-powered intelligent search that analyzes queries to determine optimal search strategy.

        Args:
            query_text: What to search for
            context_hint: Optional hint about what kind of data (e.g., "csv data", "config file")

        Returns:
            List of SearchResult objects
        """
        # Use LLM to analyze the query
        analysis = self._analyze_query_with_llm(query_text, context_hint)

        print(f"🧠 LLM Analysis: {analysis.search_type} search (confidence: {analysis.confidence:.2f})")
        print(f"   Reasoning: {analysis.reasoning}")

        results = []

        # Execute search strategy based on LLM analysis
        if analysis.search_type == "filename" or analysis.search_type == "extension":
            # Primarily filename-based search
            for pattern in analysis.likely_filename_patterns:
                filename_results = self.find_files_by_name(pattern)

                # Filter by file types if specified
                if analysis.likely_file_types:
                    filtered_files = []
                    for file_path in filename_results:
                        file_ext = os.path.splitext(file_path)[1][1:].lower()
                        if file_ext in analysis.likely_file_types:
                            filtered_files.append(file_path)
                    filename_results = filtered_files

                # Convert to SearchResult format
                for file_path in filename_results:
                    results.append(SearchResult(
                        file_path=file_path,
                        confidence=analysis.confidence,
                        search_scope=SearchScope.EXACT_MATCH
                    ))

                if results:
                    print(f"✅ Found {len(results)} files by filename pattern '{pattern}'")
                    return results

        elif analysis.search_type == "content":
            # Primarily content-based search
            for pattern in analysis.likely_content_patterns:
                content_results = self.search_progressive(pattern, analysis.likely_file_types)
                results.extend(content_results)

                if results:
                    print(f"✅ Found {len(results)} matches by content pattern '{pattern}'")
                    return results

        elif analysis.search_type == "mixed":
            # Try filename first, then content
            for pattern in analysis.likely_filename_patterns:
                filename_results = self.find_files_by_name(pattern)

                # Filter by file types if specified
                if analysis.likely_file_types:
                    filtered_files = []
                    for file_path in filename_results:
                        file_ext = os.path.splitext(file_path)[1][1:].lower()
                        if file_ext in analysis.likely_file_types:
                            filtered_files.append(file_path)
                    filename_results = filtered_files

                # Convert to SearchResult format
                for file_path in filename_results:
                    results.append(SearchResult(
                        file_path=file_path,
                        confidence=analysis.confidence,
                        search_scope=SearchScope.EXACT_MATCH
                    ))

                if results:
                    print(f"✅ Found {len(results)} files by filename pattern '{pattern}'")
                    return results

            # If filename search failed, try content search
            for pattern in analysis.likely_content_patterns:
                content_results = self.search_progressive(pattern, analysis.likely_file_types)
                results.extend(content_results)

                if results:
                    print(f"✅ Found {len(results)} matches by content pattern '{pattern}'")
                    return results

        # Fallback to original progressive search if nothing found
        if not results:
            print("🔄 Falling back to progressive search...")
            return self.search_progressive(query_text, analysis.likely_file_types)