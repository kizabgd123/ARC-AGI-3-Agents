import os
import shutil

import pytest

from agents.structs import FrameData, GameAction, GameState


def get_test_recordings_dir():
    conftest_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(conftest_dir, "recordings")


@pytest.fixture(scope="session", autouse=True)
def clean_test_recordings():
    test_recordings_dir = get_test_recordings_dir()

    os.environ["RECORDINGS_DIR"] = test_recordings_dir

    if os.path.exists(test_recordings_dir):
        shutil.rmtree(test_recordings_dir)
    os.makedirs(test_recordings_dir, exist_ok=True)

    yield test_recordings_dir


@pytest.fixture
def temp_recordings_dir(clean_test_recordings):
    test_recordings_dir = get_test_recordings_dir()

    os.makedirs(test_recordings_dir, exist_ok=True)

    original_dir = os.environ.get("RECORDINGS_DIR")
    os.environ["RECORDINGS_DIR"] = test_recordings_dir

    yield test_recordings_dir

    if original_dir:
        os.environ["RECORDINGS_DIR"] = original_dir
    else:
        os.environ.pop("RECORDINGS_DIR", None)


@pytest.fixture
def sample_frame():
    return FrameData(
        game_id="test-game",
        frame=[[[1, 2], [3, 4]]],
        state=GameState.NOT_FINISHED,
        score=5,
    )


@pytest.fixture
def mock_arc_env():
    """Create a mock arc environment for testing."""
    from unittest.mock import MagicMock

    mock_env = MagicMock()
    mock_env.observation_space = FrameData(
        game_id="test-game",
        frame=[[[1, 2], [3, 4]]],
        state=GameState.NOT_FINISHED,
        levels_completed=0,
        available_actions=[GameAction.ACTION1, GameAction.ACTION2, GameAction.RESET],
    )

    def mock_step(action, data=None, reasoning=None):
        return FrameData(
            game_id="test-game",
            frame=[[[1, 2], [3, 4]]],
            state=GameState.NOT_FINISHED,
            levels_completed=0,
            available_actions=[
                GameAction.ACTION1,
                GameAction.ACTION2,
                GameAction.RESET,
            ],
        )

    mock_env.step = mock_step
    return mock_env


@pytest.fixture
def use_env_vars(monkeypatch):
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if not os.environ.get("ARC_API_KEY"):
        monkeypatch.setenv("ARC_API_KEY", "test-key")
    if not os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    if not os.environ.get("SCHEME"):
        monkeypatch.setenv("SCHEME", "https")
    if not os.environ.get("HOST"):
        monkeypatch.setenv("HOST", "three.arcprize.org")
    if not os.environ.get("PORT"):
        monkeypatch.setenv("PORT", "443")
