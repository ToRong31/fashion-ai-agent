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


class EnhancedConversationManager:
    """Manages conversation history with structured data extraction."""

    def __init__(self, max_history: int = 20):
        self._max_history = max_history
        self._history: dict[str, list[Message]] = {}

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

        # Trim history
        if len(self._history[user_id]) > self._max_history:
            self._history[user_id] = self._history[user_id][-self._max_history:]

    def get_history(self, user_id: str) -> list[Message]:
        """Get full conversation history as Message objects."""
        return list(self._history.get(user_id, []))

    def get_history_dict(self, user_id: str) -> list[dict]:
        """Get conversation history as dicts (for LLM context)."""
        history = self.get_history(user_id)
        return [
            {
                "role": msg.role.value,
                "content": msg.content,
                "products": msg.products,
                "cart_items": msg.cart_items,
                "orders": msg.orders,
            }
            for msg in history
        ]

    def get_last_search_products(self, user_id: str) -> list[dict]:
        """Get products from the last search in conversation."""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg.products:
                return msg.products
        return []

    def get_last_cart_items(self, user_id: str) -> list[dict]:
        """Get cart items from the last cart operation."""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg.cart_items:
                return msg.cart_items
        return []

    def get_last_orders(self, user_id: str) -> list[dict]:
        """Get orders from the last order operation."""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg.orders:
                return msg.orders
        return []

    def get_last_products_count(self, user_id: str) -> int:
        """Get count of products from last search."""
        products = self.get_last_search_products(user_id)
        return len(products)

    def clear(self, user_id: str) -> None:
        """Clear conversation for a user."""
        self._history.pop(user_id, None)
