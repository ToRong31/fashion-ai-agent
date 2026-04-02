"""
PlanAndExecuteTool — analyzes intent and executes multi-agent plans.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from shared.base_agent.skill import ToolDefinition, ToolResult

if TYPE_CHECKING:
    from services.orchestrator.planning_agent import PlanningAgent, ExecutionPlan
    from services.orchestrator.plan_executor import PlanExecutor
    from services.orchestrator.conversation import SmartConversationManager

logger = structlog.get_logger()


def get_plan_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="plan_and_execute",
        description=(
            "Analyze user intent and create an execution plan, then execute it. "
            "Use this for complex requests that need multiple agents or context-aware actions "
            "(e.g., 'add all', 'item 1 and 3', 'continue shopping')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_message": {"type": "string", "description": "The user's request"},
                "user_id": {"type": "string", "description": "User ID from session"},
            },
            "required": ["user_message"],
        },
    )


async def execute_plan_and_execute(
    args: dict,
    planning_agent: "PlanningAgent",
    plan_executor: "PlanExecutor",
    conversation_mgr: "SmartConversationManager",
) -> ToolResult:
    """
    Execute plan_and_execute tool.

    Analyzes user intent, creates an execution plan, executes it,
    and returns aggregated results.
    """
    user_message: str = args.get("user_message", "")
    user_id: str | None = args.get("user_id")

    # Extract user_id from message if not provided
    if not user_id:
        match = re.search(r"\[user_id=(\d+)\]", user_message)
        if match:
            user_id = match.group(1)
    user_id = user_id or "unknown"

    # Get conversation context
    conv_history = conversation_mgr.get_history(user_id)

    # Create execution plan
    context = {"user_id": user_id, "token": None}
    try:
        plan = await planning_agent.create_plan(
            user_message,
            context,
            conversation_history=conv_history,
        )
    except Exception as e:
        logger.error("planning_failed", error=str(e))
        return ToolResult(content=f"Error creating plan: {str(e)}", data=None)

    logger.info("plan_created", mode=plan.mode.value, steps=len(plan.steps))

    # Execute plan
    try:
        result = await plan_executor.execute(plan, context)
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        return ToolResult(content=f"Error executing plan: {str(e)}", data=None)

    # Extract data
    data = result.get("data", {})
    agents_used = result.get("agents_used", [])

    return ToolResult(
        content=result.get("text", "Task completed."),
        data={
            "agent_used": ", ".join(agents_used) if agents_used else None,
            "mode": result.get("mode"),
            "steps_executed": len(plan.steps),
            **data,
        },
    )
