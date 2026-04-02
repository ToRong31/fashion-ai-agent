"""
GetConversationHistoryTool — retrieves conversation history for context.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from shared.base_agent.skill import ToolDefinition, ToolResult

if TYPE_CHECKING:
    from services.orchestrator.conversation import SmartConversationManager


def get_history_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="get_conversation_history",
        description="Get the conversation history for context about previous interactions.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
            },
            "required": ["user_id"],
        },
    )


async def execute_get_history(
    args: dict,
    conversation_mgr: "SmartConversationManager",
) -> ToolResult:
    """
    Execute get_conversation_history tool.

    Returns conversation history formatted for context.
    """
    user_id: str = args.get("user_id", "")
    history = conversation_mgr.get_history(user_id)
    formatted = conversation_mgr.get_history_for_llm(user_id)

    summary = {
        "user_id": user_id,
        "message_count": len(history),
        "recent_messages": [
            {"role": m.role.value, "content": m.content[:100]}
            for m in history[-6:]
        ],
    }

    return ToolResult(
        content=json.dumps(summary, ensure_ascii=False, indent=2),
        data={"history": formatted},
    )
