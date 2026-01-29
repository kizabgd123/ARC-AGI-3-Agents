import json
import pytest
from pathlib import Path
from unittest.mock import Mock

from agents.claude_recorder import ClaudeCodeRecorder


@pytest.mark.unit
class TestClaudeCodeRecorder:
    
    @pytest.fixture
    def recorder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path))
        return ClaudeCodeRecorder(game_id="test_game", agent_name="test_agent")
    
    def test_initialization(self, recorder, tmp_path):
        assert recorder.game_id == "test_game"
        assert recorder.agent_name == "test_agent"
        assert recorder.output_dir.exists()
        assert "test_game_test_agent" in str(recorder.output_dir)
    
    def test_aggregate_responses(self, recorder):
        formatted_messages = [
            {"type": "text", "content": "First reasoning"},
            {"type": "tool_call", "tool_name": "action1"},
            {"type": "text", "content": " Second reasoning"},
            {"type": "tool_result", "result": "ok"}
        ]
        
        result = recorder.aggregate_responses(formatted_messages)
        
        assert result == "First reasoning Second reasoning"
    
    def test_calculate_cost_no_messages(self, recorder):
        cost = recorder.calculate_cost([])
        assert cost == 0.0
    
    def test_calculate_cost_with_tokens(self, recorder):
        cost = recorder.calculate_cost([], input_tokens=1000, output_tokens=500)
        
        expected = (1000 * 0.003 / 1000) + (500 * 0.015 / 1000)
        assert cost == expected
    
    def test_calculate_cost_deduplicates_by_message_id(self, recorder):
        mock_msg1 = Mock()
        mock_msg1.id = "msg_123"
        mock_msg1.usage = Mock()
        mock_msg1.usage.input_tokens = 100
        mock_msg1.usage.output_tokens = 50
        
        mock_msg2 = Mock()
        mock_msg2.id = "msg_123"
        mock_msg2.usage = Mock()
        mock_msg2.usage.input_tokens = 100
        mock_msg2.usage.output_tokens = 50
        
        mock_msg3 = Mock()
        mock_msg3.id = "msg_456"
        mock_msg3.usage = Mock()
        mock_msg3.usage.input_tokens = 200
        mock_msg3.usage.output_tokens = 100
        
        messages = [mock_msg1, mock_msg2, mock_msg3]
        cost = recorder.calculate_cost(messages)
        
        expected = (300 * 0.003 / 1000) + (150 * 0.015 / 1000)
        assert cost == expected
    
    def test_save_step_creates_file(self, recorder):
        step = 1
        prompt = "Test prompt"
        messages = []
        parsed_action = {"action": 1, "reasoning": "Test reasoning"}
        cost = 0.05
        
        recorder.save_step(step, prompt, messages, parsed_action, cost)
        
        step_file = recorder.output_dir / "step_001.json"
        assert step_file.exists()
        
        with open(step_file, "r") as f:
            data = json.load(f)
        
        assert data["step"] == 1
        assert data["prompt"] == "Test prompt"
        assert data["parsed_action"] == parsed_action
        assert data["cost_usd"] == 0.05
    
    def test_format_messages_with_text(self, recorder):
        mock_msg = Mock()
        mock_msg.content = [Mock(text="Test reasoning")]
        mock_msg.content[0].text = "Test reasoning"
        
        from claude_agent_sdk import AssistantMessage
        
        messages = []
        formatted = recorder.format_messages(messages)
        
        assert isinstance(formatted, list)
    
    def test_save_step_formats_correctly(self, recorder):
        mock_msg = Mock()
        mock_msg.id = "msg_123"
        mock_msg.usage = Mock()
        mock_msg.usage.input_tokens = 100
        mock_msg.usage.output_tokens = 50
        
        step = 50
        prompt = "Game state prompt"
        messages = [mock_msg]
        parsed_action = {"action": 4, "reasoning": "Moving right"}
        cost = 0.12
        
        recorder.save_step(step, prompt, messages, parsed_action, cost)
        
        step_file = recorder.output_dir / "step_050.json"
        assert step_file.exists()
        
        with open(step_file, "r") as f:
            data = json.load(f)
        
        assert data["step"] == 50
        assert data["prompt"] == "Game state prompt"
        assert data["parsed_action"]["action"] == 4
        assert data["parsed_action"]["reasoning"] == "Moving right"
        assert data["cost_usd"] == 0.12
        assert "timestamp" in data
        assert "messages" in data
        assert "final_response" in data
