"""
Workflow State Manager - tracks workflow execution state per user.

This module provides:
- WorkflowState: Enum for workflow states
- WorkflowContext: Tracks current workflow including products, pending actions
- WorkflowStateManager: Manages workflow state per user
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class WorkflowState(Enum):
    """Workflow execution states."""

    IDLE = "idle"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"


@dataclass
class WorkflowContext:
    """Tracks the current workflow execution state for a user."""

    user_id: str
    original_request: str
    created_at: datetime = field(default_factory=datetime.now)
    state: WorkflowState = WorkflowState.IDLE
    updated_at: datetime = field(default_factory=datetime.now)

    # Products from searches
    last_search_results: list[dict] = field(default_factory=list)
    selected_products: list[dict] = field(default_factory=list)

    # Pending actions
    pending_action: str = ""  # "add_to_cart", "checkout", etc.
    pending_product_ids: list[int] = field(default_factory=list)
    pending_confirmation_message: str = ""

    # Execution tracking
    current_plan: dict = field(default_factory=dict)
    execution_results: dict = field(default_factory=list)

    # Conversation context
    last_user_message: str = ""
    last_agent_response: str = ""

    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if workflow has expired (default 5 minutes)."""
        return datetime.now() - self.updated_at > timedelta(seconds=timeout_seconds)

    def touch(self) -> None:
        """Update the last modified time."""
        self.updated_at = datetime.now()


class WorkflowStateManager:
    """Manages workflow state per user."""

    def __init__(self, timeout_seconds: int = 300):
        self._states: dict[str, WorkflowContext] = {}
        self._timeout_seconds = timeout_seconds

    def get_or_create(self, user_id: str, request: str = "") -> WorkflowContext:
        """Get existing state or create new one."""
        # Check if existing state is expired
        if user_id in self._states:
            if self._states[user_id].is_expired(self._timeout_seconds):
                # Clear expired state
                self._states.pop(user_id)
            else:
                # Update request and touch
                self._states[user_id].original_request = request
                self._states[user_id].touch()
                return self._states[user_id]

        # Create new state
        ctx = WorkflowContext(
            user_id=user_id,
            original_request=request,
        )
        self._states[user_id] = ctx
        return ctx

    def get(self, user_id: str) -> WorkflowContext | None:
        """Get existing state or None if not found/expired."""
        if user_id in self._states:
            if self._states[user_id].is_expired(self._timeout_seconds):
                self._states.pop(user_id)
                return None
            return self._states[user_id]
        return None

    def update_search_results(self, user_id: str, products: list[dict]) -> None:
        """Update with products from latest search."""
        ctx = self.get_or_create(user_id)
        ctx.last_search_results = products
        ctx.selected_products = []  # Clear selection when new search
        ctx.touch()

    def add_selected_products(self, user_id: str, products: list[dict]) -> None:
        """Add products to selected list."""
        ctx = self.get_or_create(user_id)
        # Add to existing selected products (avoid duplicates)
        existing_ids = {p.get("id") for p in ctx.selected_products}
        for p in products:
            if p.get("id") not in existing_ids:
                ctx.selected_products.append(p)
                existing_ids.add(p.get("id"))
        ctx.touch()

    def set_pending_action(
        self,
        user_id: str,
        action: str,
        product_ids: list[int] = None,
        confirmation_message: str = "",
    ) -> None:
        """Set a pending action to be confirmed by user."""
        ctx = self.get_or_create(user_id)
        ctx.pending_action = action
        ctx.pending_product_ids = product_ids or []
        ctx.pending_confirmation_message = confirmation_message
        ctx.state = WorkflowState.AWAITING_CONFIRMATION
        ctx.touch()

    def clear_pending_action(self, user_id: str) -> None:
        """Clear pending action."""
        ctx = self.get(user_id)
        if ctx:
            ctx.pending_action = ""
            ctx.pending_product_ids = []
            ctx.pending_confirmation_message = ""
            ctx.state = WorkflowState.IDLE
            ctx.touch()

    def update_execution_results(self, user_id: str, results: dict) -> None:
        """Update execution results."""
        ctx = self.get_or_create(user_id)
        ctx.execution_results = results
        ctx.touch()

    def set_state(self, user_id: str, state: WorkflowState) -> None:
        """Set workflow state."""
        ctx = self.get_or_create(user_id)
        ctx.state = state
        ctx.touch()

    def clear(self, user_id: str) -> None:
        """Clear state for user."""
        self._states.pop(user_id, None)

    def clear_all(self) -> None:
        """Clear all states."""
        self._states.clear()

    def has_pending_action(self, user_id: str) -> bool:
        """Check if user has pending action."""
        ctx = self.get(user_id)
        return ctx is not None and ctx.pending_action != ""

    def get_last_search_products(self, user_id: str) -> list[dict]:
        """Get last search products."""
        ctx = self.get(user_id)
        if ctx:
            return ctx.last_search_results
        return []

    def get_selected_products(self, user_id: str) -> list[dict]:
        """Get selected products."""
        ctx = self.get(user_id)
        if ctx:
            return ctx.selected_products
        return []

    def get_all_products(self, user_id: str) -> list[dict]:
        """Get all available products (selected + last search)."""
        ctx = self.get(user_id)
        if not ctx:
            return []

        # Start with selected products
        products = list(ctx.selected_products)

        # Add last search results that aren't already selected
        selected_ids = {p.get("id") for p in products}
        for p in ctx.last_search_results:
            if p.get("id") not in selected_ids:
                products.append(p)

        return products
