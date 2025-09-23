# tools/robust_search.py

import os
import re
import subprocess
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

@dataclass
class RobustSearchResult:
    """Enhanced search result with better error handling"""
    file_path: str
    line_number: Optional[int] = None
    match_content: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence: float = 1.0
    search_method: str = "exact"

class RobustSearchEngine:
    """
    Super robust search engine that handles edge cases and prevents agent loops.
    """

    def __init__(self, workspace_root: str = None):
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()
        self.default_exclusions = [
            '.git', '__pycache__', 'node_modules', '.vscode', '.idea',
            'build', 'dist', '.env', 'venv', '*.pyc', '*.log',
            '.DS_Store', 'Thumbs.db', '.pytest_cache', '.mypy_cache'
        ]

    def _escape_pattern_for_regex(self, pattern: str) -> str:
        """
        Safely escape special regex characters to prevent parsing errors.
        This was the root cause of the agent getting lost.
        """
        # Common special characters that cause regex issues
        special_chars = r'()[]{}.*+?^$|\\'
        escaped_pattern = pattern

        for char in special_chars:
            escaped_pattern = escaped_pattern.replace(char, f'\\{char}')

        return escaped_pattern

    def _has_ripgrep(self) -> bool:
        """Check if ripgrep is available with timeout to prevent hanging"""
        try:
            result = subprocess.run(['rg', '--version'],
                                  capture_output=True,
                                  check=True,
                                  timeout=5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def search_for_function_calls(self, function_name: str,
                                 include_definition: bool = True,
                                 show_context: bool = True) -> List[RobustSearchResult]:
        """
        Robustly search for function calls with parameter analysis.
        This specifically addresses the original goal: find LLM call variations.
        """
        results = []

        # Multiple search patterns to catch different call styles
        patterns = [
            f"{function_name}\\(",  # Standard calls like call_llm(
            f"\\.{function_name}\\(",  # Method calls like client.call_llm(
            f"def {function_name}\\(",  # Function definitions
            f"async def {function_name}\\(",  # Async function definitions
        ]

        if not include_definition:
            # Remove definition patterns if only looking for calls
            patterns = patterns[:2]

        for i, pattern in enumerate(patterns):
            pattern_results = self._search_with_pattern(
                pattern,
                search_method=f"function_call_{i}",
                context_lines=3 if show_context else 0
            )
            results.extend(pattern_results)

        # Deduplicate by file path and line number
        seen = set()
        unique_results = []
        for result in results:
            key = (result.file_path, result.line_number)
            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        # Sort by file path then line number
        unique_results.sort(key=lambda r: (r.file_path, r.line_number or 0))

        return unique_results

    def _search_with_pattern(self, pattern: str,
                           file_types: List[str] = None,
                           search_method: str = "pattern",
                           context_lines: int = 0) -> List[RobustSearchResult]:
        """
        Core search method with robust error handling.
        """
        results = []

        try:
            if self._has_ripgrep():
                cmd = self._build_ripgrep_command(pattern, file_types, context_lines)
            else:
                cmd = self._build_grep_command(pattern, file_types, context_lines)

            # Execute with timeout to prevent hanging
            result = subprocess.run(cmd,
                                  capture_output=True,
                                  text=True,
                                  check=False,
                                  timeout=30,  # 30 second timeout
                                  cwd=str(self.workspace_root))

            if result.returncode == 0:
                results = self._parse_search_output(result.stdout, search_method, context_lines)
            elif result.returncode == 1:
                # No matches found (normal)
                pass
            else:
                print(f"⚠️  Search command failed: {' '.join(cmd)}")
                print(f"   Error: {result.stderr}")

        except subprocess.TimeoutExpired:
            print(f"⚠️  Search timed out for pattern: {pattern}")
        except Exception as e:
            print(f"⚠️  Search error: {e}")

        return results

    def _build_ripgrep_command(self, pattern: str,
                              file_types: List[str] = None,
                              context_lines: int = 0) -> List[str]:
        """Build robust ripgrep command"""
        cmd = ['rg']

        # Add pattern (already escaped)
        cmd.append(pattern)

        # Add context if requested
        if context_lines > 0:
            cmd.extend(['-C', str(context_lines)])

        # Case insensitive by default for broader matching
        cmd.append('-i')

        # Add file type filters
        if file_types:
            for file_type in file_types:
                if not file_type.startswith('.'):
                    file_type = '.' + file_type
                cmd.extend(['--glob', f'*{file_type}'])

        # Add exclusions
        for exclusion in self.default_exclusions:
            cmd.extend(['--glob', f'!{exclusion}'])

        # Output format
        cmd.extend(['--with-filename', '--line-number'])

        # Search root
        cmd.append(str(self.workspace_root))

        return cmd

    def _build_grep_command(self, pattern: str,
                           file_types: List[str] = None,
                           context_lines: int = 0) -> List[str]:
        """Fallback grep command"""
        cmd = ['grep', '-r', '-n', '-i']  # recursive, line numbers, case insensitive

        # Add context
        if context_lines > 0:
            cmd.extend(['-C', str(context_lines)])

        # Add file type includes
        if file_types:
            for file_type in file_types:
                if not file_type.startswith('.'):
                    file_type = '.' + file_type
                cmd.append(f'--include=*{file_type}')

        # Add exclusions
        for exclusion in self.default_exclusions:
            if '.' not in exclusion:
                cmd.append(f'--exclude-dir={exclusion}')
            else:
                cmd.append(f'--exclude={exclusion}')

        # Add pattern and search root
        cmd.extend([pattern, str(self.workspace_root)])

        return cmd

    def _parse_search_output(self, output: str,
                           search_method: str,
                           context_lines: int = 0) -> List[RobustSearchResult]:
        """Parse search output into structured results"""
        results = []
        lines = output.strip().split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Parse ripgrep/grep output: filename:line_number:content
            # Handle filenames with colons by splitting on rightmost colons
            if ':' in line:
                # Find the last two colons (for line number and content)
                parts = line.rsplit(':', 2)
                if len(parts) >= 2:
                    file_path = parts[0]
                    line_content = parts[-1]

                    # Try to parse line number
                    line_number = None
                    if len(parts) == 3:
                        try:
                            line_number = int(parts[1])
                        except ValueError:
                            # Line number parsing failed, adjust
                            file_path = ':'.join(parts[:2])
                            line_content = parts[2]

                    # Convert to absolute path
                    if not os.path.isabs(file_path):
                        file_path = str(self.workspace_root / file_path)

                    # Collect context if available
                    context_before = None
                    context_after = None

                    if context_lines > 0:
                        # Simple context extraction (can be improved)
                        context_before = ""
                        context_after = ""
                        for j in range(1, min(context_lines + 1, i + 1)):
                            if i - j >= 0:
                                context_before = lines[i - j] + "\n" + context_before
                        for j in range(1, min(context_lines + 1, len(lines) - i)):
                            if i + j < len(lines):
                                context_after += lines[i + j] + "\n"

                    results.append(RobustSearchResult(
                        file_path=file_path,
                        line_number=line_number,
                        match_content=line_content.strip(),
                        context_before=context_before.strip() if context_before else None,
                        context_after=context_after.strip() if context_after else None,
                        search_method=search_method
                    ))

            i += 1

        return results

    def analyze_function_parameters(self, function_call_results: List[RobustSearchResult]) -> Dict[str, Any]:
        """
        Analyze function call patterns to extract parameter variations.
        This addresses the original goal of understanding LLM call parameters.
        """
        analysis = {
            "total_calls": len(function_call_results),
            "files_with_calls": set(),
            "call_patterns": {},
            "unique_parameters": set(),
            "parameter_combinations": []
        }

        for result in function_call_results:
            analysis["files_with_calls"].add(result.file_path)

            if result.match_content:
                # Extract function call pattern
                match_content = result.match_content.strip()

                # Simple parameter extraction (can be improved with AST parsing)
                if '(' in match_content and ')' in match_content:
                    # Extract content between parentheses
                    try:
                        start = match_content.find('(')
                        end = match_content.rfind(')')
                        params = match_content[start+1:end]

                        if params.strip():
                            analysis["unique_parameters"].add(params.strip())
                            analysis["parameter_combinations"].append({
                                "file": result.file_path,
                                "line": result.line_number,
                                "parameters": params.strip(),
                                "full_call": match_content
                            })
                    except Exception:
                        # Parameter parsing failed, skip
                        pass

                # Track call patterns
                pattern_key = match_content.split('(')[0].strip()
                if pattern_key not in analysis["call_patterns"]:
                    analysis["call_patterns"][pattern_key] = 0
                analysis["call_patterns"][pattern_key] += 1

        analysis["files_with_calls"] = list(analysis["files_with_calls"])
        analysis["unique_parameters"] = list(analysis["unique_parameters"])

        return analysis

def main():
    """
    Demonstration of robust search functionality
    """
    print("🔍 Robust Search Engine Demo")

    engine = RobustSearchEngine()

    # Search for LLM function calls (the original failing case)
    print("\n1. Searching for LLM function calls...")
    llm_calls = engine.search_for_function_calls("call_llm")

    print(f"Found {len(llm_calls)} LLM calls:")
    for call in llm_calls[:5]:  # Show first 5
        print(f"  📁 {call.file_path}:{call.line_number}")
        print(f"     {call.match_content}")

    # Analyze parameters
    print("\n2. Analyzing LLM call parameters...")
    analysis = engine.analyze_function_parameters(llm_calls)

    print(f"Total calls: {analysis['total_calls']}")
    print(f"Files with calls: {len(analysis['files_with_calls'])}")
    print(f"Unique parameter patterns: {len(analysis['unique_parameters'])}")

    print("\nParameter variations found:")
    for i, params in enumerate(analysis['unique_parameters'][:3]):  # Show first 3
        print(f"  {i+1}. {params}")

if __name__ == "__main__":
    main()