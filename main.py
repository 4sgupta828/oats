# uf_flow/main.py

import uuid
import sys
import os
import argparse
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.models import Goal
from registry.main import global_registry
from planner.main import create_plan_for_goal
from orchestrator.main import Orchestrator
from reactor.agent_controller import AgentController

def run_end_to_end_example():
    """
    Runs a full example of the UF-Flow agentic framework.
    """
    print("--- 🚀 Starting UF-Flow End-to-End Example ---")

    # 1. SETUP: Load all available tools from the 'tools' directory.
    print("\n[1. SETUP] Loading tools from the './tools' directory...")
    global_registry.load_ufs_from_directory('./tools')
    print(f"Registry loaded with {len(global_registry.list_ufs())} tools.")

    # 2. GOAL: Define the user's high-level objective.
    goal_description = "Create a file named 'hello.txt' with the content 'Hello, agent world!' and then read the content of that file back."
    goal = Goal(id=str(uuid.uuid4()), description=goal_description)
    print(f"\n[2. GOAL] User goal is: '{goal.description}'")

    # 3. PLAN: Use the AI planner to generate a step-by-step plan.
    print("\n[3. PLAN] Handing goal to the AI planner...")
    try:
        plan = create_plan_for_goal(goal, global_registry)
    except Exception as e:
        print(f"\n--- 🛑 Planning Failed ---")
        print(f"Could not generate a plan: {e}")
        return

    # 4. EXECUTE: Pass the generated plan to the orchestrator to run.
    print("\n[4. EXECUTE] Handing plan to the orchestrator...")
    orchestrator = Orchestrator()
    final_state = orchestrator.run_goal(goal, plan)

    # 5. RESULTS: Print the final outcome.
    print("\n--- ✅ End-to-End Run Complete ---")
    print(f"Final Plan Status: {final_state.plan.status.upper()}")
    print("\nExecution Summary:")
    for node_id, node in final_state.plan.nodes.items():
        print(f"  - Node '{node_id}' ({node.uf_name}): {node.status.upper()}")
        if node.result:
            print(f"    - Output: {node.result.output}")
            if node.result.error:
                print(f"    - Error: {node.result.error}")

def run_react_example():
    """
    Runs the ReAct framework example.
    """
    print("--- 🧠 Starting ReAct Framework Example ---")

    # 1. SETUP: Load all available tools
    print("\n[1. SETUP] Loading tools from the './tools' directory...")
    global_registry.load_ufs_from_directory('./tools')
    print(f"Registry loaded with {len(global_registry.list_ufs())} tools.")

    # 2. GOAL: Define the user's high-level objective
    goal_description = "Create a file named 'hello_react.txt' with the content 'Hello, ReAct world!' and then read the content of that file back to verify it was created correctly."
    print(f"\n[2. GOAL] User goal is: '{goal_description}'")

    # 3. EXECUTE: Use ReAct agent to accomplish the goal
    print("\n[3. REACT] Starting ReAct execution...")
    agent = AgentController(global_registry)
    result = agent.execute_goal(goal_description, max_turns=15)

    # 4. RESULTS: Print the outcome
    print("\n--- ✅ ReAct Execution Complete ---")
    print(f"Success: {result.success}")
    print(f"Summary: {result.execution_summary}")
    print(f"Total Turns: {result.state.turn_count}")

    if result.state.scratchpad:
        print("\nExecution History:")
        for entry in result.state.scratchpad:
            print(f"  Turn {entry.turn}: {entry.action.get('tool_name', 'unknown')}")
            if entry.observation.startswith("ERROR"):
                print(f"    ❌ {entry.observation}")
            else:
                print(f"    ✅ {entry.observation[:100]}{'...' if len(entry.observation) > 100 else ''}")

def compare_frameworks():
    """
    Run both static and ReAct frameworks for comparison.
    """
    print("--- 🔬 Framework Comparison ---")
    print("Running the same goal with both Static and ReAct frameworks...")

    # Load tools once
    global_registry.load_ufs_from_directory('./tools')

    goal_description = "Create a file named 'comparison_test.txt' with the content 'Framework comparison test' and read it back."

    print("\n1️⃣ STATIC FRAMEWORK:")
    try:
        goal = Goal(id=str(uuid.uuid4()), description=goal_description)
        plan = create_plan_for_goal(goal, global_registry)
        orchestrator = Orchestrator()
        static_result = orchestrator.run_goal(goal, plan)
        print(f"Static Result: {static_result.plan.status}")
    except Exception as e:
        print(f"Static Framework Error: {e}")

    print("\n2️⃣ REACT FRAMEWORK:")
    try:
        agent = AgentController(global_registry)
        react_result = agent.execute_goal(goal_description, max_turns=10)
        print(f"ReAct Result: {'Success' if react_result.success else 'Failed'}")
        print(f"ReAct Turns: {react_result.state.turn_count}")
    except Exception as e:
        print(f"ReAct Framework Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UF-Flow Framework Examples")
    parser.add_argument(
        "--mode",
        choices=["static", "react", "compare"],
        default="react",
        help="Choose execution mode: static (original), react (new), or compare (both)"
    )

    args = parser.parse_args()

    # Ensure OPENAI_API_KEY is set
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY environment variable not set")
        print("Please set it to use the framework:")
        print("export OPENAI_API_KEY='your-api-key-here'")
        sys.exit(1)

    if args.mode == "static":
        run_end_to_end_example()
    elif args.mode == "react":
        run_react_example()
    elif args.mode == "compare":
        compare_frameworks()