#!/usr/bin/env python3
"""
Test script for Sourcegraph search functionality.
Run this to verify that Sourcegraph integration is working correctly.
"""

import os
import sys

# Set up environment
os.environ['SRC_ENDPOINT'] = 'http://localhost:7080'
os.environ['SRC_ACCESS_TOKEN'] = 'sgp_local_4de83dcc83243ccace746332bc8408e1ca48e89d'

sys.path.append('tools')

def test_sourcegraph_search():
    """Test Sourcegraph search functionality."""
    print("🔍 Testing Sourcegraph Search Integration")
    print("=" * 60)

    success = True

    # Test 1: Core search function
    print("\n🧪 Test 1: Core Search Function")
    try:
        from sourcegraph_search import search_code_with_sourcegraph

        test_cases = [
            ("PathManager", "Class name search"),
            ("get_tmp_file", "Function name search"),
            ("workingmemory", "Working memory search"),
        ]

        for query, description in test_cases:
            print(f"\n📝 {description}")
            print(f"   Query: '{query}'")

            result = search_code_with_sourcegraph(query, max_results=3)

            if result['success']:
                print(f"   ✅ Success: Found {result['total_results']} results")
                for i, r in enumerate(result.get('results', [])[:2]):
                    print(f"      {i+1}. {r['file_path']}:{r['line_number']}")
            else:
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
                success = False

    except Exception as e:
        print(f"❌ Core search test failed: {e}")
        success = False

    # Test 2: UF Tool Integration (as used by coding agent)
    print("\n\n🧪 Test 2: UF Tool Integration (Coding Agent)")
    try:
        # Add paths like the coding agent would
        import sys
        if '/Users/sgupta/oats/tools' not in sys.path:
            sys.path.insert(0, '/Users/sgupta/oats/tools')
        if '/Users/sgupta/oats' not in sys.path:
            sys.path.insert(0, '/Users/sgupta/oats')

        from sourcegraph_search_uf import sourcegraph_search, SourcegraphSearchInput

        uf_test_cases = [
            ("workingmemory", "python", "Working memory in Python"),
            ("get_tmp_file", None, "Function search"),
            ("PathManager", None, "Class search"),
        ]

        for query, language, description in uf_test_cases:
            print(f"\n📝 {description}")
            print(f"   Query: '{query}'" + (f", Language: {language}" if language else ""))

            test_input = SourcegraphSearchInput(query=query, language=language, max_results=3)
            result = sourcegraph_search(test_input)

            if result['success']:
                print(f"   ✅ Success: Found {result['total_results']} results")
                for i, r in enumerate(result.get('results', [])[:2]):
                    print(f"      {i+1}. {r['file']}:{r['line']}")
            else:
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
                success = False

    except Exception as e:
        print(f"❌ UF tool test failed: {e}")
        import traceback
        traceback.print_exc()
        success = False

    print(f"\n{'🎉 All tests passed!' if success else '❌ Some tests failed'}")
    return success

if __name__ == "__main__":
    success = test_sourcegraph_search()
    sys.exit(0 if success else 1)