"""Base Tool abstraction."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """OpenAI function-calling tool definition."""

    name: str
    description: str
    parameters: dict


class BaseTool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict: ...

    @abstractmethod
    async def execute(self, args: dict, context: dict) -> dict: ...

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
