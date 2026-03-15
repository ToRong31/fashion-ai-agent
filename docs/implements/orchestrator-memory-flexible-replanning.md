# Orchestrator Memory & Flexible Re-Planning

> Implement conversation context for multi-agent workflows using simple history

## Implementation Status: ✅ COMPLETED (SIMPLIFIED)

| Component | Status | File |
|-----------|--------|------|
| SmartConversationManager | ✅ Done | `services/orchestrator/conversation.py` |
| Context-Aware PlanningAgent | ✅ Done | `services/orchestrator/planning_agent.py` |
| Multi-Item PlanExecutor | ✅ Done | `services/orchestrator/plan_executor.py` |
| Orchestrator Main Integration | ✅ Done | `services/orchestrator/main.py` |

## Configuration

```bash
# Environment variables (already set in code)
ORCHESTRATOR_ENABLE_MULTI_AGENT=true  # Enable multi-agent planning
```

## Problem (Before)

Each user message was planned independently - the system didn't remember what products were shown in previous messages.

## Solution: Simple History (3 Pairs + Summary)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SmartConversationManager                      │
│                                                                  │
│  Keeps conversation in a simple sliding window:                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Last 3 pairs (6 messages) = FULL conversation           │   │
│  │                                                          │   │
│  │  User: find black jacket                                 │   │
│  │  Bot: Here are 10 black jackets [products data]          │   │
│  │  User: add all to cart                                   │   │
│  │  Bot: Added all 10 to cart                               │   │
│  │  User: find white shirt                                   │   │
│  │  Bot: Here are 5 white shirts [products data]            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Older messages = 1 SUMMARY                               │   │
│  │                                                          │   │
│  │ "Earlier: showed products, added to cart..."             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

### Step 1: User searches
```
User: "find black jacket"
→ Search Agent returns 10 products
→ Products stored in conversation message
```

### Step 2: User says "add all"
```
User: "add all to my cart"
→ Planner sees "all" in message
→ Planner looks at conversation history
→ Finds 10 products from previous message
→ Creates plan to add all 10 products
```

## Implementation Details

### SmartConversationManager
```python
class SmartConversationManager:
    FULL_PAIRS = 3  # Keep last 3 pairs

    def add_message(self, user_id, role, content, products=None, ...):
        # Store message with products
        # Auto-summarize if > 3 pairs

    def get_history_for_llm(self, user_id):
        # Returns: [summary] + [last 3 pairs]
        # This is sent to the planner

    def get_last_products(self, user_id):
        # Returns products from last assistant message
```

### Planning Agent Context Detection
```python
async def create_plan(self, user_message, context, history):
    # 1. Get products from history
    products = self._extract_products_from_history(history)

    # 2. Check "add all"
    if self._wants_all_items(user_message) and products:
        return self._plan_add_all(products)

    # 3. Check specific items ("item 1, 3, 5")
    if self._extract_item_selections(user_message, products):
        return self._plan_add_specific(...)

    # 4. Continue previous flow ("add them to cart")
    if self._is_continuation(user_message) and products:
        return self._plan_with_previous_products(...)
```

## Test Cases

### Test 1: Search → Add All
```bash
# Step 1: Search
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "find black jacket"}'
# Returns 10 products, stored in conversation

# Step 2: Add all (planner sees history)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "add all to my cart"}'
# Planner finds 10 products in history → adds all 10 ✅
```

### Test 2: Search → Select Specific
```bash
# Step 1: Search
curl .../chat -d '{"message": "find white shirt"}'

# Step 2: Select specific items
curl .../chat -d '{"message": "add item 1 and 3 to cart"}'
# Planner extracts items 1,3 from history → adds those ✅
```

### Test 3: Search → Continue
```bash
# Step 1: Search
curl .../chat -d '{"message": "find blue dress"}'

# Step 2: Add to cart
curl .../chat -d '{"message": "add them to my cart"}'
# Planner sees "them" + finds products in history → adds ✅
```

## Key Benefits

| Before | After |
|--------|-------|
| Separate state management | Just conversation history |
| Complex workflow state | Simple sliding window |
| LLM doesn't see context | LLM sees full conversation |
| Products lost after response | Products in message history |
