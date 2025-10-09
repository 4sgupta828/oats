"""
Main entrypoint for containerized OATS agent execution
Reads goal from environment and executes the agent
"""
import os
import sys
import logging
import json
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from reactor.agent_controller import AgentController
from registry.main import Registry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entrypoint for containerized agent"""
    logger.info("Starting OATS SRE Agent in container mode")

    # Get configuration from environment
    goal = os.getenv("OATS_GOAL")
    max_turns = int(os.getenv("OATS_MAX_TURNS", "15"))
    llm_provider = os.getenv("UFFLOW_LLM_PROVIDER", "openai")

    if not goal:
        logger.error("OATS_GOAL environment variable not set")
        sys.exit(1)

    logger.info(f"Goal: {goal}")
    logger.info(f"Max turns: {max_turns}")
    logger.info(f"LLM Provider: {llm_provider}")

    try:
        # Initialize the agent
        logger.info("Initializing agent and registry...")
        registry = Registry()
        registry.discover_and_load_ufs()
        agent = AgentController(registry)

        # Execute the goal
        logger.info("Agent execution started")
        result = agent.execute_goal(goal=goal, max_turns=max_turns)

        # Save result to output directory
        output_dir = Path("/output")
        output_dir.mkdir(exist_ok=True)

        result_file = output_dir / "result.json"
        with open(result_file, "w") as f:
            json.dump({
                "goal": goal,
                "status": result.status if hasattr(result, 'status') else "completed",
                "summary": result.execution_summary if hasattr(result, 'execution_summary') else str(result),
                "turns": result.turn_count if hasattr(result, 'turn_count') else max_turns
            }, f, indent=2)

        logger.info(f"Agent execution completed successfully")
        logger.info(f"Result saved to {result_file}")
        return 0

    except Exception as e:
        logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
