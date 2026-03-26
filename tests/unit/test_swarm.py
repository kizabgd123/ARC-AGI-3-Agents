from unittest.mock import Mock, patch

import pytest

from agents.agent import Playback
from agents.swarm import Swarm
from agents.templates.random_agent import Random


@pytest.mark.unit
class TestSwarmInitialization:
    def test_swarm_init(self):
        with patch.dict("os.environ", {"ARC_API_KEY": "test-api-key"}):
            swarm = Swarm(
                agent="random", ROOT_URL="https://example.com", games=["game1", "game2"]
            )

            assert swarm.agent_name == "random"
            assert swarm.ROOT_URL == "https://example.com"
            assert swarm.GAMES == ["game1", "game2"]
            assert swarm.agent_class == Random
            assert len(swarm.threads) == 0
            assert len(swarm.agents) == 0

            assert swarm.headers["X-API-Key"] == "test-api-key"
            assert swarm.headers["Accept"] == "application/json"


@pytest.mark.unit
class TestSwarmScorecard:
    @patch("arc_agi.Arcade.open_scorecard")
    def test_open_scorecard(self, mock_open):
        mock_open.return_value = "test-card-123"

        swarm = Swarm(agent="random", ROOT_URL="https://example.com", games=["game1"])

        card_id = swarm.open_scorecard()
        assert card_id == "test-card-123"

        mock_open.assert_called_once_with(tags=["agent", "random"])

    @patch("arc_agi.Arcade.close_scorecard")
    def test_close_scorecard(self, mock_close):
        mock_scorecard = Mock()
        mock_scorecard.card_id = "test-card-123"
        mock_close.return_value = mock_scorecard

        swarm = Swarm(agent="random", ROOT_URL="https://example.com", games=["game1"])

        scorecard = swarm.close_scorecard("test-card-123")
        assert isinstance(scorecard, Mock)
        assert swarm.card_id is None


@pytest.mark.unit
class TestSwarmAgentManagement:
    @patch("agents.swarm.Swarm.open_scorecard")
    @patch("agents.swarm.Swarm.close_scorecard")
    @patch("agents.swarm.Thread")
    @patch("arc_agi.Arcade.make")
    @patch("agents.recorder.Recorder.record")
    def test_agent_threading(
        self, mock_record, mock_make, mock_thread, mock_close, mock_open
    ):
        mock_open.return_value = "test-card-123"
        mock_scorecard = Mock()
        mock_scorecard.card_id = "test-card-123"
        mock_scorecard.model_dump.return_value = {
            "card_id": "test-card-123",
            "cards": {},
        }
        mock_close.return_value = mock_scorecard
        mock_make.return_value = Mock()

        mock_thread_instances = [Mock() for _ in range(3)]
        mock_thread.side_effect = mock_thread_instances

        swarm = Swarm(
            agent="random",
            ROOT_URL="https://example.com",
            games=["game1", "game2", "game3"],
        )

        assert swarm.agent_name == "random"
        assert swarm.agent_class == Random
        assert swarm.GAMES == ["game1", "game2", "game3"]

        with patch.object(Random, "main") as mock_agent_main:
            mock_agent_main.return_value = None

            swarm.main()

            assert mock_thread.call_count == 3
            for mock_thread_instance in mock_thread_instances:
                mock_thread_instance.start.assert_called_once()
                mock_thread_instance.join.assert_called_once()


@pytest.mark.unit
class TestSwarmCleanup:
    def test_cleanup(self):
        swarm = Swarm(
            agent="random", ROOT_URL="https://example.com", games=["game1", "game2"]
        )

        mock_agent1 = Mock()
        mock_agent2 = Mock()
        swarm.agents = [mock_agent1, mock_agent2]

        scorecard = Mock()
        swarm.cleanup(scorecard)

        mock_agent1.cleanup.assert_called_once_with(scorecard)
        mock_agent2.cleanup.assert_called_once_with(scorecard)

        mock_agent = Mock()
        swarm.agents = [mock_agent]

        swarm.cleanup()
        mock_agent.cleanup.assert_called_once_with(None)


@pytest.mark.unit
class TestSwarmTags:
    def test_default_tags(self):
        swarm = Swarm(agent="random", ROOT_URL="https://example.com", games=["game1"])
        assert swarm.tags == ["agent", "random"]

    def test_custom_tags(self):
        custom_tags = ["experiment1", "version2", "test"]
        swarm = Swarm(
            agent="random",
            ROOT_URL="https://example.com",
            games=["game1"],
            tags=custom_tags,
        )
        assert swarm.tags == custom_tags + ["agent", "random"]

    def test_empty_tags(self):
        swarm = Swarm(
            agent="random", ROOT_URL="https://example.com", games=["game1"], tags=[]
        )
        assert swarm.tags == ["agent", "random"]

    def test_playback_tags(self):
        from agents import AVAILABLE_AGENTS
        from agents.recorder import Recorder

        recordings = Recorder.list()
        if recordings:
            for recording in recordings:
                if recording in AVAILABLE_AGENTS:
                    parts = recording.split(".")
                    guid = parts[-3] if len(parts) >= 4 else "unknown"

                    swarm = Swarm(
                        agent=recording,
                        ROOT_URL="https://example.com",
                        games=["game1"],
                    )
                    assert "playback" in swarm.tags
                    assert guid in swarm.tags
                    assert swarm.agent_class == Playback
                    return
            pytest.skip("No recordings found in AVAILABLE_AGENTS")
        else:
            pytest.skip("No recordings found")
