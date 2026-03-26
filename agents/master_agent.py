import requests
import json
from typing import List
from agents.agent import Agent
from arcengine.enums import FrameData, GameAction

from concurrent.futures import ThreadPoolExecutor

class MasterAgent(Agent):
    def __init__(self, worker_urls: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worker_urls = worker_urls

    def is_done(self, frames: List[FrameData], latest_frame: FrameData) -> bool:
        # Simple termination condition for now
        return self.action_counter >= 10

    def choose_action(self, frames: List[FrameData], latest_frame: FrameData) -> GameAction:
        payload_str = f'{{"game_state": {latest_frame.model_dump_json()}}}'
        
        suggestions = []
        
        def fetch(url):
            try:
                response = requests.post(f"{url}/suggest_move", data=payload_str, headers={'Content-Type': 'application/json'}, timeout=5)
                response.raise_for_status()
                return response.json()
            except requests.RequestException:
                return None

        with ThreadPoolExecutor(max_workers=len(self.worker_urls)) as executor:
            results = executor.map(fetch, self.worker_urls)
            suggestions = [r for r in results if r is not None]

        if not suggestions:
            # Default action if no workers respond
            return GameAction.from_id(0) # RESET

        best_suggestion = max(suggestions, key=lambda s: s['confidence_score'])
        
        action_payload = best_suggestion['suggested_action']
        action_id = action_payload['id']
        action_data = action_payload['data']
        
        action = GameAction.from_id(action_id)
        action.set_data(action_data)

        return action
