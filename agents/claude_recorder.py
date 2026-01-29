import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import AssistantMessage, ToolUseBlock, ResultMessage

logger = logging.getLogger()


class ClaudeCodeRecorder:
    
    ANTHROPIC_PRICING = {
        "input_tokens": 0.003 / 1000,
        "output_tokens": 0.015 / 1000,
    }
    
    def __init__(self, game_id: str, agent_name: str):
        self.game_id = game_id
        self.agent_name = agent_name
        
        recordings_dir = os.getenv("RECORDINGS_DIR", "recordings")
        self.output_dir = Path(recordings_dir) / f"{game_id}_{agent_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ClaudeCodeRecorder initialized: {self.output_dir}")
    
    def save_step(
        self,
        step: int,
        prompt: str,
        messages: list[Any],
        parsed_action: dict[str, Any],
        total_cost_usd: float
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        
        formatted_messages = self.format_messages(messages)
        final_response = self.aggregate_responses(formatted_messages)
        
        step_data = {
            "step": step,
            "timestamp": timestamp,
            "prompt": prompt,
            "messages": formatted_messages,
            "final_response": final_response,
            "parsed_action": parsed_action,
            "cost_usd": total_cost_usd
        }
        
        step_filename = self.output_dir / f"step_{step:03d}.json"
        with open(step_filename, "w", encoding="utf-8") as f:
            json.dump(step_data, f, indent=2)
        
        logger.info(f"Saved step {step} to {step_filename}")
    
    def format_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        formatted = []
        tool_id_to_name = {}
        
        for msg in messages:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if hasattr(block, "text") and block.text:
                        formatted.append({
                            "type": "text",
                            "timestamp": timestamp,
                            "content": block.text
                        })
                    
                    if isinstance(block, ToolUseBlock):
                        tool_id_to_name[block.id] = block.name
                        formatted.append({
                            "type": "tool_call",
                            "timestamp": timestamp,
                            "tool_use_id": block.id,
                            "tool_name": block.name,
                            "tool_input": block.input
                        })
            
            elif isinstance(msg, ResultMessage):
                for block in msg.content:
                    result_data = block.model_dump() if hasattr(block, "model_dump") else {"content": str(block)}
                    tool_use_id = getattr(block, "tool_use_id", "")
                    tool_name = tool_id_to_name.get(tool_use_id, "unknown")
                    
                    formatted.append({
                        "type": "tool_result",
                        "timestamp": timestamp,
                        "tool_use_id": tool_use_id,
                        "tool_name": tool_name,
                        "result": result_data
                    })
        
        return formatted
    
    def aggregate_responses(self, formatted_messages: list[dict[str, Any]]) -> str:
        text_parts = []
        
        for msg in formatted_messages:
            if msg.get("type") == "text":
                text_parts.append(msg.get("content", ""))
        
        return "".join(text_parts)
    
    def calculate_cost(
        self,
        messages: list[Any],
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> float:
        seen_message_ids = set()
        total_input_tokens = input_tokens
        total_output_tokens = output_tokens
        
        for msg in messages:
            if hasattr(msg, "id") and hasattr(msg, "usage"):
                if msg.id not in seen_message_ids:
                    seen_message_ids.add(msg.id)
                    
                    if hasattr(msg.usage, "input_tokens"):
                        total_input_tokens += msg.usage.input_tokens
                    if hasattr(msg.usage, "output_tokens"):
                        total_output_tokens += msg.usage.output_tokens
        
        cost_usd = (
            total_input_tokens * self.ANTHROPIC_PRICING["input_tokens"] +
            total_output_tokens * self.ANTHROPIC_PRICING["output_tokens"]
        )
        
        return cost_usd
