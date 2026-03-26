import argparse
import logging
import os
import signal
from dotenv import load_dotenv
from agents import MasterAgent
from arc_agi import Arcade, OperationMode

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global arcade instance to be accessible by signal handler
arc = None
card_id = None

def graceful_shutdown(signum, frame):
    logging.warning(f"Caught signal {signum}. Shutting down gracefully.")
    if arc and card_id:
        logging.info("--- Closing scorecard due to signal ---")
        arc.close_scorecard(card_id)
    exit(0)

def main():
    global arc, card_id
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    parser = argparse.ArgumentParser(description="Run Master/Worker agent system.")
    parser.add_argument("--game", type=str, required=True, help="Game ID to play.")
    parser.add_argument("--workers", nargs='+', default=["http://localhost:5001"], help="List of worker URLs.")
    args = parser.parse_args()

    logging.info("--- Starting Master/Worker System ---")
    
    arc = Arcade()
    arc.set_operation_mode(OperationMode.COMPETITION)
    logging.info(f"Operation mode set to: {arc.operation_mode}")

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
        if arc and card_id:
            arc.close_scorecard(card_id)
        logging.info("Master agent finished.")

if __name__ == "__main__":
    main()
