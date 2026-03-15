# Recent Implementation Changes

This document covers the recent improvements made to the ToRoMe AI Agent system.

## Table of Contents

1. [Order Agent API Integration](#order-agent-api-integration)
2. [Smart Conversation Manager](#smart-conversation-manager)
3. [Multi-Agent Planning](#multi-agent-planning)
4. [Agent Card Endpoint Update](#agent-card-endpoint-update)

---

## Order Agent API Integration

### Problem

The Order Agent's `add_to_cart` and `add_multiple_to_cart` tools were **not calling the backend API**. They simply returned fake success responses without actually adding items to the database.

### Solution

Added real backend API calls to the Order Agent tools.

### Changes

#### 1. `shared/backend_client.py`

Added two new methods:

```python
async def add_to_cart(self, user_id: int, product_id: int, quantity: int = 1) -> dict:
    """Add a single product to the user's cart."""
    client = await self._get_client()
    response = await client.post(
        "/api/cart/items",
        json={"user_id": user_id, "product_id": product_id, "quantity": quantity},
    )
    response.raise_for_status()
    return response.json()

async def add_multiple_to_cart(self, user_id: int, product_ids: list[int], quantities: list[int] | None = None) -> dict:
    """Add multiple products to the user's cart (sequential calls)."""
    quantities = quantities or [1] * len(product_ids)
    results = []
    for product_id, quantity in zip(product_ids, quantities):
        result = await self.add_to_cart(user_id, product_id, quantity)
        results.append(result)
    return {"status": "added", "items": results, "count": len(results)}
```

#### 2. `services/order/skills/order_processing.py`

Updated `add_to_cart` tool:

```python
if tool_name == "add_to_cart":
    user_id = context.get("user_id") or args.get("user_id")
    if not user_id:
        raise ValueError("user_id is required for add_to_cart")

    # Call backend API
    result = await self._backend.add_to_cart(
        user_id=int(user_id),
        product_id=int(args["product_id"]),
        quantity=int(args.get("quantity", 1)),
    )
```

Updated `add_multiple_to_cart` tool similarly.

---

## Smart Conversation Manager

### Problem

The orchestrator needed to track conversation history so when a user says "add all to cart", it knows which products from the previous search to add.

### Solution

Implemented `SmartConversationManager` with sliding window memory (last 3 message pairs + summary).

### Changes

#### `services/orchestrator/conversation.py`

```python
class SmartConversationManager:
    """Manages conversation history with sliding window (last 3 pairs + summary)."""

    FULL_PAIRS = 3  # Keep last 3 pairs

    def add_message(self, user_id, role, content, products=None, agent_used=None):
        # Store message with optional products data
        # Auto-summarize if > 3 pairs

    def get_history_for_llm(self, user_id):
        # Returns: [summary] + [last 3 pairs]
```

### Key Features

- **Sliding Window**: Keeps last 3 user↔assistant message pairs
- **Auto-Summarization**: Summarizes older messages to preserve context
- **Product Tracking**: Stores products from search results in conversation
- **Context Extraction**: Planner extracts products from history for "add all" commands

---

## Multi-Agent Planning

### Problem

The system needed flexible planning to handle:
- Single agent requests (simple search)
- Sequential workflows (search → add to cart)
- Parallel workflows (search multiple things at once)

### Solution

Implemented `PlanningAgent` with execution modes:

#### Execution Modes

| Mode | Description | Example |
|------|-------------|---------|
| `SINGLE` | One agent handles request | "find black jacket" |
| `SEQUENTIAL` | Multiple agents, one after another | "find jacket and add to cart" |
| `PARALLEL` | Multiple agents simultaneously | "find white shirts and black pants" |

#### Key Methods

```python
# Detect "add all" intent
def _wants_all_items(self, message: str) -> bool:
    all_keywords = ["all", "tất cả", "add all", "add everything", "mua tất cả"]
    return any(kw in message.lower() for kw in all_keywords)

# Extract specific item selections
def _extract_item_selections(self, message: str, products: list) -> list:
    # Handle "item 1, 3, 5" patterns

# Plan to add all products
async def _plan_add_all(self, user_message, products, context):
    return ExecutionPlan(
        mode=ExecutionMode.SEQUENTIAL,
        steps=[ExecutionStep(
            agent_name="Order Agent",
            task="Add ALL products...",
            context={"product_ids": [...], "all_products": products}
        )]
    )
```

---

## Agent Card Endpoint Update

### Problem

A2A SDK showed deprecation warning:

```
WARNING: Deprecated agent card endpoint '/.well-known/agent.json' accessed.
Please use '/.well-known/agent-card.json' instead.
```

### Solution

Updated all references from `/agent.json` to `/agent-card.json`.

### Files Changed

| File | Change |
|------|--------|
| `.env` | Updated agent card URLs |
| `docker-compose.yml` | Updated health checks and env vars |
| `services/orchestrator/main.py` | Updated default URLs |
| `services/*/Dockerfile` | Updated health checks |
| `.env.example` | Updated example |

### Example

```bash
# Before
ORCHESTRATOR_SEARCH_AGENT_CARD_URL=http://search:8001/.well-known/agent.json

# After
ORCHESTRATOR_SEARCH_AGENT_CARD_URL=http://search:8001/.well-known/agent-card.json
```

---

## User ID Passing Flow

To ensure the Order Agent knows which user to add cart items for, the flow is:

```
1. Frontend sends message with JWT token in Authorization header
2. Orchestrator extracts user_id and passes via context
3. PlanningAgent adds [user_id=X] to task message
4. Order Agent extracts user_id from message
5. Order Agent calls backend API with user_id
```

### Example Task Message

```
Add ALL 10 products to cart using add_multiple_to_cart tool.

Products to add:
1. ID:101 - Black Jacket - $199
2. ID:102 - Blue Jeans - $89
...

Call add_multiple_to_cart with the products list above. [user_id=5]
```

---

## Testing Checklist

- [ ] Search for products ("find black jacket")
- [ ] Say "add all to my cart" - verify items added to cart
- [ ] Check cart has correct items and quantities
- [ ] Test "add item 1, 3, 5" specific selection
- [ ] Verify conversation history persists across page reloads

---

## Related Files

- `services/orchestrator/main.py` - Orchestrator entry point
- `services/orchestrator/planning_agent.py` - Multi-agent planner
- `services/orchestrator/plan_executor.py` - Plan execution
- `services/orchestrator/conversation.py` - Smart conversation manager
- `services/order/skills/order_processing.py` - Order tools
- `shared/backend_client.py` - Backend API client
- `fashion-ai-frontend/src/stores/chatStore.ts` - Frontend chat handling
