import json
import logging
import time
from typing import Dict, List, TypedDict

from arcengine import GameAction, GameState
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from agents.agent import Agent, FrameData
from decision_engine import DecisionEngine
from decision_engine.grid_parser import GridParser
from utils.gemini_rotator import get_rotated_gemini_model

logger = logging.getLogger(__name__)


class ThinkingHistory(BaseModel):
    iteration: int
    plan: str
    critique: str


class AgentState(TypedDict):
    data: FrameData
    thinking_history: List[ThinkingHistory]
    iteration_count: int
    game_history: str
    plan: str
    critique: str
    action: str


PLANNER_PROMPT = """You are the Planner for an ARC-AGI-3 agent playing a puzzle game.

GAME RULES:
- You control a player character on a 64x64 grid
- ACTION1: Move Up, ACTION2: Move Down, ACTION3: Move Left, ACTION4: Move Right
- ACTION5: Interact/Confirm, ACTION6: Click at coordinates (x, y)
- Goal: Transform the key (bottom-left) to match the exit door (center), then touch the door
- Walls (INT<10>) block movement. Walkable floor is INT<8>
- You have limited energy (shown on row 2). Touch energy pills (INT<6>) to refill
- Use rotators (INT<9>) to change key shape/color

GRID INTERPRETATION:
- Grid is a bird's-eye view. Each cell is INT<0-15> representing colors
- Player is a 3x3 square. Objects are 2x2 to 6x6 squares
- Focus on: player position, nearby objects, visible goals

Current Grid (focus on relevant objects near player):
{grid}

Available Actions: {actions}

Previous Critique: {critique}

Game History (recent actions and outcomes):
{game_history}

Think step-by-step:
1. Where is the player relative to key objects?
2. What action moves toward the goal?
3. Could this action fail (wall, out of bounds)?

Output JSON: {{"plan": "your reasoning", "action": "ACTION_NAME"}}
"""

CRITIC_PROMPT = """You are the Critic for an ARC-AGI-3 agent. Your job is to REJECT bad plans.

VALIDATION CHECKLIST (reject if ANY fail):
1. ACTION VALIDITY: Is the proposed action in available_actions?
2. SPATIAL VALIDITY: Does the plan correctly identify object positions? (Key is bottom-left, door is center)
3. FEASIBILITY: Would this action succeed given the grid? (No wall blocking, not out of bounds)
4. CONSISTENCY: Does this action align with the stated goal? (Getting key → door)
5. HISTORY CHECK: Has this exact action failed in the last 3 frames with same outcome?

Proposed Plan: {plan}
Current Grid: {grid}
Game History:
{game_history}

Available Actions: {actions}

Respond with JSON:
{{
  "verdict": "APPROVED" or "REJECTED",
  "failed_checks": ["SPATIAL_VALIDITY", ...],  # empty if approved
  "critique": "Specific feedback. If rejected, explain which check failed and why."
}}
"""


def get_model():
    """Returns a rotated Gemini model instance."""
    return get_rotated_gemini_model(model_name="gemini-3-flash-preview")


