#!/usr/bin/env python3
"""
Parallel Agent Runner for ARC-AGI-3

Run multiple agents across multiple games with configurable parallelization.
Supports:
- Same agent on multiple games (default Swarm behavior)
- Different agents on different games
- Batch processing with multiple scorecards
- Custom thread pool sizing
"""

# ruff: noqa: E402
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

import argparse
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from arc_agi import Arcade, OperationMode
from arc_agi.scorecard import EnvironmentScorecard

from agents import AVAILABLE_AGENTS

# Configure logging
logger = logging.getLogger(__name__)
log_level = logging.INFO
if os.environ.get("DEBUG", "False") == "True":
    log_level = logging.DEBUG

logger.setLevel(log_level)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(log_level)
stdout_handler.setFormatter(formatter)

file_handler = logging.FileHandler("parallel_logs.log", mode="w")
file_handler.setLevel(log_level)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stdout_handler)

# API Configuration
SCHEME = os.environ.get("SCHEME", "http")
HOST = os.environ.get("HOST", "localhost")
PORT = os.environ.get("PORT", 8001)

if (SCHEME == "http" and str(PORT) == "80") or (
    SCHEME == "https" and str(PORT) == "443"
):
    ROOT_URL = f"{SCHEME}://{HOST}"
else:
    ROOT_URL = f"{SCHEME}://{HOST}:{PORT}"


@dataclass
class AgentGameAssignment:
    """Assignment of an agent type to a specific game."""

    agent_name: str
    game_id: str
    tags: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    """Results from a batch run."""

    scorecard_id: str
    scorecard: Optional[EnvironmentScorecard]
    assignments: list[AgentGameAssignment]
    duration_seconds: float
    success: bool


