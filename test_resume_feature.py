#!/usr/bin/env python3
"""
Test script for the new resume feature.

Demonstrates:
1. Starting a new execution
2. Resuming with 'new' mode (fresh start)
3. Resuming with 'continue' mode (summarized context)
"""

import requests
import time
import json

API_BASE = "http://localhost:8000/api/v1"

def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def start_execution(goal, max_turns=5):
    """Start a new execution."""
    response = requests.post(
        f"{API_BASE}/executions",
        json={"goal": goal, "max_turns": max_turns}
    )
    response.raise_for_status()
    data = response.json()
    print(f"✅ Started execution: {data['execution_id']}")
    print(f"   Goal: {data['goal']}")
    return data['execution_id']

def wait_for_completion(execution_id, timeout=60):
    """Wait for execution to complete or reach a terminal state."""
    start = time.time()
    while time.time() - start < timeout:
        response = requests.get(f"{API_BASE}/executions/{execution_id}/status")
        status = response.json()['status']

        if status in ['completed', 'failed', 'cancelled']:
            print(f"✅ Execution {execution_id} reached status: {status}")
            return status

        time.sleep(1)

    print(f"⚠️  Timeout waiting for execution {execution_id}")
    return "timeout"

def get_execution_summary(execution_id):
    """Get execution summary."""
    # This would need a new endpoint, for now we'll use status
    response = requests.get(f"{API_BASE}/executions/{execution_id}/status")
    response.raise_for_status()
    return response.json()

def resume_execution_new(execution_id, new_goal, max_turns=5):
    """Resume execution in NEW mode (fresh start)."""
    response = requests.post(
        f"{API_BASE}/executions/{execution_id}/resume",
        json={
            "mode": "new",
            "goal": new_goal,
            "max_turns": max_turns
        }
    )
    response.raise_for_status()
    data = response.json()
    print(f"✅ Resumed in NEW mode")
    print(f"   Previous execution: {data['previous_execution_id']}")
    print(f"   New execution: {data['execution_id']}")
    print(f"   New goal: {data['goal']}")
    return data['execution_id']

def resume_execution_continue(execution_id, refined_goal, max_turns=5, keep_last_n_turns=3):
    """Resume execution in CONTINUE mode (with summarization)."""
    response = requests.post(
        f"{API_BASE}/executions/{execution_id}/resume",
        json={
            "mode": "continue",
            "goal": refined_goal,
            "max_turns": max_turns,
            "keep_last_n_turns": keep_last_n_turns
        }
    )
    response.raise_for_status()
    data = response.json()
    print(f"✅ Resumed in CONTINUE mode")
    print(f"   Execution: {data['execution_id']}")
    print(f"   Old goal: {data['old_goal'][:60]}...")
    print(f"   New goal: {data['new_goal'][:60]}...")
    print(f"   Previous turns: {data['previous_turns']}")
    print(f"   Keeping last {data['keep_last_n_turns']} turns")
    return data['execution_id']

def main():
    print_section("Testing Resume Feature")

    # Test 1: Start an initial execution
    print_section("Test 1: Start Initial Execution")
    exec_id = start_execution(
        goal="Check if the oats service is running and list all pods",
        max_turns=5
    )

    print(f"\n⏳ Waiting for execution to complete...")
    status = wait_for_completion(exec_id, timeout=120)

    if status in ['failed', 'timeout']:
        print(f"⚠️  Initial execution did not complete successfully. Continuing anyway for demo.")

    # Give it a moment to settle
    time.sleep(2)

    # Test 2: Resume with NEW mode (fresh start)
    print_section("Test 2: Resume with NEW Mode (Fresh Start)")
    print("This will reset all context and start with a completely new goal")

    new_exec_id = resume_execution_new(
        exec_id,
        new_goal="Check the health of the backend-api service",
        max_turns=5
    )

    print(f"\n⏳ Waiting for new execution to complete...")
    status = wait_for_completion(new_exec_id, timeout=120)

    # Test 3: Resume with CONTINUE mode (summarized context)
    print_section("Test 3: Resume with CONTINUE Mode (Keep Learnings)")
    print("This will preserve facts and learnings but summarize old turns")

    continued_exec_id = resume_execution_continue(
        new_exec_id,
        refined_goal="Check the health of the backend-api service and also verify database connectivity",
        max_turns=5,
        keep_last_n_turns=2
    )

    print(f"\n⏳ Waiting for continued execution to complete...")
    status = wait_for_completion(continued_exec_id, timeout=120)

    # Summary
    print_section("Test Summary")
    print(f"Original execution:   {exec_id}")
    print(f"New mode execution:   {new_exec_id}")
    print(f"Continue execution:   {continued_exec_id}")
    print()
    print("✅ All tests completed!")
    print()
    print("You can view the executions in the UI or via API:")
    print(f"  curl {API_BASE}/executions/{exec_id}/status")
    print(f"  curl {API_BASE}/executions/{new_exec_id}/status")
    print(f"  curl {API_BASE}/executions/{continued_exec_id}/status")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
