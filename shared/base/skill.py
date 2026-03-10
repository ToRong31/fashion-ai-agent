"""
Base Skill abstraction.

A Skill is a self-contained capability that an agent can perform.
Each skill declares:
  - metadata (id, name, description, tags, examples) — published via agent card
  - tools — OpenAI function-calling definitions used by the LLM
  - execute_tool — runs a specific tool with given arguments
  - prompt instructions — tells the LLM how to use this skill
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from a2a.types import AgentSkill


@dataclass
class ToolDefinition:
    """OpenAI function-calling tool definition."""

    name: str
    description: str
    parameters: dict

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """Result returned by Skill.execute_tool().

    Attributes:
        content: Sent back to the LLM as the tool response (will be JSON-serialised).
        data:    Optional structured data accumulated for the final DataPart response
                 (e.g. cart_item, order, products list sent to the frontend).
    """

    content: str | dict | list
    data: dict | None = None


class Skill(ABC):
    """
    Abstract base for an agent skill.

    Subclass this to create a concrete skill. Register it on a BaseAgent so it
    gets published in the agent card and its tools are available to the executor.
    """

    # --- metadata (override as properties) ---

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def tags(self) -> list[str]:
        return []

    @property
    def examples(self) -> list[str]:
        return []

    # --- tools ---

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """Return tool definitions this skill exposes."""
        ...

    @abstractmethod
    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute a named tool with the given arguments."""
        ...

    # --- prompt ---

    @abstractmethod
    def get_prompt_instructions(self) -> str:
        """Return system-prompt instructions describing how to use this skill."""
        ...

    # --- conversions ---

    def to_a2a_skill(self) -> AgentSkill:
        """Convert to A2A AgentSkill for agent-card publishing."""
        return AgentSkill(
            id=self.id,
            name=self.name,
            description=self.description,
            tags=self.tags,
            examples=self.examples,
        )

    def get_openai_tools(self) -> list[dict]:
        """Return all tools in OpenAI function-calling format."""
        return [t.to_openai_tool() for t in self.get_tools()]
