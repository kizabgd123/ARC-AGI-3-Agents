import requests
import json
from typing import List
from agents.agent import Agent
from arcengine.enums import FrameData, GameAction

class MasterAgent(Agent):
    def __init__(self, worker_urls: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worker_urls = worker_urls

    def is_done(self, frames: List[FrameData], latest_frame: FrameData) -> bool:
        # Simple termination condition for now
        return self.action_counter >= 10

    def choose_action(self, frames: List[FrameData], latest_frame: FrameData) -> GameAction:
        # For now, contact only the first worker
        worker_url = self.worker_urls[0]
        
        # Pydantic's model_dump_json() is the reliable way to serialize
        payload_str = f'{{"game_state": {latest_frame.model_dump_json()}}}'
        
        response = requests.post(f"{worker_url}/suggest_move", data=payload_str, headers={'Content-Type': 'application/json'})
        response.raise_for_status()
        
        suggestion = response.json()
        
        action_payload = suggestion['suggested_action']
        action_id = action_payload['id']
        action_data = action_payload['data']
        
        action = GameAction.from_id(action_id)
        action.set_data(action_data)

        return action
