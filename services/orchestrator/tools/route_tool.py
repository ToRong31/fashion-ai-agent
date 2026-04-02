"""
RouteToAgentTool — routes a single user request to one worker agent.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from shared.base_agent.skill import ToolDefinition, ToolResult

if TYPE_CHECKING:
    from services.orchestrator.routing_agent import RoutingAgent
    from services.orchestrator.conversation import SmartConversationManager

logger = structlog.get_logger()

# Re-export ToolDefinition so OrchestrationSkill can import from here
__all__ = ["ToolDefinition", "execute_route_to_agent"]


def get_route_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="route_to_agent",
        description=(
            "Route user request to a single worker agent. "
            "Use this for simple requests that need only one agent."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_message": {"type": "string", "description": "The user's request"},
                "agent_name": {
                    "type": "string",
                    "description": "Target agent: Search Agent, Stylist Agent, or Order Agent",
                },
            },
            "required": ["user_message", "agent_name"],
        },
    )


async def execute_route_to_agent(
    args: dict,
    routing_agent: "RoutingAgent",
    conversation_mgr: "SmartConversationManager",
    user_id: str | None = None,
) -> ToolResult:
    """
    Execute route_to_agent tool.

    Routes user message to a single worker agent and returns the result.
    """
    user_message: str = args.get("user_message", "")
    agent_name: str = args.get("agent_name", "")

    # Extract user_id from message if not provided
    if not user_id:
        import re
        match = re.search(r"\[user_id=(\d+)\]", user_message)
        if match:
            user_id = match.group(1)

    # Get conversation history
    history = []
    if user_id:
        history = conversation_mgr.get_history(user_id)

    logger.info("routing_single", agent=agent_name, user_id=user_id)

    try:
        result = await routing_agent.run(
            user_message=user_message,
            user_id=user_id,
            conversation_history=history,
            token=None,
        )
        return ToolResult(
            content=result.get("response", "No response"),
            data={
                "agent_used": agent_name,
                "products": result.get("data", {}).get("products") if result.get("data") else None,
            },
        )
    except Exception as e:
        logger.error("routing_failed", agent=agent_name, error=str(e))
        return ToolResult(
            content=f"Error routing to {agent_name}: {str(e)}",
            data=None,
        )
