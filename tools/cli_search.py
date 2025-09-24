#!/usr/bin/env python3
"""
Command-line interface for code search.
Interactive search tool for the terminal.
"""

import sys
import os
from pathlib import Path

# Add the tools directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from local_code_search import search_code

def print_results(results, max_display=10):
    """Print search results in a formatted way."""
    if not results.get('success'):
        print(f"❌ Error: {results.get('error', 'Unknown error')}")
        return
    
    total = results.get('total_results', 0)
    result_list = results.get('results', [])
    
    print(f"\n🔍 Found {total} results")
    print("=" * 60)
    
    for i, result in enumerate(result_list[:max_display]):
        print(f"\n{i+1}. 📁 {result['file_path']}:{result['line_number']}")
        print(f"   {result['content']}")
        
        # Show context if available
        if result.get('context_before'):
            for line in result['context_before']:
                print(f"   {line}")
        
        if result.get('context_after'):
            for line in result['context_after']:
                print(f"   {line}")
    
    if total > max_display:
        print(f"\n... and {total - max_display} more results")

def interactive_search():
    """Interactive search session."""
    print("🔍 UF Flow Code Search - Interactive Mode")
    print("=" * 50)
    print("Commands:")
    print("  /help     - Show help")
    print("  /quit     - Exit")
    print("  /types    - Show search types")
    print()
    
    while True:
        try:
            query = input("🔎 Search: ").strip()
            
            if not query:
                continue
            
            if query.startswith('/'):
                if query == '/quit':
                    print("👋 Goodbye!")
                    break
                elif query == '/help':
                    print("\nHelp:")
                    print("  Enter a search query to search the codebase")
                    print("  Use search types: text, function, class, import, symbol")
                    print("  Examples:")
                    print("    PathManager                    # Text search")
                    print("    function:get_tmp_file          # Function search")
                    print("    class:PathManager              # Class search")
                    print("    import:pandas                  # Import search")
                    print("    symbol:PathManager             # Symbol usage")
                    continue
                elif query == '/types':
                    print("\nSearch Types:")
                    print("  text     - Search for any text in files")
                    print("  function - Find function definitions")
                    print("  class    - Find class definitions")
                    print("  import   - Find import statements")
                    print("  symbol   - Find symbol usage")
                    continue
            
            # Parse search type if specified
            search_type = "text"
            if ':' in query:
                parts = query.split(':', 1)
                if parts[0] in ['text', 'function', 'class', 'import', 'symbol']:
                    search_type = parts[0]
                    query = parts[1]
            
            # Perform search
            print(f"\n🔍 Searching for '{query}' ({search_type})...")
            results = search_code(query, search_type, "*.py", 20)
            print_results(results)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except EOFError:
            print("\n👋 Goodbye!")
            break

def main():
    """Main function."""
    if len(sys.argv) > 1:
        # Command line mode
        query = sys.argv[1]
        search_type = "text"
        file_pattern = "*.py"
        
        if len(sys.argv) > 2:
            search_type = sys.argv[2]
        if len(sys.argv) > 3:
            file_pattern = sys.argv[3]
        
        print(f"🔍 Searching for '{query}' ({search_type})...")
        results = search_code(query, search_type, file_pattern, 50)
        print_results(results, 20)
    else:
        # Interactive mode
        interactive_search()

if __name__ == "__main__":
    main()
