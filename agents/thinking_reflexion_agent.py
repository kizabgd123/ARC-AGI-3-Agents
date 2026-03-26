import json
from typing import List, TypedDict
from pydantic import BaseModel
from agents.agent import Agent, FrameData
from arcengine import GameAction, GameState
import os
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

class ThinkingHistory(BaseModel):
    iteration: int
    plan: str
    critique: str
    revised_plan: str = ""

class AgentState(TypedDict):
    data: FrameData
    thinking_history: List[ThinkingHistory]
    iteration_count: int
    game_history: str
    plan: str
    critique: str
    action: str

PLANNER_PROMPT = """You are the Planner for an ARC-AGI-3 agent. 
Your goal is to solve the puzzle by proposing the best next action.
Current Grid: {grid}
Available Actions: {actions}
Previous Critique (if any): {critique}
Game History: {game_history}

Your output MUST be a JSON object with two keys: "plan" and "action".
The "plan" should be your reasoning, and the "action" must be one of the available actions.
Example:
{{
  "plan": "The grid has a blue square at the top. I should move it down.",
  "action": "MOVE_DOWN"
}}
"""

CRITIC_PROMPT = """You are the Critic for an ARC-AGI-3 agent.
Your goal is to find flaws in the proposed plan.
Proposed Plan: {plan}
Current Grid: {grid}
Game History: {game_history}

Be skeptical. Check if this action has failed before or if it ignores a visible pattern.
If the plan is good, respond with 'APPROVED'. Otherwise, provide specific feedback.
Your output MUST be a JSON object with one key: "critique".
Example:
{{
  "critique": "The proposed action MOVE_DOWN will move the square out of the grid."
}}
"""

def get_model():
    return ChatGoogleGenerativeAI(model="gemini-3-pro-preview", google_api_key=os.getenv("GEMINI_API_KEY"))

def planner(state: AgentState):
    model = get_model()
    critique = state.get("critique", "None")
    prompt = PLANNER_PROMPT.format(
        grid=state["data"].frame,
        actions=[GameAction.from_id(a).name for a in state["data"].available_actions],
        critique=critique,
        game_history=state.get("game_history", "")
    )
    response = model.invoke([HumanMessage(content=prompt)])
    try:
        plan_json = json.loads(response.content)
    except json.JSONDecodeError:
        plan_json = {"plan": response.content, "action": "wait"}
        
    return {"plan": plan_json.get("plan", ""), "action": plan_json.get("action", "wait"), "iteration_count": state.get("iteration_count", 0) + 1}

def critic(state: AgentState):
    model = get_model()
    last_plan = state.get("plan", "")
    prompt = CRITIC_PROMPT.format(
        plan=last_plan,
        grid=state["data"].frame,
        game_history=state.get("game_history", "")
    )
    response = model.invoke([HumanMessage(content=prompt)])
    try:
        critique_json = json.loads(response.content)
        critique = critique_json["critique"]
    except (json.JSONDecodeError, KeyError):
        critique = response.content

    history = state.get("thinking_history", [])
    history.append(ThinkingHistory(iteration=state.get("iteration_count", 0), plan=last_plan, critique=critique))
    return {"critique": critique, "thinking_history": history}

def should_continue(state: AgentState):
    if state.get("iteration_count", 0) >= 3:
        return END
    critique = state.get("critique", "")
    if "APPROVED" in critique.upper():
        return END
    return "planner"

class ThinkingReflexionAgent(Agent):
    MAX_ACTIONS = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workflow = StateGraph(AgentState)
        workflow.add_node("planner", planner)
        workflow.add_node("critic", critic)

        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "critic")
        workflow.add_conditional_edges("critic", should_continue)

        self.graph = workflow.compile()
        self.game_history = ""

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state in [GameState.WIN, GameState.GAME_OVER]

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        initial_state = AgentState(
            data=latest_frame,
            thinking_history=[],
            iteration_count=0,
            game_history=self.game_history,
            plan="",
            critique="",
            action="wait"
        )
        
        final_state = self.graph.invoke(initial_state)

        action_name = final_state.get("action", "wait")
        
        try:
            game_action = GameAction[action_name]
        except KeyError:
            game_action = GameAction.WAIT

        self.game_history += f"\nFrame {latest_frame.frame_number}: Action {game_action.name} taken. Result: {latest_frame.result}"

        return game_action
