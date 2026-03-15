# Orchestrator Memory & Flexible Re-Planning

> Implement conversation context and state management for multi-agent workflows

## Implementation Status: ✅ COMPLETED

| Component | Status | File |
|-----------|--------|------|
| EnhancedConversationManager | ✅ Done | `services/orchestrator/conversation.py` |
| WorkflowStateManager | ✅ Done | `services/orchestrator/workflow_state.py` |
| Context-Aware PlanningAgent | ✅ Done | `services/orchestrator/planning_agent.py` |
| Multi-Item PlanExecutor | ✅ Done | `services/orchestrator/plan_executor.py` |
| Orchestrator Main Integration | ✅ Done | `services/orchestrator/main.py` |

## Configuration

```bash
# Environment variables (already set in code)
ORCHESTRATOR_ENABLE_MULTI_AGENT=true       # Enable multi-agent planning
ORCHESTRATOR_ENABLE_CONTEXT_AWARE=true    # Enable context-aware planning
ORCHESTRATOR_WORKFLOW_TIMEOUT_SECONDS=300  # Workflow expires after 5 min
```

## Problem Statement

Current implementation issues:
1. **No context retention**: Each user message is planned independently, losing previous search results
2. **Single-item limitation**: "Add all to cart" doesn't work because planner doesn't know what products were found
3. **No re-planning**: Can't adapt when user intent changes after seeing results

### Example Failure Flow

```
User: "find black jacket"
  → Plan: SINGLE, Search Agent
  → Returns 10 products (stored nowhere)

User: "add all to my cart"
  → Plan: SINGLE, Order Agent (new plan, no context!)
  → Order Agent searches again or only adds 1 item
  → FAIL: User wanted all 10 items
```

## Solution: Stateful Orchestrator

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Enhanced Orchestrator                             │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 1. CONVERSATION MANAGER - Full history + parsed context    │    │
│  │    - Stores messages                                        │    │
│  │    - Extracts structured data (products, orders, etc.)      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│        │                                                           │
│        ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 2. WORKFLOW STATE - Tracks execution state                 │    │
│  │    - Current plan                                           │    │
│  │    - Products from last search                              │    │
│  │    - Pending confirmations                                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│        │                                                           │
│        ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 3. CONTEXT-AWARE PLANNER - Uses history + state           │    │
│  │    - Analyzes full conversation                             │    │
│  │    - Detects "add all" refers to previous search            │    │
│  │    - Re-plans when needed                                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│        │                                                           │
│        ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 4. PLAN EXECUTOR - Executes with context passing          │    │
│  │    - Passes product IDs between steps                       │    │
│  │    - Handles multi-item operations                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. Update Conversation Manager

File: `services/orchestrator/conversation.py`

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """A conversation message with optional structured data."""
    role: MessageRole
    content: str
    timestamp: str = ""
    # Extracted structured data from this message
    products: list[dict] = field(default_factory=list)
    cart_items: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)


class EnhancedConversationManager:
    """Manages conversation history with structured data extraction."""

    def __init__(self, max_history: int = 20):
        self._history: dict[str, list[Message]] = {}
        self._max_history = max_history

    def add_message(
        self,
        user_id: str,
        role: MessageRole,
        content: str,
        products: list[dict] = None,
        cart_items: list[dict] = None,
        orders: list[dict] = None,
    ) -> None:
        """Add message with optional structured data."""
        if user_id not in self._history:
            self._history[user_id] = []

        message = Message(
            role=role,
            content=content,
            products=products or [],
            cart_items=cart_items or [],
            orders=orders or [],
        )
        self._history[user_id].append(message)

        # Trim history
        if len(self._history[user_id]) > self._max_history:
            self._history[user_id] = self._history[user_id][-self._max_history:]

    def get_history(self, user_id: str) -> list[Message]:
        """Get full conversation history."""
        return self._history.get(user_id, [])

    def get_last_search_products(self, user_id: str) -> list[dict]:
        """Get products from the last search in conversation."""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg.products:
                return msg.products
        return []

    def clear_user(self, user_id: str) -> None:
        """Clear conversation for a user."""
        self._history.pop(user_id, None)
