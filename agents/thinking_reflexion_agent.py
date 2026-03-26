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

import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

def get_model():
    return ChatOpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))

def planner(state: AgentState):
    model = get_model()
    critique = state["thinking_history"][-1].critique if state["thinking_history"] else "None"
    prompt = PLANNER_PROMPT.format(
        grid=state["data"].grid,
        actions=state["data"].available_actions,
        critique=critique,
        game_history=state["game_history"]
    )
    response = model.invoke([SystemMessage(content=prompt)])
    # In a real implementation, we'd parse the action from the response
    # For now, let's assume it returns a structured format or we parse it
    return {"iteration_count": state["iteration_count"]} # Placeholder for actual update

def critic(state: AgentState):
    model = get_model()
    last_plan = "..." # Extract from state
    prompt = CRITIC_PROMPT.format(
        plan=last_plan,
        grid=state["data"].grid,
        game_history=state["game_history"]
    )
    response = model.invoke([SystemMessage(content=prompt)])
    is_approved = "APPROVED" in response.content.upper()
    return {"thinking_history": state["thinking_history"] + [ThinkingHistory(iteration=state["iteration_count"], plan=last_plan, critique=response.content)]}

def should_continue(state: AgentState):
    if state["iteration_count"] >= 3:
        return END
    last_critique = state["thinking_history"][-1].critique if state["thinking_history"] else ""
    if "APPROVED" in last_critique.upper():
        return END
    return "planner"

workflow = StateGraph(AgentState)
workflow.add_node("planner", planner)
workflow.add_node("critic", critic)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "critic")
workflow.add_conditional_edges("critic", should_continue)

thinking_reflexion_agent = workflow.compile()
