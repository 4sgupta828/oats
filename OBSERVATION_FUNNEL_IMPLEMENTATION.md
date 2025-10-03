# 3-Layer Observation Funnel Implementation

## Problem Statement

Large tool outputs (e.g., 101 search results) were being fed directly to the LLM, causing:
- Context window overflow
- LLM response failures
- Incomplete analysis due to truncation
- Wasted turns trying to process truncated data

## The Solution: The 3-Layer Observation Funnel

Instead of a simple `output -> LLM` pipe, we now have a funnel that processes observations before the LLM sees them, giving it just enough information to make strategic decisions without being overwhelmed.

---

## Layer 1: The Tool-Side Summary (The "Receipt" 🧾)

### Implementation
**File:** `core/models.py`

Added `ObservationSummary` model to `ToolResult`:

```python
class ObservationSummary(BaseModel):
    """Layer 1: Tool-side summary (the 'receipt') for large outputs."""
    total_lines: Optional[int] = None
    total_chars: Optional[int] = None
    total_matches: Optional[int] = None
    files_with_matches: Optional[int] = None
    status_flag: str = Field(default="success")
    full_output_saved_to: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ToolResult(BaseModel):
    status: Literal["success", "failure"]
    output: Any
    error: Optional[str] = None
    cost: Optional[float] = None
    duration_ms: Optional[int] = None
    summary: Optional[ObservationSummary] = None  # NEW
```

### What It Does
- Captures **metrics** (lines, chars, matches, files)
- Saves full output to a **temporary file**
- Provides a **metadata summary** (the "receipt")
- Tool-specific extraction (e.g., JSON search results get match/file counts)

---

## Layer 2: The Orchestrator's Smart Truncation (The "Trailer" 🎬)

### Implementation
**File:** `reactor/tool_executor.py`

Added three key methods:

1. **`_is_large_output(output: str) -> bool`**
   - Determines if output needs funnel processing
   - Thresholds: 50 lines OR 2000 chars

2. **`_save_large_output_to_file(output: str, tool_name: str) -> str`**
   - Saves full output to `/tmp/ufflow_observations_<id>/<tool>_<timestamp>_<hash>.txt`
   - Returns file path for reference

3. **`_smart_truncate(output: str, tool_name: str) -> str`**
   - Shows **first 10 lines** (head)
   - Shows **last 5 lines** (tail)
   - Inserts truncation indicator in the middle
   - Like a "movie trailer" - gives the feel without the full content

4. **`_create_observation_summary(output: str, tool_name: str, saved_path: str) -> ObservationSummary`**
   - Generates metadata summary
   - Extracts tool-specific metrics (e.g., search match counts)

### Example Output

```
📊 LARGE OUTPUT DETECTED:
  - Total: 150 lines, 15000 chars
  - Matches: 101 results
  - Files: 32 files
  - Full output saved to: /tmp/ufflow_observations_xyz/content_search_20250102_143022_abc.txt
  - Preview (head/tail):
    [First 10 lines...]
    ... [130 lines truncated] ...
    [Last 5 lines...]
```

---

## Layer 3: The LLM's Strategic Action (The "Director" 🧑‍🎬)

### Implementation
**File:** `reactor/prompt_builder.py`

Added new section to agent prompt: **"The Principle of Large Output Handling"**

### What It Teaches the LLM

1. **Recognize the pattern**: When you see "LARGE OUTPUT DETECTED", don't try to parse it yourself

2. **Act as a Director**: Use streaming tools to process the saved file:
   - `grep/awk/sed` for pattern extraction
   - `jq` for JSON processing
   - Python scripts for complex logic
   - `head/tail` for sampling

3. **Never do these**:
   - ❌ Read the entire file into context
   - ❌ Use `create_file` with truncated data

4. **Example strategic responses**:
   ```bash
   # Good: Strategic processing
   jq -r '.[] | "\(.file):\(.line) - \(.match)"' /tmp/.../results.json > formatted.txt
   ```

### Strategic Guidance Display

When large output is detected, the observation now includes:

```
🎬 STRATEGIC GUIDANCE (Layer 3: The Director)
============================================================
The full output has been saved to a file. DO NOT attempt to:
  ❌ Read the entire file into context
  ❌ Use create_file with truncated data

INSTEAD, use streaming tools to process the saved file:
  ✅ Use grep/awk/sed to extract specific patterns
  ✅ Use jq for JSON processing
  ✅ Write a Python script to parse and analyze
  ✅ Use head/tail to sample different sections

Your role is to DIRECT these tools, not parse the data yourself.
============================================================
```

---

## How This Solves the Original Problem

### Before (Broken Workflow)
1. Tool returns 101 search results (15KB of JSON)
2. Entire output fed to LLM → **Context overflow**
3. LLM response fails or is incomplete
4. Agent tries to use truncated data → **Incorrect analysis**

### After (Fixed Workflow)
1. Tool returns 101 search results (15KB of JSON)
2. **Funnel activates**:
   - Full output saved to `/tmp/ufflow_observations_xyz/search_20250102.json`
   - Metadata extracted: "101 matches, 32 files"
   - Preview generated (first 10 + last 5 lines)
3. LLM receives clean summary + strategic guidance
4. LLM's next action: `jq` command to process the saved file
5. Extracted data is small and actionable → **Success**

---

## Testing

Run the test suite:
```bash
python test_observation_funnel.py
```

Tests verify:
1. ✅ Small outputs pass through unchanged
2. ✅ Large outputs trigger the funnel
3. ✅ JSON search results extract metadata (matches, files)
4. ✅ Smart truncation preserves head/tail structure
5. ✅ ObservationSummary model works correctly

---

## Configuration

Thresholds can be adjusted in `reactor/tool_executor.py`:

```python
LARGE_OUTPUT_LINE_THRESHOLD = 50    # Lines
LARGE_OUTPUT_CHAR_THRESHOLD = 2000  # Characters
```

---

## Files Modified

1. **`core/models.py`** - Added `ObservationSummary` model
2. **`reactor/tool_executor.py`** - Implemented Layers 1 & 2
3. **`reactor/prompt_builder.py`** - Implemented Layer 3 guidance
4. **`test_observation_funnel.py`** - Test suite (NEW)

---

## Benefits

1. **Prevents Context Overflow**: Large outputs no longer blow up the LLM context
2. **Maintains Data Integrity**: Full output is preserved in files
3. **Enables Strategic Processing**: LLM learns to use streaming tools
4. **Reduces Wasted Turns**: Agent no longer tries to parse truncated data
5. **Scalable**: Works with any size output (100 lines or 10,000 lines)

---

## Next Steps

The funnel is now active for all tool executions. The LLM will automatically receive funneled observations for large outputs and should respond by using streaming tools to process the saved files.

**Monitor the agent's behavior** to ensure it follows the strategic guidance and doesn't try to read large files directly into context.
