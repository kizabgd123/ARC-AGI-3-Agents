import json
import logging
import os
import textwrap
from typing import Any, Optional

from arcengine import FrameData, GameAction, GameState
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ToolUseBlock, ResultMessage

from ..agent import Agent
from ..claude_tools import create_arc_tools_server
from ..claude_recorder import ClaudeCodeRecorder

logger = logging.getLogger()


class ClaudeCodeAgent(Agent):
    MAX_ACTIONS: int = 80
    MODEL: str = "claude-sonnet-4-5-20250929"
    
    token_counter: int
    step_counter: int
    mcp_server: Any
    latest_reasoning: str
    claude_recorder: Optional[ClaudeCodeRecorder]
    captured_messages: list[Any]
    current_prompt: str
    result_message: Optional[Any]
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.token_counter = 0
        self.step_counter = 0
        self.latest_reasoning = ""
        self.mcp_server = create_arc_tools_server(self)
        self.captured_messages = []
        self.current_prompt = ""
        self.result_message = None
        
        if kwargs.get("record", False):
            self.claude_recorder = ClaudeCodeRecorder(
                game_id=kwargs.get("game_id", "unknown"),
                agent_name=self.agent_name
            )
        else:
            self.claude_recorder = None
        
        logging.getLogger("anthropic").setLevel(logging.CRITICAL)
        logging.getLogger("httpx").setLevel(logging.CRITICAL)
    
    @property
    def name(self) -> str:
        sanitized_model_name = self.MODEL.replace("/", "-").replace(":", "-")
        return f"{super().name}.{sanitized_model_name}"
    
    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return any([
            latest_frame.state is GameState.WIN,
        ])
    
    def build_game_prompt(self, latest_frame: FrameData) -> str:
        if latest_frame.frame and len(latest_frame.frame) > 0:
            first_layer = latest_frame.frame[0]
            grid_str = "\n".join(
                [" ".join([str(cell).rjust(2) for cell in row]) for row in first_layer]
            )
        else:
            grid_str = "No grid data available"
        
        available_actions_str = ", ".join(
            [f"ACTION{a}" if a > 0 else "RESET" for a in latest_frame.available_actions]
        )
        
        prompt = textwrap.dedent(f"""
            You are playing an ARC-AGI-3 game. Your goal is to solve the puzzle.
            
            Game: {self.game_id}
            Current State: {latest_frame.state.value}
            Levels Completed: {latest_frame.levels_completed}
            Available Actions: {available_actions_str}
            
            Current Grid (64x64, values 0-15):
            {grid_str}
            
            You have access to the following tools:
            - reset_game: Reset the game to start over
            - action1_move_up: Execute ACTION1
            - action2_move_down: Execute ACTION2
            - action3_move_left: Execute ACTION3
            - action4_move_right: Execute ACTION4
            - action5_interact: Execute ACTION5
            - action6_click: Execute ACTION6 with coordinates (x, y) in range 0-63
            - action7_undo: Execute ACTION7 (undo)
            
            Before calling a tool, explain your reasoning. Then call exactly ONE tool.
            Only call tools that are in the available_actions list.
        """).strip()
        
        return prompt
    
    async def prompt_generator(self, latest_frame: FrameData):
        game_prompt = self.build_game_prompt(latest_frame)
        yield {
            "role": "user",
            "content": game_prompt
        }
    
    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        self.step_counter += 1
        logger.info(f"Step {self.step_counter}: Choosing action...")
        
        self.latest_reasoning = ""
        action_taken: Optional[GameAction] = None
        self.captured_messages = []
        self.current_prompt = self.build_game_prompt(latest_frame)
        self.result_message = None
        
        try:
            import asyncio
            loop = asyncio.get_event_loop()
        except RuntimeError:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def run_query():
            nonlocal action_taken
            
            reasoning_parts = []
            
            async for message in query(
                prompt=self.prompt_generator(latest_frame),
                options=ClaudeAgentOptions(
                    model=self.MODEL,
                    mcp_servers={"arc-game-tools": self.mcp_server},
                    permission_mode="bypassPermissions",
                )
            ):
                self.captured_messages.append(message)
                
                if isinstance(message, ResultMessage):
                    self.result_message = message
                
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            reasoning_parts.append(block.text)
                            logger.info(f"Claude reasoning: {block.text[:100]}...")
                        
                        if isinstance(block, ToolUseBlock):
                            tool_name = block.name
                            logger.info(f"Claude calling tool: {tool_name}")
                            
                            if reasoning_parts:
                                self.latest_reasoning = " ".join(reasoning_parts)
                            
                            action_taken = self.parse_action_from_tool(tool_name, block.input)
                            
                            if action_taken:
                                logger.info(f"Parsed action: {action_taken.name}")
                                return
                
                if hasattr(message, "usage") and message.usage:
                    self.track_tokens(message.usage)
        
        loop.run_until_complete(run_query())
        
        if action_taken:
            if self.claude_recorder and not self.is_playback:
                parsed_action = {
                    "action": action_taken.value,
                    "reasoning": self.latest_reasoning
                }
                
                if self.result_message and hasattr(self.result_message, 'total_cost_usd'):
                    cost_usd = self.result_message.total_cost_usd
                else:
                    cost_usd = self.claude_recorder.calculate_cost(self.captured_messages)
                
                self.claude_recorder.save_step(
                    step=self.step_counter,
                    prompt=self.current_prompt,
                    messages=self.captured_messages,
                    parsed_action=parsed_action,
                    total_cost_usd=cost_usd
                )
            
            return action_taken
        
        logger.warning("No action was taken by Claude, defaulting to RESET")
        return GameAction.RESET
    
    def parse_action_from_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Optional[GameAction]:
        tool_map = {
            "mcp__arc-game-tools__reset_game": GameAction.RESET,
            "mcp__arc-game-tools__action1_move_up": GameAction.ACTION1,
            "mcp__arc-game-tools__action2_move_down": GameAction.ACTION2,
            "mcp__arc-game-tools__action3_move_left": GameAction.ACTION3,
            "mcp__arc-game-tools__action4_move_right": GameAction.ACTION4,
            "mcp__arc-game-tools__action5_interact": GameAction.ACTION5,
            "mcp__arc-game-tools__action6_click": GameAction.ACTION6,
            "mcp__arc-game-tools__action7_undo": GameAction.ACTION7,
        }
        
        if tool_name in tool_map:
            action = tool_map[tool_name]
            
            if action == GameAction.ACTION6:
                x = tool_input.get("x", 0)
                y = tool_input.get("y", 0)
                action.action_data.x = x
                action.action_data.y = y
            
            action.action_data.game_id = self.game_id
            
            if self.latest_reasoning:
                action.action_data.__dict__["reasoning"] = {
                    "text": self.latest_reasoning[:16000]
                }
            
            return action
        
        logger.warning(f"Unknown tool name: {tool_name}")
        return None
    
    def track_tokens(self, usage: Any) -> None:
        if hasattr(usage, "input_tokens"):
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total = input_tokens + output_tokens
            self.token_counter += total
            
            logger.info(
                f"Token usage: +{total} (in: {input_tokens}, out: {output_tokens}), total: {self.token_counter}"
            )
            
            if hasattr(self, "recorder") and not self.is_playback:
                self.recorder.record({
                    "tokens": total,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": self.token_counter,
                })
