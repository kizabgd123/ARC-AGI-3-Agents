import argparse
import logging
import os
from dotenv import load_dotenv
from agents import MasterAgent
from arc_agi import Arcade

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Run Master/Worker agent system.")
    parser.add_argument("--game", type=str, required=True, help="Game ID to play.")
    parser.add_argument("--workers", nargs='+', default=["http://localhost:5001"], help="List of worker URLs.")
    args = parser.parse_args()

    logging.info("--- Starting Master/Worker System ---")
    logging.info(f"Master will play game: {args.game}")
    logging.info(f"Using workers: {args.workers}")
    logging.info("NOTE: Ensure worker servers are running separately. You can run a worker with: python -m agents.worker_agent")

    arc = Arcade()
    card_id = arc.open_scorecard(tags=["master-worker-run"])
    logging.info(f"Scorecard created: {card_id}")

    env = arc.make(args.game, scorecard_id=card_id)
    
    master = MasterAgent(
        worker_urls=args.workers,
        game_id=args.game,
        card_id=card_id,
        agent_name="master",
        ROOT_URL=os.getenv("ARC_ROOT_URL", ""),
        record=True,
        arc_env=env
    )

    try:
        master.main()
    finally:
        logging.info("--- Closing scorecard ---")
        arc.close_scorecard(card_id)
        logging.info("Master agent finished.")


if __name__ == "__main__":
    main()
