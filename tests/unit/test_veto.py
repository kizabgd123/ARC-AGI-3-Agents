import json
import os

import pytest

from agents.structs import GameAction
from decision_engine.decision_engine import DecisionEngine

# Mock data for configurations
VETO_CONFIG_PATH = "config/veto_criteria.json"
SCORING_CONFIG_PATH = "config/scoring_metrics.json" # Needed for DecisionEngine init
AUDIT_LOG_PATH = "logs/decision_audit.jsonl" # Needed for DecisionEngine init

@pytest.fixture(autouse=True)
def setup_config_files():
    # Create dummy config files for the test
    os.makedirs("config", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    with open(VETO_CONFIG_PATH, "w") as f:
        json.dump({
          "veto_rules": [
            {"id": "V1", "name": "boundary_violation", "severity": "CRITICAL", "auto_veto": True},
            {"id": "V2", "name": "wall_collision", "severity": "CRITICAL", "auto_veto": True},
            {"id": "V3", "name": "repeated_failure", "severity": "HIGH", "threshold": 3}
          ]
        }, f)
    with open(SCORING_CONFIG_PATH, "w") as f:
        json.dump({"metrics": [], "scoring_method": "weighted_sum"}, f)
    
    # Clean up after tests if audit log is created
    if os.path.exists(AUDIT_LOG_PATH):
        os.remove(AUDIT_LOG_PATH)
    
    yield # Run the test
    
    # Clean up dummy config files
    os.remove(VETO_CONFIG_PATH)
    os.remove(SCORING_CONFIG_PATH)
    os.rmdir("config")
    if os.path.exists(AUDIT_LOG_PATH):
        os.remove(AUDIT_LOG_PATH)
    os.rmdir("logs")


@pytest.mark.unit
class TestVetoChecks:

    @pytest.fixture
    def decision_engine(self):
        return DecisionEngine(
            veto_config_path=VETO_CONFIG_PATH,
            scoring_config_path=SCORING_CONFIG_PATH,
            audit_log_path=AUDIT_LOG_PATH
        )

    @pytest.mark.parametrize("action_name, player_pos, expected_survivors, expected_vetoed_reasons", [
        # V1: boundary_violation
        (GameAction.ACTION1.name, (0, 30), [], {"ACTION1": ["V1: boundary_violation"]}), # Move UP from top edge
        (GameAction.ACTION2.name, (63, 30), [], {"ACTION2": ["V1: boundary_violation"]}), # Move DOWN from bottom edge
        (GameAction.ACTION3.name, (30, 0), [], {"ACTION3": ["V1: boundary_violation"]}), # Move LEFT from left edge
        (GameAction.ACTION4.name, (30, 63), [], {"ACTION4": ["V1: boundary_violation"]}), # Move RIGHT from right edge
        (GameAction.ACTION1.name, (30, 30), [GameAction.ACTION1.name], {}), # Valid move
    ])
    def test_boundary_violation(self, decision_engine, action_name, player_pos, expected_survivors, expected_vetoed_reasons):
        candidates = [action_name]
        game_state = {
            "player_position": player_pos,
            "grid_bounds": (0, 63, 0, 63),
            "nearby_walls": [], # No walls
            "last_actions_outcomes": [] # No history for repeated failure
        }
        survivors, vetoed = decision_engine.run_veto_checks(candidates, game_state)
        assert set(survivors) == set(expected_survivors)
        assert vetoed == expected_vetoed_reasons

    @pytest.mark.parametrize("action_name, player_pos, nearby_walls, expected_survivors, expected_vetoed_reasons", [
        # V2: wall_collision (simplified: assuming nearby_walls logic works)
        (GameAction.ACTION1.name, (30, 30), [{"position": (29, 30), "type": "wall"}], [], {"ACTION1": ["V2: wall_collision"]}),
        (GameAction.ACTION1.name, (30, 30), [], [GameAction.ACTION1.name], {}), # No wall
    ])
    def test_wall_collision(self, decision_engine, action_name, player_pos, nearby_walls, expected_survivors, expected_vetoed_reasons):
        candidates = [action_name]
        game_state = {
            "player_position": player_pos,
            "grid_bounds": (0, 63, 0, 63),
            "nearby_walls": nearby_walls,
            "last_actions_outcomes": []
        }
        survivors, vetoed = decision_engine.run_veto_checks(candidates, game_state)
        assert set(survivors) == set(expected_survivors)
        assert vetoed == expected_vetoed_reasons

    @pytest.mark.parametrize("action_name, initial_failure_counts, expected_survivors, expected_vetoed_reasons", [
        # V3: repeated_failure (threshold=3)
        (GameAction.ACTION1.name, {GameAction.ACTION1.name: 3}, [], {"ACTION1": ["V3: repeated_failure"]}),
        (GameAction.ACTION1.name, {GameAction.ACTION1.name: 2}, [GameAction.ACTION1.name], {}),
        (GameAction.ACTION2.name, {GameAction.ACTION1.name: 3}, [GameAction.ACTION2.name], {}), # Different action
    ])
    def test_repeated_failure(self, decision_engine, action_name, initial_failure_counts, expected_survivors, expected_vetoed_reasons):
        candidates = [action_name]
        game_state = { # Minimal game_state needed
            "player_position": (30, 30),
            "grid_bounds": (0, 63, 0, 63),
            "nearby_walls": [],
        }
        
        # Mock the internal failure_counts of the decision_engine
        decision_engine.failure_counts = initial_failure_counts
        
        survivors, vetoed = decision_engine.run_veto_checks(candidates, game_state)
        assert set(survivors) == set(expected_survivors)
        assert vetoed == expected_vetoed_reasons
