#!/usr/bin/env python3
"""
Test script to verify the enhanced tool provisioner with LLM knowledge gathering.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.provisioner import ToolProvisioningAgent

def test_scrubcsv_installation():
    """Test the enhanced provisioner with scrubcsv installation."""
    print("Testing enhanced tool provisioner with scrubcsv...")
    print("=" * 60)

    # Create the provisioner agent
    agent = ToolProvisioningAgent()

    # Test the new LLM instructions action directly first
    print("\n1. Testing LLM instructions action directly:")
    print("-" * 40)

    parameters = {
        "tool_name": "scrubcsv",
        "platform": "macOS"
    }

    result = agent._execute_ask_llm_for_instructions_action(parameters)
    print(f"Result: {result}")

    print("\n2. Testing full provisioner flow:")
    print("-" * 40)

    # Test full provisioning flow
    goal = "I need scrubcsv to do CSV data cleaning"
    result = agent.run(goal, show_live_updates=True)

    print("\nFinal result:")
    print(f"Success: {result.get('success')}")
    print(f"Tool: {result.get('tool_name')}")
    print(f"Message: {result.get('message')}")
    print(f"Methods tried: {result.get('attempted_methods', [])}")

    return result

if __name__ == "__main__":
    test_scrubcsv_installation()