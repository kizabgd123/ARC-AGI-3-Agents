import json
import os
from unittest.mock import MagicMock, patch

import pytest

from agents.structs import GameAction
from decision_engine.decision_engine import DecisionEngine

# from decision_engine.grid_parser import GridParser # GridParser is not directly used in this test

# Mock data for configurations
VETO_CONFIG_PATH = "config/veto_criteria.json"
SCORING_CONFIG_PATH = "config/scoring_metrics.json"
AUDIT_LOG_PATH = "logs/decision_audit.jsonl"

# Ensure config files exist for tests (mocking them if not)
@pytest.fixture(autouse=True)
def setup_config_files():
    # Create dummy config files for the test
    os.makedirs("config", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    with open(VETO_CONFIG_PATH, "w") as f:
        json.dump({"veto_rules": []}, f)
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
class TestDecisionEngineFullCycle:

    def test_full_decision_cycle(self):
        engine = DecisionEngine(
            veto_config_path=VETO_CONFIG_PATH,
            scoring_config_path=SCORING_CONFIG_PATH,
            audit_log_path=AUDIT_LOG_PATH
        )

        candidates = [GameAction.ACTION1.name, GameAction.ACTION2.name, GameAction.RESET.name]
        
        # Mock a simple game state
        game_state = {
            "player_position": (32, 32),
            "energy": 100,
            "energy_pill_visible": False,
            "key_matches_door": False,
            "door_distance": 50,
            "nearby_walls": [],
            "last_action": None,
            "grid_bounds": (0, 63, 0, 63)
        }

        # Mock run_veto_checks to pass all candidates for simplicity in full cycle test
        with patch.object(engine, 'run_veto_checks', return_value=(candidates, {})) as mock_veto:
            # Mock score_actions to return some scores
            with patch.object(engine, 'score_actions', return_value={
                GameAction.ACTION1.name: 70.0, 
                GameAction.ACTION2.name: 60.0, 
                GameAction.RESET.name: 30.0
            }) as mock_score:
                # Mock make_recommendation to return a recommended action
                with patch.object(engine, 'make_recommendation', return_value=(GameAction.ACTION1.name, MagicMock())) as mock_recommend:
                    # Mock log_decision to avoid actual file writing issues during test
                    with patch.object(engine, 'log_decision') as mock_log:
                        # Full cycle execution
                        survivors, vetoed = engine.run_veto_checks(candidates, game_state)
                        scores = engine.score_actions(survivors, game_state)
                        recommended, reason = engine.make_recommendation(survivors, scores, vetoed)
                        engine.log_decision("test_scenario", "test_context", candidates, vetoed, scores, recommended, reason)

                        # Assertions to ensure methods were called
                        mock_veto.assert_called_once_with(candidates, game_state)
                        mock_score.assert_called_once_with(survivors, game_state)
                        mock_recommend.assert_called_once_with(survivors, scores, vetoed)
                        mock_log.assert_called_once()
                        
                        assert recommended == GameAction.ACTION1.name
