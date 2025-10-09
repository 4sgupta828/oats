#!/usr/bin/env python3
"""
Example demonstrating the Read-Modify-Verify pattern for using edit_file tool.
This is the SAFE way to use edit_file to prevent errors from stale line numbers.
"""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from tools.file_system import edit_file, read_file, create_file
from tools.file_system import EditFileInput, ReadFileInput, CreateFileInput

def example_read_modify_verify():
    """
    Demonstrates the Read-Modify-Verify pattern.

    Pattern:
    1. READ: Get fresh content and line numbers
    2. PLAN: Calculate start_line and end_line
    3. MODIFY: Execute edit_file
    4. VERIFY: Read again to confirm changes
    """

    print("=" * 70)
    print("EXAMPLE: Read-Modify-Verify Pattern for edit_file")
    print("=" * 70)

    # Create a sample file
    print("\n📝 Step 0: Create a sample file")
    result = create_file(CreateFileInput(
        filename="example_code.py",
        content="""def hello():
    print("Hello")
    print("World")
    return True

def goodbye():
    print("Goodbye")
""",
        is_temporary=True
    ))
    filepath = result['filepath']
    print(f"Created: {filepath}")

    # STEP 1: READ - Get fresh content and line numbers
    print("\n📖 Step 1: READ - Get current content")
    content = read_file(ReadFileInput(filename=filepath))
    print("Current file content:")
    print(content)
    print()

    # STEP 2: PLAN - Decide what to change based on fresh content
    print("🧠 Step 2: PLAN - Calculate line numbers from fresh content")
    print("   Goal: Replace lines 2-3 (the two print statements in hello())")
    print("   New content: Combined into single print statement")
    start_line = 2
    end_line = 3
    new_content = '    print("Hello World")\n'
    print(f"   start_line={start_line}, end_line={end_line}")
    print()

    # STEP 3: MODIFY - Execute the edit
    print("✏️  Step 3: MODIFY - Execute edit_file")
    result = edit_file(EditFileInput(
        filename=filepath,
        start_line=start_line,
        end_line=end_line,
        new_content=new_content
    ))
    print(f"Edit result: {result['changes']}")
    print()

    # STEP 4: VERIFY - Read again to confirm
    print("✅ Step 4: VERIFY - Read modified content to confirm")
    new_content = read_file(ReadFileInput(filename=filepath))
    print("Modified file content:")
    print(new_content)
    print()

    print("=" * 70)
    print("✅ Read-Modify-Verify pattern completed successfully!")
    print("=" * 70)

def example_preview_mode():
    """Demonstrates using preview mode for safety."""

    print("\n" + "=" * 70)
    print("EXAMPLE: Using Preview Mode")
    print("=" * 70)

    # Create a sample file
    result = create_file(CreateFileInput(
        filename="example_preview.txt",
        content="line 1\nline 2\nline 3\nline 4\nline 5\n",
        is_temporary=True
    ))
    filepath = result['filepath']

    print("\n🔍 Preview mode: See changes without applying them")

    # Preview the change first
    preview = edit_file(EditFileInput(
        filename=filepath,
        start_line=2,
        end_line=4,
        new_content="REPLACED LINES\n",
        preview=True  # This prevents actual modification
    ))

    print(f"\nPreview results:")
    print(f"  Operation: {preview['changes']['operation']}")
    print(f"  Lines removed: {preview['changes']['lines_removed']}")
    print(f"  Lines added: {preview['changes']['lines_added']}")
    print(f"  Old content: {repr(preview['old_content'])}")
    print(f"  New content: {repr(preview['new_content'])}")

    # Now apply it for real
    print("\n✅ Preview looks good, applying changes...")
    edit_file(EditFileInput(
        filename=filepath,
        start_line=2,
        end_line=4,
        new_content="REPLACED LINES\n",
        preview=False
    ))

    print("=" * 70)

def example_special_cases():
    """Demonstrates special cases: insert and delete."""

    print("\n" + "=" * 70)
    print("EXAMPLE: Special Cases - Insert and Delete")
    print("=" * 70)

    # Create a sample file
    result = create_file(CreateFileInput(
        filename="example_special.txt",
        content="line 1\nline 2\nline 3\n",
        is_temporary=True
    ))
    filepath = result['filepath']

    # CASE 1: Insert lines (end_line = start_line - 1)
    print("\n📥 Insert lines before line 2 (end_line = start_line - 1)")
    edit_file(EditFileInput(
        filename=filepath,
        start_line=2,
        end_line=1,  # end_line = start_line - 1
        new_content="inserted line\n"
    ))

    content = read_file(ReadFileInput(filename=filepath))
    print("After insertion:")
    print(content)

    # CASE 2: Delete lines (empty new_content)
    print("\n🗑️  Delete line 2 (empty new_content)")
    edit_file(EditFileInput(
        filename=filepath,
        start_line=2,
        end_line=2,
        new_content=""  # Empty = delete
    ))

    content = read_file(ReadFileInput(filename=filepath))
    print("After deletion:")
    print(content)

    print("=" * 70)

if __name__ == "__main__":
    example_read_modify_verify()
    example_preview_mode()
    example_special_cases()

    print("\n✨ All examples completed!")
    print("\n💡 Remember: Always use Read-Modify-Verify pattern:")
    print("   1. Read file to get fresh line numbers")
    print("   2. Plan your changes based on fresh content")
    print("   3. Execute edit_file")
    print("   4. Verify by reading the modified section")
