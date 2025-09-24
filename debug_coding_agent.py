#!/usr/bin/env python3
"""
Debug script that simulates how the coding agent calls the sourcegraph tool.
This will help us identify any environment differences.
"""

import os
import sys
from pathlib import Path

def simulate_coding_agent_call():
    """Simulate how the coding agent would call the sourcegraph tool."""
    print("🤖 Simulating Coding Agent Call to sourcegraph_search")
    print("=" * 60)

    # The coding agent would likely have these in its path
    print("1. Setting up Python path...")
    oats_root = Path(__file__).parent
    tools_dir = oats_root / "tools"

    if str(oats_root) not in sys.path:
        sys.path.insert(0, str(oats_root))
        print(f"   Added to sys.path: {oats_root}")

    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
        print(f"   Added to sys.path: {tools_dir}")

    print(f"\n2. Current sys.path (first 3 entries):")
    for i, path in enumerate(sys.path[:3]):
        print(f"   [{i}] {path}")

    print(f"\n3. Environment check:")
    print(f"   PWD: {os.getcwd()}")
    print(f"   PATH: {os.environ.get('PATH', 'NOT SET')[:100]}...")

    # Import and call the tool like the coding agent would
    print(f"\n4. Importing sourcegraph tool...")
    try:
        from sourcegraph_search_uf import sourcegraph_search, SourcegraphSearchInput
        print(f"   ✅ Import successful")
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n5. Creating tool input...")
    test_input = SourcegraphSearchInput(query='workingmemory', language='python')
    print(f"   Input created: query='{test_input.query}', language='{test_input.language}'")

    print(f"\n6. Calling sourcegraph_search...")
    try:
        result = sourcegraph_search(test_input)
        print(f"\n7. Result received:")
        print(f"   Success: {result['success']}")
        print(f"   Total results: {result.get('total_results', 0)}")
        if not result['success']:
            print(f"   Error: {result.get('error', 'No error message')}")
        else:
            for i, r in enumerate(result.get('results', [])[:2]):
                print(f"   Result {i+1}: {r.get('file', 'NO FILE')}:{r.get('line', 'NO LINE')}")
    except Exception as e:
        print(f"   ❌ Call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simulate_coding_agent_call()