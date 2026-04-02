"""
OrchestrationSkill — skill-based orchestrator.

This skill coordinates multi-agent workflows using tools:
  - route_to_agent: delegate to a single worker agent
  - plan_and_execute: analyze intent and run multi-agent plans
  - get_conversation_history: retrieve context from conversation
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from shared.base_agent.skill import Skill, ToolDefinition, ToolResult

if TYPE_CHECKING:
    from services.orchestrator.planning_agent import PlanningAgent
    from services.orchestrator.plan_executor import PlanExecutor
    from services.orchestrator.routing_agent import RoutingAgent
    from services.orchestrator.conversation import SmartConversationManager

from services.orchestrator.tools.route_tool import (
    get_route_tool_definition,
    execute_route_to_agent,
)
from services.orchestrator.tools.plan_tool import (
    get_plan_tool_definition,
    execute_plan_and_execute,
)
from services.orchestrator.tools.history_tool import (
    get_history_tool_definition,
    execute_get_history,
)

logger = structlog.get_logger()


def _load_prompt(filename: str) -> str:
    yaml_path = Path(__file__).parent / "prompts" / filename
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["prompt"]


class OrchestrationSkill(Skill):
    """
    Skill for orchestrating multi-agent workflows.

    Uses tools to delegate to worker agents and coordinate complex workflows.
    """

    def __init__(
        self,
        routing_agent: "RoutingAgent",
        planning_agent: "PlanningAgent",
        plan_executor: "PlanExecutor",
        conversation_mgr: "SmartConversationManager",
    ):
        self._routing = routing_agent
        self._planning = planning_agent
        self._executor = plan_executor
        self._conversation = conversation_mgr
        self._user_message: str | None = None

    # -------------------------------------------------------------------------
    # Skill metadata
    # -------------------------------------------------------------------------

    @property
    def id(self) -> str:
        return "orchestration"

    @property
    def name(self) -> str:
        return "Multi-Agent Orchestration"

    @property
    def description(self) -> str:
        return (
            "Orchestrates multi-agent workflows. Analyzes user intent, "
            "creates execution plans, routes to appropriate agents (search, stylist, order), "
            "and aggregates results. Handles both single-agent and multi-agent scenarios."
        )

    @property
    def tags(self) -> list[str]:
        return ["orchestrate", "route", "plan", "coordinate", "multi-agent"]

    @property
    def examples(self) -> list[str]:
        return [
            "find me a white shirt and add to cart",
            "search for black dress and recommend an outfit",
            "show me shoes and pants together",
            "I want to buy the blue jacket I saw earlier",
            "what outfits match this dress?",
        ]

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    def get_tools(self) -> list[ToolDefinition]:
        return [
            get_route_tool_definition(),
            get_plan_tool_definition(),
            get_history_tool_definition(),
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute orchestration tool by delegating to tool functions."""
        # Extract user_id from user_message for context
        user_id = self._extract_user_id(args.get("user_message", ""))

        if tool_name == "route_to_agent":
            return await execute_route_to_agent(
                args,
                routing_agent=self._routing,
                conversation_mgr=self._conversation,
                user_id=user_id,
            )
        elif tool_name == "plan_and_execute":
            return await execute_plan_and_execute(
                args,
                planning_agent=self._planning,
                plan_executor=self._executor,
                conversation_mgr=self._conversation,
            )
        elif tool_name == "get_conversation_history":
            return await execute_get_history(
                args,
                conversation_mgr=self._conversation,
            )
        else:
            return ToolResult(content=f"Unknown tool: {tool_name}", data=None)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _extract_user_id(self, text: str) -> str | None:
        """Extract user_id from message if present."""
        import re
        match = re.search(r"\[user_id=(\d+)\]", text)
        return match.group(1) if match else None

    def set_user_message(self, message: str) -> None:
        """Store user message for context extraction."""
        self._user_message = message

    # -------------------------------------------------------------------------
    # Prompt instructions
    # -------------------------------------------------------------------------

    def get_prompt_instructions(self) -> str:
        return _load_prompt("orchestration.yaml")
