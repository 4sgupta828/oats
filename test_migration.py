#!/usr/bin/env python3
"""Test script to verify the migration to BasePrompt.md format"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from reactor.models import (
    ReActState, State, TranscriptEntry, ParsedLLMResponse,
    ReflectSection, StrategizeSection, ActSection, Hypothesis,
    Task, ActiveTask
)
from reactor.prompt_builder import ReActPromptBuilder
from core.models import UFDescriptor

def test_models():
    """Test that all new models can be instantiated"""
    print("Testing new data models...")

    # Test State
    state = State(
        goal="Test goal",
        tasks=[Task(id=1, desc="Test task", status="active")],
        active=ActiveTask(id=1, archetype="INVESTIGATE", phase="GATHER", turns=1),
        knownTrue=["fact1"],
        knownFalse=["invalid1"],
        unknowns=["unknown1"]
    )
    print(f"✓ State created: {state.goal}")

    # Test ReActState
    react_state = ReActState(goal="Test goal", state=state)
    print(f"✓ ReActState created with {len(react_state.transcript)} entries")

    # Test ParsedLLMResponse
    parsed = ParsedLLMResponse(
        reflect=ReflectSection(
            turn=1,
            narrativeSynthesis="Test synthesis",
            outcome="NO_LAST_ACTION",
            hypothesisResult="N/A",
            insight="Initial turn"
        ),
        strategize=StrategizeSection(
            reasoning="Test reasoning",
            hypothesis=Hypothesis(
                claim="Test claim",
                test="Test test",
                signal="Test signal"
            ),
            ifInvalidated="Test fallback"
        ),
        state=state,
        act=ActSection(tool="bash", params={"command": "echo test"}),
        is_finish=False,
        raw_response="test"
    )
    print(f"✓ ParsedLLMResponse created")

    # Test TranscriptEntry
    entry = TranscriptEntry(
        turn=1,
        reflect=parsed.reflect,
        strategize=parsed.strategize,
        state=parsed.state,
        act=parsed.act,
        observation="Test observation"
    )
    print(f"✓ TranscriptEntry created for turn {entry.turn}")

    return True

def test_prompt_builder():
    """Test that prompt builder can generate prompts"""
    print("\nTesting prompt builder...")

    builder = ReActPromptBuilder()
    print(f"✓ ReActPromptBuilder instantiated")

    # Create a simple state
    state = ReActState(
        goal="List all Python files",
        state=State(goal="List all Python files")
    )

    # Create dummy tools using the registry
    from registry.main import Registry
    registry = Registry()
    tools = registry.list_ufs()[:1]  # Just use first available tool for testing

    if not tools:
        print("⚠ No tools available, skipping prompt generation test")
        return True

    # Build prompt
    prompt = builder.build_react_prompt(state, tools)
    print(f"✓ Prompt generated ({len(prompt)} chars)")

    # Check key components
    assert "Reflect → Strategize → Act" in prompt, "Missing R-S-A description"
    assert "**Goal:**" in prompt, "Missing goal section"
    assert "**State:**" in prompt, "Missing state section"
    assert "**Turn Number:**" in prompt, "Missing turn number"
    print("✓ Prompt contains all required sections")

    return True

def test_json_parsing():
    """Test parsing of JSON responses"""
    print("\nTesting JSON response parsing...")

    from reactor.agent_controller import AgentController
    from registry.main import Registry

    registry = Registry()
    controller = AgentController(registry)

    # Test JSON response
    test_json = '''```json
{
  "reflect": {
    "turn": 1,
    "narrativeSynthesis": "Starting investigation",
    "outcome": "NO_LAST_ACTION",
    "hypothesisResult": "N/A",
    "insight": "This is the first turn"
  },
  "strategize": {
    "reasoning": "Need to list files",
    "hypothesis": {
      "claim": "Running ls will show Python files",
      "test": "Execute ls *.py",
      "signal": "Output contains .py files"
    },
    "ifInvalidated": "Try find command instead"
  },
  "state": {
    "goal": "List all Python files",
    "tasks": [
      {"id": 1, "desc": "List Python files", "status": "active"}
    ],
    "active": {
      "id": 1,
      "archetype": "INVESTIGATE",
      "phase": "GATHER",
      "turns": 1
    },
    "knownTrue": [],
    "knownFalse": [],
    "unknowns": ["What Python files exist"]
  },
  "act": {
    "tool": "bash",
    "params": {
      "command": "ls *.py"
    }
  }
}
```'''

    parsed = controller._parse_llm_response(test_json)
    print(f"✓ Parsed JSON response")
    assert parsed.reflect.turn == 1, "Wrong turn number"
    assert parsed.act.tool == "bash", "Wrong tool"
    assert parsed.act.params["command"] == "ls *.py", "Wrong command"
    print(f"✓ All fields parsed correctly")
    print(f"  - Tool: {parsed.act.tool}")
    print(f"  - Command: {parsed.act.params['command']}")
    print(f"  - Hypothesis: {parsed.strategize.hypothesis.claim}")

    return True

if __name__ == "__main__":
    try:
        print("=" * 60)
        print("MIGRATION TEST SUITE")
        print("=" * 60)

        success = True
        success &= test_models()
        success &= test_prompt_builder()
        success &= test_json_parsing()

        print("\n" + "=" * 60)
        if success:
            print("✅ ALL TESTS PASSED")
            print("Migration to BasePrompt.md format successful!")
        else:
            print("❌ SOME TESTS FAILED")
            sys.exit(1)
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
