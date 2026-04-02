"""
Self-contained memory per agent session.
Stores conversation history and intermediate results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


@dataclass
class Message:
    role: MessageRole
    content: str
    tool_name: str | None = None
    tool_result: Any = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolCall:
    """Record of a tool call made during agent execution."""
    name: str
    arguments: dict
    result: Any
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)


class AgentMemory:
    """
    Self-contained memory for a single agent session.
    Tracks conversation history, tool calls, and collected data.
    """

    def __init__(self, session_id: str, max_history: int = 10):
        self.session_id = session_id
        self.max_history = max_history
        self.messages: list[Message] = []
        self.tool_calls: list[ToolCall] = []
        self.collected_data: dict[str, Any] = {}
        self.created_at = datetime.now()

    def add_user_message(self, content: str) -> None:
        """Add a user message to history."""
        self.messages.append(Message(role=MessageRole.USER, content=content))
        self._trim_history()

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to history."""
        self.messages.append(Message(role=MessageRole.ASSISTANT, content=content))
        self._trim_history()

    def add_tool_call(self, name: str, arguments: dict, result: Any, success: bool = True) -> None:
        """Record a tool call."""
        self.tool_calls.append(ToolCall(name=name, arguments=arguments, result=result, success=success))
        # Also add as assistant message (the tool call)
        self.messages.append(
            Message(role=MessageRole.ASSISTANT, content=f"Calling tool: {name}", tool_name=name)
        )
        self._trim_history()

    def add_collected_data(self, key: str, value: Any) -> None:
        """Store data collected during execution."""
        self.collected_data[key] = value

    def update_collected_data(self, data: dict[str, Any]) -> None:
        """Update multiple collected data at once."""
        self.collected_data.update(data)

    def get_conversation_for_llm(self) -> list[dict]:
        """Get conversation formatted for LLM context."""
        result = []
        for msg in self.messages:
            if msg.role == MessageRole.TOOL:
                result.append({"role": "tool", "content": str(msg.content)})
            else:
                result.append({"role": msg.role.value, "content": msg.content})
        return result

    def get_recent_messages(self, n: int = 5) -> list[Message]:
        """Get the n most recent messages."""
        return self.messages[-n:]

    def get_tool_call_summary(self) -> str:
        """Get a summary of all tool calls made."""
        if not self.tool_calls:
            return "No tools called."
        lines = []
        for tc in self.tool_calls:
            status = "✅" if tc.success else "❌"
            lines.append(f"{status} {tc.name}({tc.arguments})")
        return "\n".join(lines)

    def get_data_summary(self) -> str:
        """Get a summary of collected data."""
        if not self.collected_data:
            return "No data collected."
        return "\n".join(f"- {k}: {v}" for k, v in self.collected_data.items())

    def clear(self) -> None:
        """Clear all memory (for new session)."""
        self.messages.clear()
        self.tool_calls.clear()
        self.collected_data.clear()

    def _trim_history(self) -> None:
        """Trim history to max_history pairs (user + assistant = 1 pair)."""
        # Keep max_history * 2 messages (1 pair = user + assistant)
        if len(self.messages) > self.max_history * 2:
            self.messages = self.messages[-self.max_history * 2:]


class MemoryStore:
    """
    In-memory store for all agent sessions.
    Maps session_id -> AgentMemory.
    """

    def __init__(self):
        self._store: dict[str, AgentMemory] = {}

    def get_or_create(self, session_id: str, max_history: int = 10) -> AgentMemory:
        """Get existing memory or create new for session."""
        if session_id not in self._store:
            self._store[session_id] = AgentMemory(session_id=session_id, max_history=max_history)
        return self._store[session_id]

    def get(self, session_id: str) -> AgentMemory | None:
        """Get existing memory for session."""
        return self._store.get(session_id)

    def clear(self, session_id: str) -> None:
        """Clear memory for a session."""
        if session_id in self._store:
            self._store[session_id].clear()

    def remove(self, session_id: str) -> None:
        """Remove session from store."""
        self._store.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        return list(self._store.keys())

    def cleanup_old_sessions(self, max_age_seconds: int = 3600) -> int:
        """Remove sessions older than max_age_seconds. Returns count removed."""
        now = datetime.now()
        to_remove = []
        for sid, memory in self._store.items():
            age = (now - memory.created_at).total_seconds()
            if age > max_age_seconds:
                to_remove.append(sid)
        for sid in to_remove:
            self._store.pop(sid, None)
        return len(to_remove)