```

### 2. Workflow State Manager

File: `services/orchestrator/workflow_state.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


class WorkflowState(Enum):
    IDLE = "idle"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"


@dataclass
class WorkflowContext:
    """Tracks the current workflow execution state."""

    user_id: str
    original_request: str
    created_at: datetime = field(default_factory=datetime.now)
    state: WorkflowState = WorkflowState.IDLE

    # Products from searches
    last_search_results: list[dict] = field(default_factory=list)
    selected_products: list[dict] = field(default_factory=list)

    # Pending actions
    pending_action: str = ""  # "add_to_cart", "checkout", etc.
    pending_product_ids: list[int] = field(default_factory=list)

    # Execution tracking
    current_plan: dict = field(default_factory=dict)
    execution_results: dict = field(default_factory=dict)


class WorkflowStateManager:
    """Manages workflow state per user."""

    def __init__(self):
        self._states: dict[str, WorkflowContext] = {}

    def get_or_create(self, user_id: str, request: str = "") -> WorkflowContext:
        """Get existing state or create new one."""
        if user_id not in self._states:
            self._states[user_id] = WorkflowContext(
                user_id=user_id,
                original_request=request,
            )
        return self._states[user_id]

    def update_search_results(self, user_id: str, products: list[dict]) -> None:
        """Update with products from latest search."""
        ctx = self.get_or_create(user_id)
        ctx.last_search_results = products

    def set_pending_action(
        self,
        user_id: str,
        action: str,
        product_ids: list[int] = None,
    ) -> None:
        """Set a pending action to be confirmed by user."""
        ctx = self.get_or_create(user_id)
        ctx.pending_action = action
        ctx.pending_product_ids = product_ids or []
        ctx.state = WorkflowState.AWAITING_CONFIRMATION

    def clear(self, user_id: str) -> None:
        """Clear state for user."""
        self._states.pop(user_id, None)
```

### 3. Context-Aware Planning Agent

File: `services/orchestrator/planning_agent.py` (update)

```python
class PlanningAgent:
    """Analyzes user request with full conversation context."""

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        self._openai = openai_client
        self._model = model
        self._use_llm = openai_client is not None

    async def create_plan(
        self,
        user_message: str,
        context: dict | None = None,
        conversation_history: list[Message] = None,
        workflow_state: WorkflowContext = None,
    ) -> ExecutionPlan:
        """
        Create execution plan with full context awareness.

        Key improvements:
        - Uses previous search results if user says "add all"
        - Detects confirmation vs new request
        - Re-plans based on workflow state
        """
        context = context or {}
        conversation_history = conversation_history or []

        # Extract products from conversation
        last_products = []
        for msg in reversed(conversation_history):
            if msg.products:
                last_products = msg.products
                break

        # Check workflow state for pending actions
        if workflow_state and workflow_state.pending_action:
            return await self._plan_with_pending_action(
                user_message, workflow_state, context
            )

        # If user mentions "all" and we have previous results
        if self._wants_all_items(user_message) and last_products:
            return await self._plan_add_all(user_message, last_products, context)

        # Standard planning (existing logic)
        return await self._create_plan_standard(user_message, context)

    def _wants_all_items(self, message: str) -> bool:
        """Check if user wants all items."""
        all_keywords = ["all", "tất cả", "every", "add all"]
        return any(kw in message.lower() for kw in all_keywords)

    async def _plan_add_all(
        self,
        user_message: str,
        products: list[dict],
        context: dict,
    ) -> ExecutionPlan:
        """Plan to add all products to cart."""

        # Extract all product IDs
        product_ids = [p.get("id") for p in products if p.get("id")]

        user_id = context.get("user_id", 1)

        # SEQUENTIAL: Search (already done) → Order (add all)
        return ExecutionPlan(
            mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="1",
                    agent_name="Order Agent",
                    task=f"Add ALL of these products to cart: {products}",
                    context={"product_ids": product_ids, "all_products": products},
                ),
            ],
            estimated_response="Added all products to cart",
        )

    async def _plan_with_pending_action(
        self,
        user_message: str,
        workflow_state: WorkflowContext,
        context: dict,
    ) -> ExecutionPlan:
        """Plan based on pending action from previous turn."""

        if workflow_state.pending_action == "add_to_cart":
            # User confirmed add to cart
            product_ids = workflow_state.pending_product_ids

            return ExecutionPlan(
                mode=ExecutionMode.SEQUENTIAL,
                steps=[
                    ExecutionStep(
                        step_id="1",
                        agent_name="Order Agent",
                        task=f"Add products {product_ids} to cart",
                    ),
                ],
            )

        # Default: clear pending and re-plan
        return await self._create_plan_standard(user_message, context)
