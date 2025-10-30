#!/usr/bin/env python3
"""Test agent execution with specific goal."""

import sys
import os

# Add UFFLOW to path
agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services', 'agent')
sys.path.insert(0, agent_dir)
sys.path.insert(0, os.path.join(agent_dir, 'tools'))

from core.models import Goal
from core.logging_config import get_logger, setup_logging
from registry.main import global_registry
from reactor.agent_controller import AgentController

# Setup logging
setup_logging(suppress_info_logs=True)
logger = get_logger('test_agent')

def test_agent_execution():
    """Test agent execution with RCA goal."""
    print("🔧 Setting up UFFLOW environment...")

    # Initialize providers (optional)
    try:
        from config.customer_config import initialize_customer_config
        from providers import initialize_providers

        customer_config = initialize_customer_config()
        if customer_config.validate_config():
            initialize_providers(customer_config.config)
            print(f"✅ Initialized providers for customer: {customer_config.get_customer_id()}")
    except Exception as e:
        print(f"⚠️  Failed to initialize providers: {e}")

    # Load tools
    tools_dir = os.path.join(agent_dir, 'tools')
    global_registry.load_ufs_from_directory(tools_dir)
    print(f"✅ Loaded {len(global_registry.list_ufs())} tools")

    # Create agent controller
    agent_controller = AgentController(global_registry)

    # Create goal
    goal_description = "find root cause of production issue from data dir /Users/sgupta/sim/output/data_20251029_133849"

    print(f"\n🎯 Testing goal: {goal_description}")
    print(f"📊 Max turns: 5")

    # Execute goal
    try:
        result = agent_controller.execute_goal(goal_description, max_turns=5)

        if result:
            print(f"\n{'='*80}")
            print(f"EXECUTION RESULT")
            print(f"{'='*80}")
            print(f"Success: {result.success}")
            print(f"Total Turns: {result.state.turn_count}")
            print(f"Goal Achieved: {result.state.is_complete}")
            print(f"Completion Reason: {result.state.completion_reason}")

            if result.state.transcript:
                print(f"\n{'='*80}")
                print(f"TURN-BY-TURN SUMMARY")
                print(f"{'='*80}")
                for i, entry in enumerate(result.state.transcript, 1):
                    status = "✅" if not entry.observation.startswith("ERROR") else "❌"
                    print(f"\n{status} Turn {entry.turn}: {entry.act.tool}")
                    print(f"   Hypothesis: {entry.strategize.hypothesis.claim}")
                    if entry.observation.startswith("ERROR"):
                        print(f"   ERROR: {entry.observation[:200]}...")
                    else:
                        print(f"   Success: {entry.observation[:200]}...")

            # Show any failures
            failures = [e for e in result.state.transcript if e.observation.startswith("ERROR")]
            if failures:
                print(f"\n{'='*80}")
                print(f"FAILURES DETECTED: {len(failures)}/{len(result.state.transcript)} turns failed")
                print(f"{'='*80}")
                for entry in failures:
                    print(f"\nTurn {entry.turn}: {entry.act.tool}")
                    print(f"Tool params: {entry.act.params}")
                    print(f"Error: {entry.observation[:500]}")

            return result
        else:
            print("❌ Execution failed to return result")
            return None

    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_agent_execution()
