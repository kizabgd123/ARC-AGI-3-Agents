from typing import Annotated, List, TypedDict, Union, Dict
from pydantic import BaseModel, Field
from agents.agent import AgentState as BaseAgentState

class ThinkingHistory(BaseModel):
    iteration: int
    plan: str
    critique: str
    revised_plan: str = ""

class AgentState(BaseAgentState):
    thinking_history: List[ThinkingHistory]
    iteration_count: int
    game_history: str  # Summary of previous moves

PLANNER_PROMPT = """You are the Planner for an ARC-AGI-3 agent. 
Your goal is to solve the puzzle by proposing the best next action.
Current Grid: {grid}
Available Actions: {actions}
Previous Critique (if any): {critique}
Game History: {game_history}

Propose an action and justify it."""

CRITIC_PROMPT = """You are the Critic for an ARC-AGI-3 agent.
Your goal is to find flaws in the proposed plan.
Proposed Plan: {plan}
Current Grid: {grid}
Game History: {game_history}

Be skeptical. Check if this action has failed before or if it ignores a visible pattern.
If the plan is good, respond with 'APPROVED'. Otherwise, provide specific feedback."""
