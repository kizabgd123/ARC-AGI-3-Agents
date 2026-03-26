"""Structs module - re-exports from arcengine and defines additional structs."""

from typing import Any, Optional

from arcengine import FrameData as EngineFrameData
from arcengine import GameAction, GameState
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrameData(BaseModel):
    """Wrapper around arcengine FrameData with additional test-compatible fields."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    game_id: str = ""
    frame: list[list[list[int]]] = Field(default_factory=list)
    state: GameState = Field(default=GameState.NOT_PLAYED)
    levels_completed: int = 0
    win_levels: int = 0
    guid: Optional[str] = None
    full_reset: bool = False
    available_actions: list[GameAction] = Field(default_factory=list)
    action_input: Optional[Any] = None
    score: int = Field(default=0, ge=0, le=254)

    def is_empty(self) -> bool:
        """Check if the frame is empty."""
        return len(self.frame) == 0

    @classmethod
    def from_engine(cls, engine_frame: EngineFrameData) -> "FrameData":
        """Create a FrameData from an arcengine FrameData."""
        return cls(
            game_id=engine_frame.game_id,
            frame=[arr.tolist() for arr in engine_frame.frame]
            if engine_frame.frame
            else [],
            state=engine_frame.state,
            levels_completed=engine_frame.levels_completed,
            win_levels=engine_frame.win_levels,
            guid=engine_frame.guid,
            full_reset=engine_frame.full_reset,
            available_actions=engine_frame.available_actions,
            action_input=engine_frame.action_input,
        )


class ActionInput(BaseModel):
    """Represents an action input with ID, data, and optional reasoning."""

    id: GameAction = Field(default=GameAction.RESET)
    data: dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[dict[str, Any]] = None

    @field_validator("reasoning")
    @classmethod
    def validate_reasoning_json(
        cls, v: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Validate that reasoning is JSON serializable."""
        if v is not None:
            try:
                import json

                json.dumps(v)
            except (TypeError, ValueError) as e:
                raise ValueError(f"reasoning must be JSON serializable: {e}")
        return v


class Card(BaseModel):
    """Represents a scorecard for a single game."""

    game_id: str
    total_plays: int = 0
    scores: list[int] = Field(default_factory=list)
    states: list[GameState] = Field(default_factory=list)
    actions: list[int] = Field(default_factory=list)
    resets: list[int] = Field(default_factory=list)

    @property
    def started(self) -> bool:
        """Check if the game has started."""
        return self.total_plays > 0

    @property
    def score(self) -> Optional[int]:
        """Get the latest score."""
        return self.scores[-1] if self.scores else None

    @property
    def high_score(self) -> int:
        """Get the highest score."""
        return max(self.scores) if self.scores else 0

    @property
    def state(self) -> Optional[GameState]:
        """Get the latest state."""
        return self.states[-1] if self.states else None

    @property
    def action_count(self) -> int:
        """Get the latest action count."""
        return self.actions[-1] if self.actions else 0

    @property
    def total_actions(self) -> int:
        """Get total actions across all plays."""
        return sum(self.actions)

    @property
    def idx(self) -> int:
        """Get the index of the current play."""
        return self.total_plays - 1 if self.total_plays > 0 else -1


class Scorecard(BaseModel):
    """Represents a scorecard containing multiple game cards."""

    card_id: str
    api_key: str
    cards: dict[str, Card] = Field(default_factory=dict)

    @property
    def won(self) -> int:
        """Count number of games won."""
        return sum(1 for card in self.cards.values() if card.state == GameState.WIN)

    @property
    def played(self) -> int:
        """Count number of games played."""
        return len([c for c in self.cards.values() if c.started])

    @property
    def total_actions(self) -> int:
        """Get total actions across all games."""
        return sum(card.total_actions for card in self.cards.values())

    def get(
        self, game_id: Optional[str] = None
    ) -> dict[str, Any] | dict[str, dict[str, Any]]:
        """Get cards, optionally filtered by game_id."""
        if game_id:
            card = self.cards.get(game_id)
            if card:
                return {game_id: card.model_dump()}
            return {}
        return {gid: card.model_dump() for gid, card in self.cards.items()}

    def get_json_for(self, game_id: str) -> dict[str, Any]:
        """Get JSON representation for a specific game."""
        card = self.cards.get(game_id)
        if not card:
            return {}
        return {
            "won": self.won,
            "played": self.played,
            "cards": self.get(),
        }


__all__ = [
    "FrameData",
    "GameState",
    "GameAction",
    "ActionInput",
    "Card",
    "Scorecard",
]
