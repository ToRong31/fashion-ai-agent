"""
Base Agent — a container of Skills.

An agent registers one or more Skills, then can:
  - build an A2A AgentCard with all skills published
  - aggregate all tools for the LLM executor
  - build a combined system prompt from skill instructions
  - route a tool call to the skill that owns it
"""
from __future__ import annotations

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from shared.base_agent.skill import Skill


class BaseAgent:
    """Agent that holds a collection of skills."""

    def __init__(self, name: str, description: str, version: str = "0.1.0"):
        self.name = name
        self.description = description
        self.version = version
        self._skills: dict[str, Skill] = {}

    # --- skill management ---

    def register_skill(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def find_skill_for_tool(self, tool_name: str) -> Skill | None:
        """Find which skill owns a given tool name."""
        for skill in self._skills.values():
            for tool_def in skill.get_tools():
                if tool_def.name == tool_name:
                    return skill
        return None

    # --- aggregated tools (deduplicated by name) ---

    def get_all_openai_tools(self) -> list[dict]:
        seen: set[str] = set()
        tools: list[dict] = []
        for skill in self._skills.values():
            for t in skill.get_openai_tools():
                name = t["function"]["name"]
                if name not in seen:
                    seen.add(name)
                    tools.append(t)
        return tools

    # --- system prompt ---

    def build_system_prompt(self) -> str:
        parts = [f"You are the {self.name} for ToRoMe Store, a fashion clothing store."]
        for skill in self._skills.values():
            parts.append(f"\n## Skill: {skill.name}\n{skill.get_prompt_instructions()}")
        parts.append(
            "\n**IMPORTANT:** Always use the provided tools to fulfill requests. "
            "Never answer from your own knowledge about products or orders."
        )
        return "\n".join(parts)

    # --- A2A agent card ---

    def build_agent_card(self, host: str, port: int) -> AgentCard:
        return AgentCard(
            name=self.name,
            description=self.description,
            url=f"{host}:{port}/",
            version=self.version,
            capabilities=AgentCapabilities(streaming=False, push_notifications=False),
            skills=[s.to_a2a_skill() for s in self._skills.values()],
            default_input_modes=["text/plain", "application/json"],
            default_output_modes=["application/json"],
        )
