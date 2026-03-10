import json
import logging
import math
import os
import re
import textwrap
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import openai
from arcengine import FrameData, GameAction, GameState
from openai import OpenAI as OpenAIClient

from ...agent import Agent
from .recording import RunRecord, StepRecord, StepUsage


class EmptyResponseError(Exception):
    """Raised when the API returns HTTP 200 but with null/empty choices."""


logger = logging.getLogger()


class ConversationRollingWindow(Agent):
    """An agent that maintains a growing conversation with an OpenAI model.

    Each turn appends a user message (frame data as text) and an assistant
    message (reasoning + chosen action). On context overflow, the oldest
    turns are trimmed from the front of the conversation.
    """

    MAX_ACTIONS: int = 20
    MAX_RETRIES: int = 3
    MAX_CONTEXT_LENGTH: int = 175000
    MODEL: str = "openai/gpt-5.2"
    ANIMATION_FRAME_COUNT: int = 3
    REASONING_EFFORT: Optional[str] = None
    # Empirically, rendered ARC grid payloads are close to 1 char per token.
    # Using 1.0 is intentionally conservative relative to observed runs.
    ESTIMATED_CHARS_PER_TOKEN: float = 1.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.conversation: list[dict[str, Any]] = []
        self.token_counter: int = 0
        self._client = OpenAIClient(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
        # Per-step recording
        self.step_counter: int = 0
        run_id = uuid.uuid4()
        self.run_dir = os.path.join("recordings", f"{self.name}.{run_id}")
        os.makedirs(self.run_dir, exist_ok=True)
        self.run_record = RunRecord(
            run_id=str(run_id),
            game_id=self.game_id,
            agent_name=self.name,
            model=self.MODEL,
            started_at=datetime.now(timezone.utc),
            run_dir=self.run_dir,
        )
        self._write_run_meta()

    @property
    def name(self) -> str:
        sanitized = self.MODEL.replace("/", "-").replace(":", "-")
        return f"{super().name}.{sanitized}.anim{self.ANIMATION_FRAME_COUNT}"

    # ── Prompts ──────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return textwrap.dedent("""\
            You are playing a game. Win in as few actions as possible. Reply with the exact action you choose.
        """)

    def _get_actions(self, latest_frame: FrameData) -> list[GameAction]:
        """Convert frame's available_actions (list[int]) to GameAction objects."""
        return [GameAction.from_id(a) for a in latest_frame.available_actions]

    def _build_available_actions_text(self, actions: list[GameAction]) -> str:
        lines = []
        for action in actions:
            if action.is_complex():
                lines.append(f"- {action.name} x y  (where x and y are integers 0-63)")
            else:
                lines.append(f"- {action.name}")
        return "\n".join(lines)

    # ── Frame rendering ──────────────────────────────────────────────────

    def interpolate_frames(
        self, frame_grids: list[list[list[int]]]
    ) -> list[list[list[int]]]:
        n = len(frame_grids)
        target = self.ANIMATION_FRAME_COUNT
        if n <= target:
            return frame_grids
        if target == 1:
            return [frame_grids[-1]]
        indices = [round(i * (n - 1) / (target - 1)) for i in range(target)]
        return [frame_grids[i] for i in indices]

    def build_frame_content(self, latest_frame: FrameData) -> str:
        grids = self.interpolate_frames(latest_frame.frame)

        parts = [
            f"State: {latest_frame.state.name}\n"
            f"Levels completed: {latest_frame.levels_completed}\n"
            f"Grids: {len(grids)} of {len(latest_frame.frame)} animation frames",
        ]

        for i, grid in enumerate(grids):
            grid_text = f"Grid {i}:\n" + "\n".join(f"  {row}" for row in grid)
            parts.append(grid_text)

        actions_text = self._build_available_actions_text(
            self._get_actions(latest_frame)
        )
        parts.append(
            f"Available actions:\n{actions_text}\n\nChoose exactly one action."
        )

        return "\n\n".join(parts)

    # ── Action parsing ───────────────────────────────────────────────────

    def _parse_action(
        self, text: str, available_actions: list[GameAction]
    ) -> Optional[GameAction]:
        """Parse the last mentioned action from the assistant's response."""
        text_upper = text.upper()
        candidates: list[tuple[int, GameAction]] = []

        for action in available_actions:
            if action.is_complex():
                pattern = rf"{action.name}\s*[:(]?\s*(\d+)\s*[,\s]\s*(\d+)\s*\)?"
                for match in re.finditer(pattern, text_upper):
                    a = GameAction.from_name(action.name)
                    x = max(0, min(int(match.group(1)), 63))
                    y = max(0, min(int(match.group(2)), 63))
                    a.set_data({"x": x, "y": y})
                    candidates.append((match.start(), a))
            else:
                start = 0
                while True:
                    pos = text_upper.find(action.name, start)
                    if pos == -1:
                        break
                    candidates.append((pos, GameAction.from_name(action.name)))
                    start = pos + len(action.name)

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0])
        return candidates[-1][1]

    # ── Per-step recording ──────────────────────────────────────────────

    @staticmethod
    def _format_parsed_action(action: GameAction) -> str | dict[str, Any]:
        """Format a parsed action for recording. Complex actions include coordinates."""
        if action.is_complex():
            return {"action": action.name, **action.data}
        return str(action.name)

    def _write_run_meta(self) -> None:
        path = os.path.join(self.run_dir, "run_meta.json")
        with open(path, "w") as f:
            f.write(self.run_record.model_dump_json(indent=2))

    def _save_diagnostic(self, response: Any) -> None:
        """Dump a raw API response to a diagnostic file for post-mortem debugging."""
        filename = os.path.join(
            self.run_dir,
            f"diagnostic_step_{self.step_counter + 1}_{int(time.time())}.json",
        )
        try:
            raw = (
                response.model_dump()
                if hasattr(response, "model_dump")
                else repr(response)
            )
            with open(filename, "w") as f:
                json.dump(raw, f, indent=2, default=str)
        except Exception as exc:
            with open(filename, "w") as f:
                f.write(f"Failed to serialize response: {exc}\nrepr: {repr(response)}")
        logger.warning(f"Saved diagnostic response to {filename}")

    def _save_step(self, step: StepRecord) -> None:
        self.step_counter += 1
        self.run_record.total_usage = self.run_record.total_usage + step.usage
        self.run_record.total_steps = self.step_counter
        filename = os.path.join(self.run_dir, f"step_{self.step_counter:03d}.json")
        with open(filename, "w") as f:
            f.write(step.model_dump_json(indent=2))
        self._write_run_meta()
        logger.info(f"Saved step {self.step_counter} to {filename}")

    # ── Core loop ────────────────────────────────────────────────────────

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        # Bootstrap: first call sends RESET without an API call
        if not self.conversation:
            self.conversation.append(
                {"role": "system", "content": self._build_system_prompt()}
            )
            self.conversation.append(
                {"role": "assistant", "content": "RESET - Starting the game."}
            )
            self._save_step(
                StepRecord(
                    step=self.step_counter + 1,
                    timestamp=datetime.now(timezone.utc),
                    duration_seconds=0.0,
                    model=self.MODEL,
                    messages_sent=list(self.conversation),
                    assistant_response="RESET - Starting the game.",
                    parsed_action="RESET",
                )
            )
            return GameAction.RESET

        # Handle NOT_PLAYED / GAME_OVER states that need a RESET
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self.conversation.append(
                {"role": "user", "content": f"State: {latest_frame.state.name}"}
            )
            self.conversation.append(
                {"role": "assistant", "content": "RESET - Restarting the game."}
            )
            self._save_step(
                StepRecord(
                    step=self.step_counter + 1,
                    timestamp=datetime.now(timezone.utc),
                    duration_seconds=0.0,
                    model=self.MODEL,
                    messages_sent=list(self.conversation),
                    assistant_response="RESET - Restarting the game.",
                    parsed_action="RESET",
                )
            )
            return GameAction.RESET

        # Normal turn: append frame, call the model, parse action
        self.conversation.append(
            {"role": "user", "content": self.build_frame_content(latest_frame)}
        )

        actions = self._get_actions(latest_frame)
        assistant_text = ""
        step_usage = StepUsage()
        empty_response_count = 0
        start = time.monotonic()
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self._call_with_overflow_handling()
            except EmptyResponseError:
                empty_response_count += 1
                logger.warning(
                    f"Empty API response "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1})."
                )
                continue

            step_usage = step_usage + StepUsage.from_response(response)
            assistant_text = response.choices[0].message.content or ""
            logger.info(f"Assistant response: {assistant_text[:200]}")

            action = self._parse_action(assistant_text, actions)
            if action is not None:
                self.conversation.append(
                    {"role": "assistant", "content": assistant_text}
                )
                logger.info(f"Parsed action: {self._format_parsed_action(action)}")
                duration = time.monotonic() - start
                self._save_step(
                    StepRecord(
                        step=self.step_counter + 1,
                        timestamp=datetime.now(timezone.utc),
                        duration_seconds=round(duration, 3),
                        model=self.MODEL,
                        messages_sent=list(self.conversation),
                        assistant_response=assistant_text,
                        parsed_action=self._format_parsed_action(action),
                        usage=step_usage,
                        retries=attempt,
                    )
                )
                return action

            logger.warning(
                f"No action found in response "
                f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1}). Retrying."
            )

        # All attempts returned empty responses — no fallback, propagate the error
        if empty_response_count == self.MAX_RETRIES + 1:
            raise EmptyResponseError(
                f"All {self.MAX_RETRIES + 1} attempts returned empty API responses. "
                f"Diagnostics saved to {self.run_dir}"
            )

        # Exhausted retries due to parse failures — fall back
        self.conversation.append({"role": "assistant", "content": assistant_text})
        logger.error(
            f"Failed to parse action after {self.MAX_RETRIES + 1} attempts. "
            "Defaulting to ACTION5."
        )
        duration = time.monotonic() - start
        self._save_step(
            StepRecord(
                step=self.step_counter + 1,
                timestamp=datetime.now(timezone.utc),
                duration_seconds=round(duration, 3),
                model=self.MODEL,
                messages_sent=list(self.conversation),
                assistant_response=assistant_text,
                parsed_action="ACTION5 (fallback)",
                usage=step_usage,
                retries=self.MAX_RETRIES + 1,
            )
        )
        return GameAction.ACTION5

    # ── Token estimation & proactive trimming ─────────────────────────

    def _estimate_conversation_tokens(self) -> int:
        """Estimate token count using an empirically calibrated chars-per-token ratio."""
        total_chars = sum(len(m.get("content", "")) for m in self.conversation)
        return math.ceil(total_chars / self.ESTIMATED_CHARS_PER_TOKEN)

    def _trim_to_fit_context(self) -> None:
        """Proactively trim oldest turns if estimated tokens exceed MAX_CONTEXT_LENGTH."""
        estimated = self._estimate_conversation_tokens()
        while estimated > self.MAX_CONTEXT_LENGTH:
            if not self._trim_oldest_turn():
                logger.warning(
                    f"Cannot trim further but estimated tokens ({estimated}) "
                    f"still exceed MAX_CONTEXT_LENGTH ({self.MAX_CONTEXT_LENGTH})."
                )
                break
            estimated = self._estimate_conversation_tokens()
            logger.info(
                f"Proactive context trim: ~{estimated} tokens "
                f"(limit {self.MAX_CONTEXT_LENGTH}), "
                f"{len(self.conversation)} messages remaining."
            )

    # ── OpenAI call with context-overflow trimming ───────────────────────

    def _call_with_overflow_handling(self) -> Any:
        self._trim_to_fit_context()

        while True:
            create_kwargs: dict[str, Any] = {
                "model": self.MODEL,
                "messages": self.conversation,
            }
            if self.REASONING_EFFORT is not None:
                create_kwargs["reasoning_effort"] = self.REASONING_EFFORT

            try:
                response = self._client.chat.completions.create(**create_kwargs)
            except openai.BadRequestError as e:
                error_str = str(e).lower()
                is_context_error = (
                    "context" in error_str
                    or "token" in error_str
                    or "length" in error_str
                )
                if is_context_error and self._trim_oldest_turn():
                    logger.info(
                        f"Context overflow: trimmed oldest turn. "
                        f"Conversation now has {len(self.conversation)} messages."
                    )
                    continue
                raise

            # Guard against null/empty choices (200 OK but no usable content)
            if not response.choices:
                self._save_diagnostic(response)
                if self._trim_oldest_turn():
                    logger.warning(
                        f"Empty choices in response. "
                        f"Trimmed context to {len(self.conversation)} messages. Retrying."
                    )
                    continue
                raise EmptyResponseError(
                    f"API returned 200 with empty choices and context cannot be trimmed further. "
                    f"Diagnostics saved to {self.run_dir}"
                )

            if response.usage:
                self.track_tokens(response.usage.total_tokens)
            return response

    def _trim_oldest_turn(self) -> bool:
        """Remove the oldest user/assistant pair, preserving the system message."""
        # Find the first user message (skips system prompt and bootstrap assistant)
        for i in range(1, len(self.conversation)):
            if self.conversation[i]["role"] == "user":
                # Remove this user message and its assistant reply if present
                end = i + 1
                if (
                    end < len(self.conversation)
                    and self.conversation[end]["role"] == "assistant"
                ):
                    end += 1
                # Keep at least 2 messages (system + current user turn)
                if len(self.conversation) - (end - i) < 2:
                    return False
                removed = self.conversation[i:end]
                self.conversation = self.conversation[:i] + self.conversation[end:]
                logger.info(
                    f"Trimmed oldest turn: {[m.get('role', '?') for m in removed]}"
                )
                return True
        return False

    # ── Token tracking & cleanup ─────────────────────────────────────────

    def track_tokens(self, tokens: int, message: str = "") -> None:
        self.token_counter += tokens
        if hasattr(self, "recorder") and not self.is_playback:
            self.recorder.record(
                {
                    "tokens": tokens,
                    "total_tokens": self.token_counter,
                    "conversation_length": len(self.conversation),
                    "assistant": message,
                }
            )
        logger.info(
            f"Tokens: {tokens}, total: {self.token_counter}, "
            f"messages: {len(self.conversation)}"
        )

    def cleanup(self, *args: Any, **kwargs: Any) -> None:
        if self._cleanup:
            now = datetime.now(timezone.utc)
            self.run_record.ended_at = now
            self.run_record.duration_seconds = round(
                (now - self.run_record.started_at).total_seconds(), 3
            )
            if self.state is GameState.WIN:
                self.run_record.outcome = "WIN"
            elif self.state is GameState.GAME_OVER:
                self.run_record.outcome = "GAME_OVER"
            elif self.action_counter >= self.MAX_ACTIONS:
                self.run_record.outcome = "MAX_ACTIONS"
            self._write_run_meta()

            if hasattr(self, "recorder") and not self.is_playback:
                self.recorder.record(
                    {
                        "system_prompt": self._build_system_prompt(),
                        "final_conversation_length": len(self.conversation),
                        "total_tokens": self.token_counter,
                    }
                )
        super().cleanup(*args, **kwargs)