class ParallelSwarm:
    """
    Enhanced parallel swarm for running multiple agents on multiple games.

    Supports:
    - Running same agent type on multiple games (original Swarm behavior)
    - Running different agent types on different games
    - Configurable max_workers for thread pool
    - Batch processing with multiple scorecards
    """

    def __init__(
        self,
        assignments: list[AgentGameAssignment],
        max_workers: Optional[int] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Initialize parallel swarm.

        Args:
            assignments: List of agent-game assignments
            max_workers: Max concurrent threads (default: len(assignments))
            tags: Base tags for all scorecards
        """
        self.assignments = assignments
        self.max_workers = max_workers or len(assignments)
        self.base_tags = tags or []
        self._arc = Arcade()
        self.results: list[BatchResult] = []

        logger.info(
            f"Initialized ParallelSwarm with {len(assignments)} assignments, "
            f"max_workers={self.max_workers}"
        )

    def run_single_scorecard(
        self,
        assignments: list[AgentGameAssignment],
        scorecard_tags: Optional[list[str]] = None,
    ) -> BatchResult:
        """
        Run multiple agents on a single scorecard.

        All agents share the same scorecard for coordinated evaluation.
        """
        start_time = time.time()
        tags = (self.base_tags + (scorecard_tags or [])) or []

        logger.info(f"Opening scorecard with tags: {tags}")
        card_id = self._arc.open_scorecard(tags=tags)
        logger.info(f"Scorecard opened: {card_id}")

        agents = []
        threads = []

        try:
            # Create agents for each assignment
            for assignment in assignments:
                agent_class = AVAILABLE_AGENTS[assignment.agent_name]
                agent = agent_class(
                    card_id=card_id,
                    game_id=assignment.game_id,
                    agent_name=assignment.agent_name,
                    ROOT_URL=ROOT_URL,
                    record=True,
                    arc_env=self._arc.make(assignment.game_id, scorecard_id=card_id),
                    tags=tags + [f"game:{assignment.game_id}"],
                )
                agents.append(agent)

            # Create and start threads
            for agent in agents:
                thread = threading.Thread(target=agent.main, daemon=True)
                threads.append(thread)

            logger.info(f"Starting {len(threads)} agent threads...")
            for t in threads:
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

            logger.info("All agent threads completed")

            # Close scorecard
            scorecard = self._arc.close_scorecard(card_id)

            duration = time.time() - start_time

            result = BatchResult(
                scorecard_id=card_id,
                scorecard=scorecard,
                assignments=assignments,
                duration_seconds=duration,
                success=True,
            )

            if scorecard:
                logger.info(f"Scorecard {card_id} results:")
                logger.info(json.dumps(scorecard.model_dump(), indent=2))

                # Online URL
                if self._arc.operation_mode == OperationMode.ONLINE:
                    scorecard_url = f"{ROOT_URL}/scorecards/{card_id}"
                    logger.info(f"View scorecard: {scorecard_url}")

            return result

        except Exception as e:
            logger.error(f"Error in scorecard {card_id}: {e}")
            # Cleanup agents
            for agent in agents:
                try:
                    agent.cleanup()
                except Exception:
                    pass

            return BatchResult(
                scorecard_id=card_id,
                scorecard=None,
                assignments=assignments,
                duration_seconds=time.time() - start_time,
                success=False,
            )

    def run_batch(
        self,
        batch_size: int = 1,
    ) -> list[BatchResult]:
        """
        Run agents in batches, each batch gets its own scorecard.

        Args:
            batch_size: Number of assignments per scorecard

        Returns:
            List of BatchResult for each batch
        """
        if batch_size >= len(self.assignments):
            # Single batch - run all together
            logger.info("Running all assignments in single batch")
            result = self.run_single_scorecard(self.assignments)
            self.results = [result]
            return self.results

        # Multiple batches
        logger.info(
            f"Running {len(self.assignments)} assignments in batches of {batch_size}"
        )

        batches = []
        for i in range(0, len(self.assignments), batch_size):
            batch = self.assignments[i : i + batch_size]
            batches.append(batch)

        results = []
        for i, batch in enumerate(batches):
            logger.info(f"=== Starting batch {i + 1}/{len(batches)} ===")
            tags = [f"batch_{i + 1}_of_{len(batches)}"]
            result = self.run_single_scorecard(batch, scorecard_tags=tags)
            results.append(result)
            self.results.append(result)

        return results

    def run_parallel_games(
        self,
        max_concurrent: int = 5,
    ) -> list[BatchResult]:
        """
        Run games in parallel using thread pool.

        Each game gets its own scorecard and runs independently.
        Best for testing many games quickly without coordination.

        Args:
            max_concurrent: Maximum concurrent games

        Returns:
            List of BatchResult for each game
        """
        logger.info(
            f"Running {len(self.assignments)} games with max_concurrent={max_concurrent}"
        )

        results = []

        def run_single_game(assignment: AgentGameAssignment) -> BatchResult:
            """Run a single game with its own scorecard."""
            tags = self.base_tags + [
                f"game:{assignment.game_id}",
                f"agent:{assignment.agent_name}",
            ]
            return self.run_single_scorecard(
                [assignment],
                scorecard_tags=tags,
            )

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(run_single_game, assignment): assignment
                for assignment in self.assignments
            }

            for future in as_completed(futures):
                assignment = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(
                        f"Completed {assignment.agent_name} on {assignment.game_id}: "
                        f"{'SUCCESS' if result.success else 'FAILED'}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed {assignment.agent_name} on {assignment.game_id}: {e}"
                    )
                    results.append(
                        BatchResult(
                            scorecard_id="",
                            scorecard=None,
                            assignments=[assignment],
                            duration_seconds=0,
                            success=False,
                        )
                    )

        self.results = results
        return results

    def print_summary(self) -> None:
        """Print summary of all results."""
        logger.info("\n" + "=" * 60)
        logger.info("PARALLEL RUN SUMMARY")
        logger.info("=" * 60)

        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        total_duration = sum(r.duration_seconds for r in self.results)

        logger.info(f"Total batches: {total}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(
            f"Total duration: {total_duration:.2f}s ({total_duration / 60:.2f} min)"
        )

        for i, result in enumerate(self.results):
            status = "✓" if result.success else "✗"
            games = ", ".join(
                f"{a.game_id}({a.agent_name})" for a in result.assignments
            )
            logger.info(
                f"{status} Batch {i + 1}: {games} - {result.duration_seconds:.2f}s"
            )

        logger.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parallel Agent Runner for ARC-AGI-3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run same agent on multiple games (original Swarm behavior)
  python parallel_runner.py --agent=llm --games=ar25,ls20,bp35

  # Run different agents on different games
  python parallel_runner.py --assign llm:ar25 --assign random:ls20 --assign fastllm:bp35

  # Run with limited concurrency
  python parallel_runner.py --agent=llm --games=ar25,ls20,bp35 --max-concurrent=2

  # Batch processing (multiple scorecards)
  python parallel_runner.py --agent=llm --games=ar25,ls20,bp35 --batch-size=2

  # Parallel independent games (fastest for testing)
  python parallel_runner.py --agent=llm --games=ar25,ls20,bp35 --parallel-games --max-concurrent=3
        """,
    )

    # Agent selection
    parser.add_argument(
        "-a",
        "--agent",
        choices=AVAILABLE_AGENTS.keys(),
        help="Single agent type to run on all games",
    )

    parser.add_argument(
        "-g",
        "--games",
        type=str,
        help="Comma-separated list of game IDs (e.g., ar25,ls20,bp35)",
    )

    parser.add_argument(
        "--assign",
        action="append",
        metavar="AGENT:GAME",
        help="Assign specific agent to game (can be repeated). Format: agent_name:game_id",
    )

    # Parallelization options
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=None,
        help="Maximum concurrent threads/games (default: number of assignments)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Split assignments into batches (each gets own scorecard)",
    )

    parser.add_argument(
        "--parallel-games",
        action="store_true",
        help="Run each game independently with own scorecard (fastest)",
    )

    # Metadata
    parser.add_argument(
        "-t",
        "--tags",
        type=str,
        help="Comma-separated tags for scorecards",
        default=None,
    )

    args = parser.parse_args()

    # Validate and build assignments
    assignments: list[AgentGameAssignment] = []

    if args.assign:
        # Custom assignments mode
        for assign in args.assign:
            if ":" not in assign:
                logger.error(f"Invalid assignment format '{assign}'. Use AGENT:GAME")
                sys.exit(1)
            agent_name, game_id = assign.split(":", 1)
            if agent_name not in AVAILABLE_AGENTS:
                logger.error(f"Unknown agent: {agent_name}")
                sys.exit(1)
            assignments.append(
                AgentGameAssignment(
                    agent_name=agent_name,
                    game_id=game_id,
                )
            )

    elif args.agent and args.games:
        # Single agent on multiple games
        game_list = [g.strip() for g in args.games.split(",")]
        for game_id in game_list:
            assignments.append(
                AgentGameAssignment(
                    agent_name=args.agent,
                    game_id=game_id,
                )
            )

    else:
        logger.error(
            "Must specify either:\n  --agent and --games, OR\n  --assign (one or more)"
        )
        sys.exit(1)

    if not assignments:
        logger.error("No assignments created")
        sys.exit(1)

    logger.info(f"Created {len(assignments)} assignments:")
    for a in assignments:
        logger.info(f"  - {a.agent_name} → {a.game_id}")

    # Parse tags
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",")]

    # Create and run swarm
    swarm = ParallelSwarm(
        assignments=assignments,
        max_workers=args.max_concurrent,
        tags=tags,
    )

    try:
        if args.parallel_games:
            # Independent parallel games
            results = swarm.run_parallel_games(
                max_concurrent=args.max_concurrent or len(assignments)
            )
        elif args.batch_size:
            # Batched processing
            results = swarm.run_batch(batch_size=args.batch_size)
        else:
            # Single scorecard (original Swarm behavior)
            results = swarm.run_batch(batch_size=len(assignments))

        # Print summary
        swarm.print_summary()

        # Exit with error if any failed
        if any(not r.success for r in results):
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    os.environ["TESTING"] = "False"
    main()
