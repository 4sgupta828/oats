#!/usr/bin/env python3
"""Test script to verify the 3-layer observation funnel implementation."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.models import ToolResult, ObservationSummary
from reactor.tool_executor import ReActToolExecutor
from registry.main import Registry

def test_small_output():
    """Test that small outputs are passed through unchanged."""
    print("=" * 60)
    print("TEST 1: Small Output (No Funnel Applied)")
    print("=" * 60)

    registry = Registry()
    executor = ReActToolExecutor(registry)

    small_output = "Hello World\nThis is a small output\nWith only 3 lines"
    result = ToolResult(
        status="success",
        output={"stdout": small_output, "return_code": 0}
    )

    observation = executor._format_observation("test_tool", result)
    print(observation)
    print()

    # Verify no funnel was applied
    assert "LARGE OUTPUT DETECTED" not in observation
    assert "Full output saved to" not in observation
    print("✅ Small output passed through correctly\n")

def test_large_output():
    """Test that large outputs trigger the funnel."""
    print("=" * 60)
    print("TEST 2: Large Output (Funnel Applied)")
    print("=" * 60)

    registry = Registry()
    executor = ReActToolExecutor(registry)

    # Create large output (100 lines)
    large_lines = [f"Line {i}: Some data here" for i in range(100)]
    large_output = "\n".join(large_lines)

    result = ToolResult(
        status="success",
        output={"stdout": large_output, "return_code": 0}
    )

    observation = executor._format_observation("execute_shell", result)
    print(observation)
    print()

    # Verify funnel was applied
    assert "📊 LARGE OUTPUT DETECTED:" in observation
    assert "Total:" in observation
    assert "Full output saved to:" in observation
    assert "Preview (head/tail):" in observation
    # Strategic guidance is now in the prompt, not the observation
    print("✅ Large output correctly funneled\n")

def test_search_results_json():
    """Test that JSON search results get proper metadata extraction."""
    print("=" * 60)
    print("TEST 3: JSON Search Results (Metadata Extraction)")
    print("=" * 60)

    registry = Registry()
    executor = ReActToolExecutor(registry)

    # Simulate search results
    import json
    search_results = [
        {"file": "test1.py", "line": 10, "match": "def foo()"},
        {"file": "test2.py", "line": 20, "match": "def bar()"},
        {"file": "test1.py", "line": 30, "match": "def baz()"},
    ] * 40  # 120 results

    json_output = json.dumps(search_results, indent=2)

    result = ToolResult(
        status="success",
        output=json_output
    )

    observation = executor._format_observation("content_search", result)
    print(observation)
    print()

    # Verify metadata extraction
    assert "📊 LARGE OUTPUT DETECTED:" in observation
    assert "Matches:" in observation
    assert "Files:" in observation
    # Strategic guidance is in prompt, not observation
    print("✅ Search results metadata extracted correctly\n")

def test_observation_summary_model():
    """Test the ObservationSummary model."""
    print("=" * 60)
    print("TEST 4: ObservationSummary Model")
    print("=" * 60)

    summary = ObservationSummary(
        total_lines=150,
        total_chars=15000,
        total_matches=101,
        files_with_matches=32,
        status_flag="success",
        full_output_saved_to="/tmp/test.txt",
        metadata={"tool": "content_search"}
    )

    print(f"Summary: {summary}")
    print(f"  Lines: {summary.total_lines}")
    print(f"  Chars: {summary.total_chars}")
    print(f"  Matches: {summary.total_matches}")
    print(f"  Files: {summary.files_with_matches}")
    print(f"  Saved to: {summary.full_output_saved_to}")
    print()
    print("✅ ObservationSummary model works correctly\n")

def test_smart_truncate():
    """Test the smart truncation logic."""
    print("=" * 60)
    print("TEST 5: Smart Truncation (Preview Generation)")
    print("=" * 60)

    registry = Registry()
    executor = ReActToolExecutor(registry)

    # Create output with clear structure
    lines = [f"Result {i}" for i in range(100)]
    output = "\n".join(lines)

    preview = executor._smart_truncate(output, "test_tool")

    print("Preview generated:")
    print(preview)
    print()

    # Verify structure
    preview_lines = preview.split("\n")
    assert "Result 0" in preview  # First line
    assert "Result 99" in preview  # Last line
    assert "truncated" in preview.lower()  # Truncation indicator
    print("✅ Smart truncation works correctly\n")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("OBSERVATION FUNNEL TEST SUITE")
    print("=" * 60 + "\n")

    try:
        test_small_output()
        test_large_output()
        test_search_results_json()
        test_observation_summary_model()
        test_smart_truncate()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe 3-Layer Observation Funnel is working correctly!")
        print("Summary of changes:")
        print("  • Layer 1 (Receipt): ObservationSummary with metadata")
        print("  • Layer 2 (Trailer): Smart head/tail truncation")
        print("  • Layer 3 (Director): Strategic guidance in prompt")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
