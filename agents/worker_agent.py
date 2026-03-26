from flask import Flask, request, jsonify
from arcengine.enums import GameAction, SimpleAction

def create_app():
    app = Flask(__name__)

    @app.route('/suggest_move', methods=['POST'])
    def suggest_move():
        # For now, return a hardcoded action
        # The agent's real job is to figure out what ACTION1, ACTION2, etc. do
        action_enum = GameAction.ACTION1
        action_data = SimpleAction()

        # The payload must be serializable and reconstructable by the master
        action_payload = {
            "id": action_enum.value,
            "name": action_enum.name, # Helpful for debugging
            "data": action_data.model_dump()
        }

        response = {
            'suggested_action': action_payload,
            'confidence_score': 0.5
        }
        return jsonify(response)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(port=5001)
