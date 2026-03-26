import pytest
from flask import Flask
import json
from agents.worker_agent import create_app
from arcengine.enums import FrameData

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_suggest_move_endpoint(client):
    # Mock FrameData, replace with a real one later if needed
    mock_frame = FrameData(game_id="test", frame=[[]], state="NOT_PLAYED", levels_completed=0, win_levels=0, guid="", full_reset=False, available_actions=[])
    
    response = client.post('/suggest_move', 
                           data=f'{{"game_state": {mock_frame.model_dump_json()}}}',
                           content_type='application/json')
    
    assert response.status_code == 200
    data = response.get_json()
    assert 'suggested_action' in data
    assert 'confidence_score' in data
    
    action = data['suggested_action']
    assert 'id' in action
    assert 'name' in action
    assert 'data' in action
    assert isinstance(action['id'], int)
