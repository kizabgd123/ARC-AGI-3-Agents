"""
Decision Engine — VETO → SCORING → PREPORUKA → AUDIT

Implementation of the Decision Playbook pattern for ARC-AGI-3 action selection.
"""

import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VetoSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class DecisionReason(Enum):
    CLEAR_WINNER = "clear_winner"
    SCORE_BASED = "score_based"
    SINGLE_SURVIVOR = "single_survivor"
    HUMAN_OVERRIDE = "human_override"
    DEFAULT = "default"


@dataclass
class VetoResult:
    vetoed: bool
    veto_id: Optional[str]
    reason: Optional[str]
    severity: Optional[str]


@dataclass
class ScoredAction:
    action_name: str
    raw_score: float
    normalized_score: float
    metrics_breakdown: Dict[str, float]
    veto_status: str


@dataclass
class DecisionRecord:
    scenario_id: str
    timestamp: str
    initiator: str
    context: str
    entities_evaluated: List[str]
    vetoed: Dict[str, List[str]]
    scores: Dict[str, float]
    recommended: str
    decision_reason: str
    human_override: Optional[str]
    hmac_signature: str


class DecisionEngine:
    """
    Core decision engine implementing VETO → SCORING → PREPORUKA → AUDIT workflow.
    """

    def __init__(
        self,
        veto_config_path: str = "config/veto_criteria.json",
        scoring_config_path: str = "config/scoring_metrics.json",
        audit_log_path: str = "logs/decision_audit.jsonl",
        hmac_secret: Optional[str] = None,
    ):
        logger.info(f"DEBUG: DecisionEngine CWD: {os.getcwd()}")
        logger.info(f"DEBUG: Veto config path: {veto_config_path}")
        logger.info(f"DEBUG: Scoring config path: {scoring_config_path}")

        self.veto_config = self._load_json(veto_config_path)
        self.scoring_config = self._load_json(scoring_config_path)
        self.audit_log_path = audit_log_path
        self.hmac_secret = hmac_secret or os.getenv(
            "DECISION_HMAC_SECRET", "default_secret"
        )

        # Ensure log directory exists
        os.makedirs(os.path.dirname(audit_log_path), exist_ok=True)

        # Game state tracking
        self.action_history: List[str] = []
        self.failure_counts: Dict[str, int] = {}
        self.last_positions: List[Tuple[int, int]] = []

        # EXPLORATION TRACKING
        self.visited_cells: set = set()
        self.total_cells_explored = 0

    def _load_json(self, path: str) -> Dict:
        """Load JSON configuration file."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {path}, using defaults")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {path}: {e}")
            return {}

    # ==================== VETO FAZA ====================

    def run_veto_checks(
        self, candidate_actions: List[str], game_state: Dict[str, Any]
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Run all VETO checks on candidate actions.

        Returns:
            - List of actions that passed all vetos
            - Dict of vetoed actions with their veto reasons
        """
        survivors = []
        vetoed_actions = {}

        for action in candidate_actions:
            # RESET action is always allowed (emergency fallback)
            if action == "RESET":
                survivors.append(action)
                continue

            veto_result = self._check_all_vetos(action, game_state)
            if veto_result.vetoed:
                veto_key = f"{veto_result.veto_id}: {veto_result.reason}"
                vetoed_actions[action] = [veto_key]
                logger.info(f"VETO: Action {action} blocked - {veto_result.reason}")
            else:
                survivors.append(action)

        return survivors, vetoed_actions

    def _check_all_vetos(self, action: str, game_state: Dict) -> VetoResult:
        """Check all veto rules for a single action."""
        veto_rules = self.veto_config.get("veto_rules", [])

        for rule in veto_rules:
            veto_check = getattr(self, f"check_{rule['name']}", None)
            if veto_check:
                result = veto_check(action, game_state, rule)
                if result:  # <-- If check function returns True, it means vetoed
                    return VetoResult(
                        vetoed=True,
                        veto_id=rule["id"],
                        reason=rule["name"],
                        severity=rule.get("severity", "MEDIUM"),
                    )

        return VetoResult(vetoed=False, veto_id=None, reason=None, severity=None)

    # ========== VETO Check Implementations ==========

    def check_boundary_violation(
        self, action: str, game_state: Dict, rule: Dict
    ) -> bool:
        """V1: Check if action moves player out of bounds (0-63)."""
        player_pos = game_state.get("player_position", (32, 32))
        action_deltas = {
            "ACTION1": (-1, 0),  # UP (row decreases)
            "ACTION2": (1, 0),  # DOWN (row increases)
            "ACTION3": (0, -1),  # LEFT (col decreases)
            "ACTION4": (0, 1),  # RIGHT (col increases)
        }

        delta = action_deltas.get(action, (0, 0))
        new_x = player_pos[0] + delta[0]
        new_y = player_pos[1] + delta[1]

        return new_x < 0 or new_x > 63 or new_y < 0 or new_y > 63

    def check_wall_collision(self, action: str, game_state: Dict, rule: Dict) -> bool:
        """V2: Check if action moves player into wall (INT<10>)."""
        player_pos = game_state.get("player_position", (32, 32))
        action_deltas = {
            "ACTION1": (-1, 0),  # UP (row decreases)
            "ACTION2": (1, 0),  # DOWN (row increases)
            "ACTION3": (0, -1),  # LEFT (col decreases)
            "ACTION4": (0, 1),  # RIGHT (col increases)
        }
        delta = action_deltas.get(action, (0, 0))
        target_pos = (player_pos[0] + delta[0], player_pos[1] + delta[1])

        nearby_walls = game_state.get("nearby_walls", [])
        for wall in nearby_walls:
            if wall["position"] == target_pos:
                return True  # Veto if moving into a wall
        return False

    def check_repeated_failure(self, action: str, game_state: Dict, rule: Dict) -> bool:
        """V3: Check if same action failed 3+ consecutive times."""
        threshold = rule.get("threshold", 3)
        return self.failure_counts.get(action, 0) >= threshold

    def check_energy_critical(self, action: str, game_state: Dict, rule: Dict) -> bool:
        """V4: Check if energy is critical and no refill nearby."""
        energy = game_state.get("energy", 25)
        threshold = rule.get("threshold", 5)
        has_pill_nearby = game_state.get("energy_pill_visible", False)

        return energy < threshold and not has_pill_nearby

    def check_ignore_rotator(self, action: str, game_state: Dict, rule: Dict) -> bool:
        """V5: Check if ignoring rotator when key doesn't match."""
        # Placeholder - implement with key-door match state
        return False

    def check_loop_detection(self, action: str, game_state: Dict, rule: Dict) -> bool:
        """V6: Detect action loops (same 4 actions repeating)."""
        loop_size = rule.get("loop_size", 4)
        if len(self.action_history) < loop_size * 2:
            return False

        recent = self.action_history[-loop_size:]
        previous = self.action_history[-loop_size * 2 : -loop_size]

        return recent == previous and recent[-1] == action

    # ==================== SCORING FAZA ====================

    def score_actions(
        self, candidate_actions: List[str], game_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Score surviving actions using weighted metrics.
        """
        scores = {}
        metrics = self.scoring_config.get("metrics", [])

        for action in candidate_actions:
            action_metrics = self._calculate_action_metrics(action, game_state)
            raw_score = self._weighted_sum(action_metrics, metrics)
            scores[action] = raw_score

        # Normalize scores to 0-100 scale
        normalized = self._normalize_scores(scores)

        return normalized

    def _calculate_action_metrics(
        self, action: str, game_state: Dict
    ) -> Dict[str, float]:
        """Calculate individual metric values for an action."""
        metrics = {}

        # 1. Progress toward door (30%)
        door_distance = game_state.get("door_distance", 100.0)
        # Normalize: closer = higher score
        metrics["progress_toward_door"] = max(0, 1.0 - (door_distance / 100.0))

        # 2. Energy efficiency (25%)
        energy = game_state.get("energy", 25)
        energy_pill_distance = game_state.get("energy_pill_distance", 100.0)
        # High energy + far from pill = efficient
        # Low energy + close to pill = smart (going for refill)
        if energy < 10 and energy_pill_distance < 20:
            metrics["energy_efficiency"] = 0.9  # Smart: going for refill
        elif energy >= 20:
            metrics["energy_efficiency"] = 0.8  # Good: high energy
        elif energy < 5:
            metrics["energy_efficiency"] = 0.3  # Bad: low energy, no refill plan
        else:
            metrics["energy_efficiency"] = 0.5

        # 3. Exploration value (20%) - NOW IMPLEMENTED
        player_pos = game_state.get("player_position", (32, 32))
        self._track_visited_cell(player_pos)
        metrics["exploration_value"] = self._calculate_exploration_score()

        # 4. Rotator proximity (15%)
        key_matches = game_state.get("key_matches_door", False)
        rotator_distance = game_state.get("rotator_distance", 100.0)
        if not key_matches and rotator_distance < 30:
            metrics["rotator_proximity"] = 0.9  # Smart: going to rotator
        elif not key_matches:
            metrics["rotator_proximity"] = 0.3  # Bad: ignoring rotator
        else:
            metrics["rotator_proximity"] = 0.5  # Key already matches

        # 5. Safety margin (10%)
        wall_distance = game_state.get("wall_distance", 10)
        metrics["safety_margin"] = min(1.0, wall_distance / 10.0)

        return metrics

    def _track_visited_cell(self, position: Tuple[int, int]) -> None:
        """Track that player has visited this cell."""
        # Round position to nearest integer for consistency
        cell = (int(position[0]), int(position[1]))
        if cell not in self.visited_cells:
            self.visited_cells.add(cell)
            self.total_cells_explored += 1

    def _calculate_exploration_score(self) -> float:
        """
        Calculate exploration value based on newly visited cells.

        Scoring:
        - High score (0.8-1.0): Moving to unvisited area
        - Medium score (0.4-0.7): Mixed visited/unvisited
        - Low score (0.0-0.3): Revisiting same cells (looping)
        """
        # Get recent positions (last 10 moves)
        recent_positions = self.last_positions[-10:] if self.last_positions else []

        if not recent_positions:
            return 0.5  # No history, neutral

        # Calculate how many recent positions are unique
        unique_recent = len(set(recent_positions))
        total_recent = len(recent_positions)

        # Ratio of unique to total recent positions
        uniqueness_ratio = unique_recent / total_recent if total_recent > 0 else 0.5

        # Also consider total exploration progress
        # Assuming ~4000 walkable cells, 100 moves should explore ~100 unique cells
        expected_exploration = min(1.0, self.total_cells_explored / 100.0)

        # Combine both factors
        exploration_score = (uniqueness_ratio * 0.6) + (expected_exploration * 0.4)

        return min(1.0, max(0.0, exploration_score))

    def _weighted_sum(
        self, metrics: Dict[str, float], metric_configs: List[Dict]
    ) -> float:
        """Calculate weighted sum of metrics."""
        total = 0.0
        for config in metric_configs:
            metric_name = config["name"]
            weight = config.get("weight", 1.0)
            value = metrics.get(metric_name, 0.0)
            total += value * weight

        return total * 100  # Scale to 0-100

    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to 0-100 range."""
        if not scores:
            return {}

        min_score = min(scores.values())
        max_score = max(scores.values())

        if max_score == min_score:
            return {k: 50.0 for k in scores}

        normalized = {}
        for action, score in scores.items():
            norm_score = (score - min_score) / (max_score - min_score) * 100
            normalized[action] = norm_score

        return normalized

    # ==================== PREPORUKA FAZA ====================

    def make_recommendation(
        self,
        survivors: List[str],
        scores: Dict[str, float],
        vetoed: Dict[str, List[str]],
    ) -> Tuple[str, DecisionReason]:
        """
        Make final recommendation based on survivors and scores.
        """
        if not survivors:
            # No survivors - use default
            return "RESET", DecisionReason.DEFAULT

        if len(survivors) == 1:
            # Single survivor - auto-select
            return survivors[0], DecisionReason.SINGLE_SURVIVOR

        # Multiple survivors - use scoring
        best_action = max(scores, key=scores.get)

        # Check for clear winner (>20% ahead of second best)
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap > 20:
                return best_action, DecisionReason.CLEAR_WINNER

        return best_action, DecisionReason.SCORE_BASED

    # ==================== AUDIT FAZA ====================

    def log_decision(
        self,
        scenario_id: str,
        context: str,
        candidates: List[str],
        vetoed: Dict[str, List[str]],
        scores: Dict[str, float],
        recommended: str,
        reason: DecisionReason,
        human_override: Optional[str] = None,
    ) -> DecisionRecord:
        """Log decision to audit trail with HMAC signature."""

        record = DecisionRecord(
            scenario_id=scenario_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            initiator="thinking_reflexion_agent",
            context=context,
            entities_evaluated=candidates,
            vetoed=vetoed,
            scores=scores,
            recommended=recommended,
            decision_reason=reason.value,
            human_override=human_override,
            hmac_signature="",
        )

        # Generate HMAC signature
        record.hmac_signature = self._generate_hmac(record)

        # Write to audit log
        self._write_audit_log(record)

        return record

    def _generate_hmac(self, record: DecisionRecord) -> str:
        """Generate HMAC signature for audit record."""
        data = f"{record.scenario_id}:{record.timestamp}:{record.recommended}"
        signature = hmac.new(
            self.hmac_secret.encode(), data.encode(), hashlib.sha256
        ).hexdigest()
        return signature

    def _write_audit_log(self, record: DecisionRecord) -> None:
        """Append record to JSONL audit log."""
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    # ==================== UTILS ====================

    def update_game_state(
        self,
        action_taken: str,
        success: bool,
        current_position: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Update internal game state tracking."""
        self.action_history.append(action_taken)

        # Track position for exploration calculation
        if current_position:
            self.last_positions.append(current_position)
            # Keep last 100 positions for exploration tracking
            if len(self.last_positions) > 100:
                self.last_positions = self.last_positions[-100:]

        if not success:
            self.failure_counts[action_taken] = (
                self.failure_counts.get(action_taken, 0) + 1
            )
        else:
            self.failure_counts[action_taken] = 0

        # Keep history bounded
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]

    def reset_game_state(self) -> None:
        """Reset game state tracking for new game."""
        self.action_history = []
        self.failure_counts = {}
        self.last_positions = []
        # Also reset exploration tracking
        self.visited_cells = set()
        self.total_cells_explored = 0
