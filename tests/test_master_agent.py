import pytest
import requests_mock
from agents.master_agent import MasterAgent
from arcengine.enums import FrameData, GameAction, SimpleAction, ComplexAction

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

def test_master_agent_broadcasts_and_selects_best():
    worker_urls = ["http://localhost:5001", "http://localhost:5002"]
    agent = MasterAgent(worker_urls=worker_urls, game_id="test_game", card_id="test_card", agent_name="test_master", ROOT_URL="", record=False, arc_env=None)

    # Worker 1 suggests ACTION1 with low confidence
    action1_enum = GameAction.ACTION1
    action1_data = SimpleAction()
    mock_response1 = {
        'suggested_action': {"id": action1_enum.value, "name": action1_enum.name, "data": action1_data.model_dump()},
        'confidence_score': 0.5
    }
    
    # Worker 2 suggests ACTION6 (a complex action) with high confidence
    action2_enum = GameAction.ACTION6
    action2_data = ComplexAction(x=10, y=20)
    mock_response2 = {
        'suggested_action': {"id": action2_enum.value, "name": action2_enum.name, "data": action2_data.model_dump()},
        'confidence_score': 0.9
    }

    with requests_mock.Mocker() as m:
        m.post(worker_urls[0] + "/suggest_move", json=mock_response1)
        m.post(worker_urls[1] + "/suggest_move", json=mock_response2)
        
        mock_frame = FrameData(game_id="test", frame=[[]], state="NOT_PLAYED", levels_completed=0, win_levels=0, guid="", full_reset=False, available_actions=[])
        
        action = agent.choose_action(frames=[], latest_frame=mock_frame)
        
        # Should choose the action from worker 2
        assert action.name == "ACTION6"
        assert action.action_data.x == 10
        assert action.action_data.y == 20
