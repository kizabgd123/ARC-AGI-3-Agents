import pytest
from unittest.mock import patch, MagicMock
import run_master_worker

@patch('run_master_worker.Arcade')
@patch('run_master_worker.argparse.ArgumentParser')
def test_main_function_runs(mock_argparse, mock_arcade):
    # Mock command line arguments
    mock_args = MagicMock()
    mock_args.game = "test_game"
    mock_args.workers = ["http://localhost:5001"]
    mock_argparse.return_value.parse_args.return_value = mock_args

    # Mock the Arcade object and its methods
    mock_arcade_instance = MagicMock()
    mock_arcade.return_value = mock_arcade_instance
    
    # Mock the agent and its main loop to prevent it from running forever
    with patch('run_master_worker.MasterAgent') as mock_agent:
        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        run_master_worker.main()

        # Verify key methods were called
        mock_arcade_instance.open_scorecard.assert_called_once()
        mock_arcade_instance.make.assert_called_with("test_game", scorecard_id=mock_arcade_instance.open_scorecard.return_value)
        mock_agent.assert_called_once()
        mock_agent_instance.main.assert_called_once()
        mock_arcade_instance.close_scorecard.assert_called_once()