```

### 4. Update Orchestrator Main

File: `services/orchestrator/main.py`

```python
from services.orchestrator.conversation import EnhancedConversationManager, MessageRole
from services.orchestrator.workflow_state import WorkflowStateManager

# Update globals
conversation_mgr = EnhancedConversationManager(...)
workflow_mgr = WorkflowStateManager()

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str | None = Header(None)):
    # ... existing token extraction ...

    # Get workflow state
    workflow_state = workflow_mgr.get_or_create(
        request.user_id,
        request.message
    )

    # Create plan with full context
    plan = await planning_agent.create_plan(
        user_message=request.message,
        context={"user_id": request.user_id, "token": token},
        conversation_history=conversation_mgr.get_history(request.user_id),
        workflow_state=workflow_state,
    )

    # Execute plan
    if plan.mode == ExecutionMode.SINGLE:
        result = await routing_agent.run(...)
    else:
        execution_result = await plan_executor.execute(plan, context)
        result = {...}

    # Extract products from result and update conversation/state
    if result.get("data") and "products" in result["data"]:
        products = result["data"]["products"]
        conversation_mgr.add_message(
            request.user_id,
            MessageRole.ASSISTANT,
            result["response"],
            products=products,
        )
        workflow_mgr.update_search_results(request.user_id, products)

    # Clear pending if action completed
    if workflow_state.pending_action:
        workflow_state.pending_action = ""

    return ChatResponse(...)
```

### 5. Update Plan Executor for Multi-Item Operations

File: `services/orchestrator/plan_executor.py`

```python
async def _execute_sequential(self, steps, context):
    results = {}
    accumulated_context = context.copy()

    for step in steps:
        # If step has product_ids in context, expand to multi-item
        if step.context and "product_ids" in step.context:
            product_ids = step.context["product_ids"]

            # If multiple products, create order with all
            if len(product_ids) > 1:
                task = step.task
                task += f"\n\nIMPORTANT: Add ALL {len(product_ids)} products: {product_ids}"
                step = ExecutionStep(
                    step_id=step.step_id,
                    agent_name=step.agent_name,
                    task=task,
                    context=step.context,
                )

        result = await self._send_to_agent(step.agent_name, task, context)
        # ... rest of execution
```

## Test Cases

### Test 1: Search → Add All
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "find black jacket"}'
# Returns 10 products

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "add all to my cart"}'
# Should add all 10 products to cart
```

### Test 2: Search → Select Some → Add
```bash
# User searches, sees results, selects specific items
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "find white shirt"}'

# User wants specific ones
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "add item 1, 3, and 5 to cart"}'
```

### Test 3: Search → Checkout Flow
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "find blue dress and checkout"}'
```

## Configuration

```bash
# Environment variables
ORCHESTRATOR_MAX_CONVERSATION_HISTORY=20
ORCHESTRATOR_ENABLE_MULTI_AGENT=true
ORCHESTRATOR_WORKFLOW_TIMEOUT_SECONDS=300  # Clear state after 5 min
```

## Key Improvements

| Issue | Solution |
|-------|----------|
| No context between turns | EnhancedConversationManager with structured data |
| Lost search results | WorkflowStateManager tracks last_search_results |
| "Add all" doesn't work | Context-aware planner detects "all" + uses previous products |
| Single item limitation | Pass all product_ids to Order Agent |
| No re-planning | Planner checks workflow_state.pending_action |