def planner(state: AgentState):
    model = get_model()
    critique = state.get("critique", "None")
    prompt = PLANNER_PROMPT.format(
        grid=summarize_grid(state["data"]),  # Summarized, not raw
        actions=[GameAction.from_id(a).name for a in state["data"].available_actions],
        critique=critique,
        game_history=state.get("game_history", ""),
    )

    # Retry loop with key rotation for 429s
    for attempt in range(5):
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            break
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                print(f"DEBUG: 429 in planner (attempt {attempt + 1}), rotating key...")
                model = get_model()
            else:
                raise e

    content = response.content
    if isinstance(content, list):
        content = "".join(
            [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        )

    try:
        plan_json = json.loads(content)
        action_name = plan_json.get("action", "RESET").upper().strip()
        # Normalize action name
        action_name = action_name.replace(" ", "_").replace("-", "_")
        # Validate action name
        valid_actions = [a.name for a in GameAction]
        if action_name not in valid_actions:
            logger.warning(f"Invalid action '{action_name}', defaulting to RESET")
            action_name = "RESET"
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Planner JSON parse failed: {e}. Content: {str(content)[:200]}")
        plan_json = {"plan": str(content), "action": "RESET"}
        action_name = "RESET"

    return {
        "plan": plan_json.get("plan", ""),
        "action": action_name,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


def critic(state: AgentState):
    model = get_model()
    last_plan = state.get("plan", "")
    prompt = CRITIC_PROMPT.format(
        plan=last_plan,
        grid=state["data"].frame,
        game_history=state.get("game_history", ""),
        actions=[GameAction.from_id(a).name for a in state["data"].available_actions],
    )

    # Retry loop with key rotation for 429s
    for attempt in range(5):
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            break
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                print(f"DEBUG: 429 in critic (attempt {attempt + 1}), rotating key...")
                model = get_model()
            else:
                raise e

    content = response.content
    if isinstance(content, list):
        content = "".join(
            [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        )

    try:
        critique_json = json.loads(content)
        # Validate required fields
        if "verdict" not in critique_json:
            critique_json["verdict"] = "REJECTED"
            critique_json["critique"] = "Invalid critique format - missing verdict"
        if critique_json.get("verdict", "").upper() != "APPROVED":
            critique = f"REJECTED: {critique_json.get('critique', '')}"
        else:
            critique = "APPROVED"
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Critic JSON parse failed: {e}")
        critique = "REJECTED: Critic failed to produce valid JSON"

    history = state.get("thinking_history", [])
    history.append(
        ThinkingHistory(
            iteration=state.get("iteration_count", 0), plan=last_plan, critique=critique
        )
    )
    # Trim thinking history to prevent unbounded growth
    if len(history) > 5:
        history = history[-5:]
    return {"critique": critique, "thinking_history": history}


def find_player_position(frame_data: FrameData) -> tuple[int, int] | None:
    """Find player position in grid (simplified - would need full detection)."""
    if not frame_data or not frame_data.frame:
        return None
    # Look for player pattern (3x3 of specific colors)
    # Simplified: assume player is at center for now
    return (30, 30)  # Placeholder


def build_game_history(frames: list[FrameData]) -> str:
    """Build history with action outcomes and grid deltas."""
    history_list = []

    for i in range(1, len(frames)):
        prev_frame = frames[i - 1]
        curr_frame = frames[i]
        action = (
            prev_frame.action_input.id.name
            if hasattr(prev_frame, "action_input") and prev_frame.action_input
            else "UNKNOWN"
        )

        # Compute simple delta (player position change)
        prev_pos = find_player_position(prev_frame)
        curr_pos = find_player_position(curr_frame)

        if prev_pos and curr_pos:
            delta = (curr_pos[0] - prev_pos[0], curr_pos[1] - prev_pos[1])
            outcome = f"moved {delta}"
        else:
            outcome = "no visible change"

        # Check if state changed
        if curr_frame.state != prev_frame.state:
            outcome += f", state changed to {curr_frame.state.name}"

        history_list.append(f"Frame {i}: {action} → {outcome}")

    # Keep only recent
    if len(history_list) > 10:
        history_list = history_list[-10:]

    return "\n".join(history_list) if history_list else "No history (first turn)"


def summarize_grid(frame_data) -> str:
    """Extract key objects from grid, don't dump raw integers."""
    grid = frame_data.frame[0] if frame_data.frame else []
    if not grid:
        return "Empty grid"

    # Find player (3x3 of 0s and 4s typically)
    # Find key (6x6 in bottom-left)
    # Find door (4x4 with INT<11> border)
    # Find nearby walls (INT<10>)

    summary = []
    summary.append(f"Grid size: {len(grid)}x{len(grid[0])}")

    # Scan for objects (simplified - would need full object detection)
    # For now, just note player position and nearby cells
    player_row, player_col = 30, 30  # Would need actual detection
    nearby = grid[player_row - 2 : player_row + 3][player_col - 2 : player_col + 3]

    summary.append(f"Player area (5x5): {nearby}")
    summary.append(f"Key visible in bottom-left: {grid[58:64][0:6]}")
    summary.append(f"Door visible in center: {grid[30:34][30:34]}")

    return "\n".join(summary)


def should_continue(state: AgentState):
    # Allow up to 7 iterations for complex puzzles
    if state.get("iteration_count", 0) > 7:
        return END
    critique = state.get("critique", "")
    if "APPROVED" in critique.upper():
        return END
    return "planner"


class ThinkingReflexionAgent(Agent):
    MAX_ACTIONS = 80
    MAX_HISTORY_ENTRIES = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workflow = StateGraph(AgentState)
        workflow.add_node("planner", planner)
        workflow.add_node("critic", critic)

        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "critic")
        workflow.add_conditional_edges("critic", should_continue)

        self.graph = workflow.compile()
        self.game_history = []
        self.persistent_thoughts = []  # Across turns!
        self.persistent_plan = ""

        # Initialize Decision Engine and Grid Parser
        self.decision_engine = DecisionEngine(
            veto_config_path="config/veto_criteria.json",
            scoring_config_path="config/scoring_metrics.json",
            audit_log_path="logs/decision_audit.jsonl",
        )
        self.grid_parser = GridParser(grid_size=64)

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state in [GameState.WIN, GameState.GAME_OVER]

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        start_time = time.time()
        game_history_str = build_game_history(frames)

        # ========== DECISION ENGINE: VETO → SCORING → PREPORUKA ==========

        # Get available actions from LLM
        initial_state = AgentState(
            data=latest_frame,
            thinking_history=self.persistent_thoughts[-5:],  # Keep last 5
            iteration_count=0,
            game_history=game_history_str,
            plan=self.persistent_plan,  # Continue from last plan
            critique="",
            action="RESET",
        )

        try:
            final_state = self.graph.invoke(initial_state)
        except Exception as e:
            logger.error(f"LangGraph workflow failed: {e}")
            return GameAction.RESET

        # Save for next turn
        self.persistent_thoughts = final_state.get("thinking_history", [])
        self.persistent_plan = final_state.get("plan", "")

        # Log metrics
        elapsed = time.time() - start_time
        iterations = final_state.get("iteration_count", 0)
        critique = final_state.get("critique", "")

        logger.info(
            f"METRICS: game={self.game_id}, frame={len(frames)}, "
            f"iterations={iterations}, elapsed={elapsed:.2f}s, "
            f"critique_len={len(critique)}, action={final_state.get('action')}"
        )

        # Track planner failures
        if final_state.get("action") == "RESET":
            logger.warning(
                f"PLANNER_FAILURE: game={self.game_id}, frame={len(frames)}, "
                f"reason=invalid_action_or_json_parse_failure"
            )

        # Track critic approval rate
        if "APPROVED" in critique.upper():
            logger.info(f"CRITIC_APPROVED: game={self.game_id}, frame={len(frames)}")
        else:
            logger.info(
                f"CRITIC_REJECTED: game={self.game_id}, frame={len(frames)}, "
                f"critique={critique[:100]}"
            )

        llm_action = final_state.get("action", "RESET")

        # Build candidate actions (LLM suggestion + alternatives)
        candidate_actions = [llm_action, "ACTION1", "ACTION2", "ACTION3", "ACTION4"]
        candidate_actions = list(set(candidate_actions))[:6]  # Dedupe and limit

        # Extract game state for decision engine
        game_state = self._extract_game_state(latest_frame, frames)

        # VETO PHASE: Filter out dangerous/invalid actions
        survivors, vetoed = self.decision_engine.run_veto_checks(
            candidate_actions, game_state
        )

        # SCORING PHASE: Score surviving actions
        scores = self.decision_engine.score_actions(survivors, game_state)

        # PREPORUKA PHASE: Make final recommendation
        recommended_action, decision_reason = self.decision_engine.make_recommendation(
            survivors, scores, vetoed
        )

        # AUDIT PHASE: Log decision
        scenario_id = f"{self.game_id}_{self.action_counter}"
        self.decision_engine.log_decision(
            scenario_id=scenario_id,
            context=f"LockSmith level {latest_frame.levels_completed}",
            candidates=candidate_actions,
            vetoed=vetoed,
            scores=scores,
            recommended=recommended_action,
            reason=decision_reason,
        )

        logger.info(
            f"DECISION: {recommended_action} (reason={decision_reason.value}, "
            f"survivors={len(survivors)}/{len(candidate_actions)}, "
            f"score={scores.get(recommended_action, 0):.1f})"
        )

        # Update decision engine game state
        game_action = GameAction[recommended_action]
        self.decision_engine.update_game_state(
            recommended_action,
            success=True,
            current_position=game_state.get("player_position"),
        )

        # Update game history with correct FrameData fields
        frame_idx = len(frames) - 1
        history_entry = f"Frame {frame_idx}: Action {game_action.name} taken. Result: {latest_frame.state.name}"
        self.game_history.append(history_entry)

        # Trim history if needed
        if len(self.game_history) > self.MAX_HISTORY_ENTRIES:
            self.game_history = self.game_history[-self.MAX_HISTORY_ENTRIES :]

        return game_action

    def _extract_game_state(
        self, latest_frame: FrameData, frames: list[FrameData]
    ) -> Dict:
        """Extract relevant game state for decision engine using GridParser."""
        try:
            # Parse grid to extract game state
            grid = latest_frame.frame
            game_state = self.grid_parser.get_game_state_for_decision_engine(
                grid, frames
            )

            logger.debug(
                f"Game state: player={game_state['player_position']}, "
                f"energy={game_state['energy']}, door_dist={game_state['door_distance']:.1f}, "
                f"key_matches={game_state['key_matches_door']}"
            )

            return game_state
        except Exception as e:
            logger.error(f"Grid parsing failed: {e}")
            # Fallback to default state
            return {
                "player_position": (32, 32),
                "energy": 25,
                "energy_pill_visible": False,
                "energy_pill_distance": 100.0,
                "key_matches_door": False,
                "door_position": None,
                "door_distance": 100.0,
                "rotator_position": None,
                "rotator_distance": 100.0,
                "nearby_walls": [],
                "wall_distance": 10,
                "last_action": None,
                "grid_bounds": (0, 63, 0, 63),
            }

    def cleanup(self, scorecard=None) -> None:
        """Cleanup and reset decision engine for new game."""
        super().cleanup(scorecard)
        self.decision_engine.reset_game_state()
        logger.info("Decision Engine game state reset")
