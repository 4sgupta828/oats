import os
import sys

# Add parent directory to path to import sibling modules
sys.path.insert(0, '/app')

from reactor.agent_controller import AgentController
from registry.main import global_registry
from providers import initialize_providers
from config.customer_config import initialize_customer_config

def run_agent():
    """
    Container entrypoint to run a single goal-oriented investigation.
    """
    # Initialize customer configuration and providers
    try:
        customer_config = initialize_customer_config()
        if customer_config.validate_config():
            initialize_providers(customer_config.config)
            print(f"✅ Initialized providers for customer: {customer_config.get_customer_id()}")
        else:
            print("⚠️  Customer config validation failed, continuing with default tools only")
    except Exception as e:
        print(f"⚠️  Failed to initialize providers: {e}, continuing with default tools only")
    
    # Load all available tools from the 'tools' directory
    # Your existing discovery logic is perfect for this.
    global_registry.load_ufs_from_directory('./tools')

    # The goal is passed into the container via an environment variable.
    goal = os.environ.get("OATS_GOAL")
    if not goal:
        print("ERROR: OATS_GOAL environment variable not set. Aborting.")
        sys.exit(1)

    print(f"🚀 Starting OATS Agent for goal: '{goal}'")
    agent = AgentController(global_registry)
    result = agent.execute_goal(goal, max_turns=15)

    print("\n" + "="*30 + " EXECUTION SUMMARY " + "="*30)
    print(result.execution_summary)
    print("="*80)

    if not result.success or not result.state.is_complete:
        print("🔥 Goal execution did not complete successfully.")
        # Exit with a non-zero status code to signal failure to Kubernetes
        sys.exit(1)
    else:
        print("✅ Goal execution completed successfully.")

if __name__ == "__main__":
    run_agent()