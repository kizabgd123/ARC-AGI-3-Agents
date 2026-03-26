import pytest
import requests_mock
from agents.master_agent import MasterAgent
from arcengine.enums import FrameData, GameAction, SimpleAction

def test_master_agent_chooses_action():
    worker_url = "http://localhost:5001"
    # The base Agent class expects a valid arc_env. We pass None for this unit test,
    # as choose_action doesn't directly use it. This may need adjustment if the
    # base class initialization changes.
    agent = MasterAgent(worker_urls=[worker_url], game_id="test_game", card_id="test_card", agent_name="test_master", ROOT_URL="", record=False, arc_env=None)

    action_enum = GameAction.ACTION1
    action_data = SimpleAction()
    mock_response = {
        'suggested_action': {
            "id": action_enum.value,
            "name": action_enum.name,
            "data": action_data.model_dump()
        },
        'confidence_score': 0.9
    }

    with requests_mock.Mocker() as m:
        m.post(f"{worker_url}/suggest_move", json=mock_response)
        
        # Mock FrameData
        mock_frame = FrameData(game_id="test", frame=[[]], state="NOT_PLAYED", levels_completed=0, win_levels=0, guid="", full_reset=False, available_actions=[])
        
        action = agent.choose_action(frames=[], latest_frame=mock_frame)
        
        assert isinstance(action, GameAction)
        assert action.name == "ACTION1"
