#!/usr/bin/env python3
"""
Test script for the edit_file tool.
Tests all edge cases: replace, insert, delete, and boundary conditions.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from tools.file_system import edit_file, EditFileInput

def create_test_file(content: str) -> str:
    """Create a temporary test file with given content in the workspace tmp directory."""
    # Use workspace tmp directory
    tmp_dir = Path(__file__).parent / 'tmp'
    tmp_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', dir=str(tmp_dir)) as f:
        f.write(content)
        return f.name

def read_file(filepath: str) -> str:
    """Read file content."""
    with open(filepath, 'r') as f:
        return f.read()

def test_replace_lines():
    """Test replacing a block of lines."""
    print("\n=== Test 1: Replace lines 2-4 ===")

    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=2,
            end_line=4,
            new_content="new line 2\nnew line 3\n"
        ))

        new_content = read_file(filepath)
        expected = "line 1\nnew line 2\nnew line 3\nline 5\n"

        assert new_content == expected, f"Expected:\n{expected}\nGot:\n{new_content}"
        assert result['changes']['lines_removed'] == 3
        assert result['changes']['lines_added'] == 2
        assert result['changes']['net_change'] == -1
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_insert_lines():
    """Test inserting lines (end_line = start_line - 1)."""
    print("\n=== Test 2: Insert lines before line 3 ===")

    content = "line 1\nline 2\nline 3\nline 4\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=3,
            end_line=2,  # end_line = start_line - 1
            new_content="inserted line 1\ninserted line 2\n"
        ))

        new_content = read_file(filepath)
        expected = "line 1\nline 2\ninserted line 1\ninserted line 2\nline 3\nline 4\n"

        assert new_content == expected, f"Expected:\n{expected}\nGot:\n{new_content}"
        assert result['changes']['lines_removed'] == 0
        assert result['changes']['lines_added'] == 2
        assert result['changes']['operation'] == 'insert'
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_delete_lines():
    """Test deleting lines (empty new_content)."""
    print("\n=== Test 3: Delete lines 2-3 ===")

    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=2,
            end_line=3,
            new_content=""
        ))

        new_content = read_file(filepath)
        expected = "line 1\nline 4\nline 5\n"

        assert new_content == expected, f"Expected:\n{expected}\nGot:\n{new_content}"
        assert result['changes']['lines_removed'] == 2
        assert result['changes']['lines_added'] == 0
        assert result['changes']['net_change'] == -2
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_replace_single_line():
    """Test replacing a single line."""
    print("\n=== Test 4: Replace single line 3 ===")

    content = "line 1\nline 2\nline 3\nline 4\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=3,
            end_line=3,
            new_content="replaced line 3\n"
        ))

        new_content = read_file(filepath)
        expected = "line 1\nline 2\nreplaced line 3\nline 4\n"

        assert new_content == expected, f"Expected:\n{expected}\nGot:\n{new_content}"
        assert result['changes']['lines_removed'] == 1
        assert result['changes']['lines_added'] == 1
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_preview_mode():
    """Test preview mode (dry-run)."""
    print("\n=== Test 5: Preview mode ===")

    content = "line 1\nline 2\nline 3\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=2,
            end_line=2,
            new_content="CHANGED\n",
            preview=True
        ))

        # File should not be modified
        new_content = read_file(filepath)
        assert new_content == content, "File was modified in preview mode!"
        assert result['preview_mode'] == True
        assert result['changes']['lines_removed'] == 1
        assert result['changes']['lines_added'] == 1
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_insert_at_beginning():
    """Test inserting at the beginning of file."""
    print("\n=== Test 6: Insert at beginning ===")

    content = "line 1\nline 2\n"
    filepath = create_test_file(content)

    try:
        result = edit_file(EditFileInput(
            filename=filepath,
            start_line=1,
            end_line=0,  # end_line = start_line - 1
            new_content="new first line\n"
        ))

        new_content = read_file(filepath)
        expected = "new first line\nline 1\nline 2\n"

        assert new_content == expected, f"Expected:\n{expected}\nGot:\n{new_content}"
        assert result['changes']['operation'] == 'insert'
        print("✅ PASSED")
        print(f"Result: {result}")

    finally:
        os.unlink(filepath)

def test_error_invalid_line_numbers():
    """Test error handling for invalid line numbers."""
    print("\n=== Test 7: Error handling - invalid line numbers ===")

    content = "line 1\nline 2\nline 3\n"
    filepath = create_test_file(content)

    try:
        # Test start_line < 1
        try:
            edit_file(EditFileInput(
                filename=filepath,
                start_line=0,
                end_line=1,
                new_content="test"
            ))
            assert False, "Should have raised ValueError for start_line < 1"
        except ValueError as e:
            assert "must be >= 1" in str(e)
            print(f"✅ Correctly raised ValueError: {e}")

        # Test end_line > total lines
        try:
            edit_file(EditFileInput(
                filename=filepath,
                start_line=1,
                end_line=10,
                new_content="test"
            ))
            assert False, "Should have raised ValueError for end_line > total lines"
        except ValueError as e:
            assert "beyond file end" in str(e)
            print(f"✅ Correctly raised ValueError: {e}")

        print("✅ PASSED")

    finally:
        os.unlink(filepath)

def test_error_file_not_found():
    """Test error handling for non-existent file."""
    print("\n=== Test 8: Error handling - file not found ===")

    # Use a path within workspace that doesn't exist
    nonexistent = str(Path(__file__).parent / 'tmp' / 'nonexistent_file_12345.txt')

    try:
        edit_file(EditFileInput(
            filename=nonexistent,
            start_line=1,
            end_line=1,
            new_content="test"
        ))
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        print(f"✅ Correctly raised FileNotFoundError: {e}")
        print("✅ PASSED")

def run_all_tests():
    """Run all test cases."""
    print("=" * 60)
    print("Testing edit_file tool")
    print("=" * 60)

    tests = [
        test_replace_lines,
        test_insert_lines,
        test_delete_lines,
        test_replace_single_line,
        test_preview_mode,
        test_insert_at_beginning,
        test_error_invalid_line_numbers,
        test_error_file_not_found,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
