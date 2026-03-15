from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """A conversation message with optional structured data."""
    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # Extracted structured data from this message
    products: list[dict] = field(default_factory=list)
    cart_items: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    # Agent used for this message
    agent_used: str = ""


class ConversationManager:
    def __init__(self, max_history: int = 20):
        self._max_history = max_history
        self._histories: dict[str, list[dict]] = defaultdict(list)

    def add_message(self, user_id: str, role: str, content: str) -> None:
        self._histories[user_id].append({"role": role, "content": content})
        if len(self._histories[user_id]) > self._max_history:
            self._histories[user_id] = self._histories[user_id][-self._max_history:]

    def get_history(self, user_id: str) -> list[dict]:
        return list(self._histories.get(user_id, []))

    def clear(self, user_id: str) -> None:
        self._histories.pop(user_id, None)


class SmartConversationManager:
    """
    Manages conversation with sliding window:
    - Last 3 pairs (6 messages) = full conversation
    - Older messages = 1 summary

    This keeps context for the LLM without overwhelming it.
    """

    # Number of message pairs to keep in full
    FULL_PAIRS = 3

    def __init__(self):
        self._history: dict[str, list[Message]] = {}
        self._summary: dict[str, str] = {}  # user_id -> summary

    def add_message(
        self,
        user_id: str,
        role: MessageRole | str,
        content: str,
        products: list[dict] = None,
        cart_items: list[dict] = None,
        orders: list[dict] = None,
        agent_used: str = "",
    ) -> None:
        """Add message with optional structured data."""
        if user_id not in self._history:
            self._history[user_id] = []

        # Convert string role to enum
        if isinstance(role, str):
            role = MessageRole(role)

        message = Message(
            role=role,
            content=content,
            products=products or [],
            cart_items=cart_items or [],
            orders=orders or [],
            agent_used=agent_used,
        )
        self._history[user_id].append(message)

        # Check if we need to summarize (more than 3 pairs)
        if len(self._history[user_id]) > self.FULL_PAIRS * 2:
            self._summarize(user_id)

    def _summarize(self, user_id: str) -> None:
        """Create a summary of older messages, keep only last 3 pairs."""
        history = self._history.get(user_id, [])
        if len(history) <= self.FULL_PAIRS * 2:
            return

        # Messages to summarize (everything except last 3 pairs)
        messages_to_summarize = history[:-self.FULL_PAIRS * 2]

        # Build summary from messages
        summary_parts = []
        for msg in messages_to_summarize:
            if msg.role == MessageRole.USER:
                summary_parts.append(f"User: {msg.content[:100]}")
            elif msg.role == MessageRole.ASSISTANT:
                if msg.products:
                    summary_parts.append(f"Bot: showed {len(msg.products)} products")
                if msg.cart_items:
                    summary_parts.append(f"Bot: added {len(msg.cart_items)} items to cart")
                if msg.orders:
                    summary_parts.append(f"Bot: created order")
                if not msg.products and not msg.cart_items and not msg.orders:
                    summary_parts.append(f"Bot: {msg.content[:80]}")

        self._summary[user_id] = " | ".join(summary_parts[-5:])  # Last 5 key events

        # Keep only last 3 pairs
        self._history[user_id] = history[-self.FULL_PAIRS * 2:]

    def get_history(self, user_id: str) -> list[Message]:
        """Get full conversation history as Message objects."""
        return list(self._history.get(user_id, []))

    def get_history_for_llm(self, user_id: str) -> list[dict]:
        """
        Get conversation formatted for LLM context.

        Returns:
            - Summary of older messages (if any)
            - Last 3 pairs of full conversation
        """
        result = []
        history = self.get_history(user_id)

        # Add summary if exists
        if user_id in self._summary and self._summary[user_id]:
            result.append({
                "role": "system",
                "content": f"Earlier conversation summary: {self._summary[user_id]}"
            })

        # Add recent messages
        for msg in history:
            result.append({
                "role": msg.role.value,
                "content": msg.content,
                # Include structured data for recent messages
                "products": msg.products if len(result) < 4 else [],  # Only last few
                "cart_items": msg.cart_items if len(result) < 4 else [],
                "orders": msg.orders if len(result) < 4 else [],
            })

        return result

    def get_last_products(self, user_id: str) -> list[dict]:
        """Get products from the last assistant message."""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg.products:
                return msg.products
        return []

    def get_last_search_products(self, user_id: str) -> list[dict]:
        """Get products from the last search in conversation."""
        return self.get_last_products(user_id)

    def clear(self, user_id: str) -> None:
        """Clear conversation for a user."""
        self._history.pop(user_id, None)
        self._summary.pop(user_id, None)


# Backwards compatibility alias
EnhancedConversationManager = SmartConversationManager
