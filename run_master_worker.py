# ARC-AGI-3-Agents/run_master_worker.py
import argparse
import subprocess
from agents import MasterAgent
from arc_agi import Arcade

def main():
    parser = argparse.ArgumentParser(description="Run Master/Worker agent system.")
    parser.add_argument("--game", type=str, required=True, help="Game ID to play.")
    parser.add_argument("--workers", nargs='+', default=["http://localhost:5001"], help="List of worker URLs.")
    args = parser.parse_args()

    print("--- Starting Master/Worker System ---")
    print(f"Master will play game: {args.game}")
    print(f"Using workers: {args.workers}")
    print("
NOTE: Ensure worker servers are running separately. You can run a worker with:")
    print("python -m agents.worker_agent
")


    # This is a simplified setup. A real implementation would need to handle
    # the environment and scorecard more robustly, like Swarm does.
    arc = Arcade()
    card_id = arc.open_scorecard(tags=["master-worker-run"])
    print(f"Scorecard created: {card_id}")

    env = arc.make(args.game, scorecard_id=card_id)
    
    master = MasterAgent(
        worker_urls=args.workers,
        game_id=args.game,
        card_id=card_id,
        agent_name="master",
        ROOT_URL="", # Should be configured from environment
        record=True,
        arc_env=env
    )

    try:
        master.main()
    finally:
        print("--- Closing scorecard ---")
        arc.close_scorecard(card_id)
        print("Master agent finished.")


if __name__ == "__main__":
    main()
