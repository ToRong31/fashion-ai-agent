# Order Agent

> Shopping cart management, order creation, and payment processing

## Purpose

The Order Agent handles **e-commerce transactions** including:
1. Adding products to shopping cart
2. Creating orders from cart items
3. Generating VNPay payment links
4. Order status tracking

## Development Context

- **File**: `services/order/agent.py`
- **Port**: 8003
- **Framework**: FastAPI + BaseAgent
- **Payment Gateway**: VNPay (Vietnamese payment provider)

## How It Works

### Agent Registration

```
main.py → build_order_agent()
  │
  └─→ BaseAgent(name="Order Agent")
       └─→ register_skill(OrderProcessingSkill)
            │
            └─→ Agent Card published at /.well-known/agent.json
```

### Skill: OrderProcessingSkill

File: `services/order/skills/order_processing.py`

```python
class OrderProcessingSkill(Skill):
    id: "order-processing"
    name: "Order Processing"

    def get_tools(self):
        - search_products: Find products before ordering
        - add_to_cart: Add item to shopping cart
        - create_order: Create order from products
        - get_payment_link: Generate VNPay payment URL

    async def execute_tool(tool_name, args):
        if tool_name == "search_products":
            → backend_client.vector_search()
        if tool_name == "add_to_cart":
            → Returns cart item (in-memory for current session)
        if tool_name == "create_order":
            → backend_client.auto_create_order()
        if tool_name == "get_payment_link":
            → backend_client.get_payment_link()
```

### Tools

#### 1. search_products
```json
{
    "name": "search_products",
    "description": "Search for clothing products to find their IDs and details before ordering",
    "parameters": {
        "query": "string - Product search query"
    }
}
```

#### 2. add_to_cart
```json
{
    "name": "add_to_cart",
    "description": "Add a product to the user's shopping cart",
    "parameters": {
        "product_id": "integer - The product ID to add",
        "product_name": "string - The product name",
        "price": "number - The product price",
        "quantity": "integer - Quantity (default 1)"
    }
}
```

#### 3. create_order
```json
{
    "name": "create_order",
    "description": "Create a new order for a user with specified product IDs",
    "parameters": {
        "user_id": "integer - The user's ID",
        "product_ids": "array[integer] - List of product IDs"
    }
}
```

#### 4. get_payment_link
```json
{
    "name": "get_payment_link",
    "description": "Generate a VNPay payment link for a created order",
    "parameters": {
        "order_id": "integer - The order ID"
    }
}
```

### Prompt Instructions

```python
def get_prompt_instructions(self):
    return """
    You handle shopping cart and order operations.

    When a user wants to ADD TO CART:
    1. Call search_products to find the product by name.
    2. Call add_to_cart with the found product's id, name, and price.
    3. Confirm what was added to the cart.

    When a user wants to BUY/ORDER/CHECKOUT:
    1. Call search_products to find the product by name.
    2. Call create_order with the user's ID and the found product IDs.
    3. Call get_payment_link to generate the VNPay payment link.
    4. Present the order summary and payment link.

    If user_id is provided in brackets like [user_id=3], use that ID.
    If not mentioned, default to user_id=1.
    NEVER ask the user what they want — execute the task directly.
    """
```

## Order Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Order Flow                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. SEARCH              2. ADD TO CART         3. CREATE ORDER  │
│  ┌──────────────┐      ┌──────────────┐        ┌──────────────┐ │
│  │ search_      │ ────►│ add_to_cart  │ ──────►│ create_order │ │
│  │ products()   │      │              │        │              │ │
│  └──────────────┘      └──────────────┘        └──────┬───────┘ │
│         │                      │                      │         │
│         ▼                      ▼                      ▼         │
│  ┌──────────────┐      ┌──────────────┐        ┌──────────────┐ │
│  │ Product IDs  │      │ Cart Item    │        │ Order ID     │ │
│  │ + Details    │      │ Confirmed    │        │ + Summary    │ │
│  └──────────────┘      └──────────────┘        └──────┬───────┘ │
│                                                       │         │
│                                                       ▼         │
│                                              4. PAYMENT        │
│                                              ┌──────────────┐  │
│                                              │ get_payment  │  │
│                                              │ _link()      │  │
│                                              └──────┬───────┘  │
│                                                     │          │
│                                                     ▼          │
│                                              ┌──────────────┐  │
│                                              │ VNPay URL    │  │
│                                              │ for checkout │  │
│                                              └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## User ID Handling

The Order Agent extracts user ID from message context:

```python
# In prompt instructions:
# "If user_id is provided in brackets like [user_id=3], use that ID."
# "If not mentioned, default to user_id=1."

# Example: "Add [user_id=5] product 1 to cart"
```

This allows the Orchestrator to pass user context:
```
"Find me a black jacket and add to cart [user_id=3]"
```

## A2A Protocol

### Agent Card

```json
{
    "name": "Order Agent",
    "description": "Handles shopping cart, order creation, and payment link generation. Supports adding items to cart, placing orders, and VNPay checkout.",
    "skills": [{
        "id": "order-processing",
        "name": "Order Processing",
        "description": "Handles shopping cart, order creation, and payment link generation",
        "tags": ["order", "buy", "purchase", "checkout", "cart", "payment", "add to cart", "mua", "giỏ hàng"],
        "examples": [
            "I want to buy this jacket",
            "Add the black blazer to my cart",
            "Purchase product 1 and product 3",
            "Checkout my order"
        ]
    }]
}
```

## Tags & Intent Matching

```python
tags = ["order", "buy", "purchase", "checkout", "cart", "payment", "add to cart", "mua", "giỏ hàng"]
```

| Tag | Example Triggers |
|-----|------------------|
| order | "order", "đặt hàng" |
| buy | "buy", "mua" |
| purchase | "purchase", "mua" |
| checkout | "checkout", "thanh toán" |
| cart | "cart", "giỏ hàng" |
| payment | "payment", "payment" |

## Backend Integration

### Auto-Create Order API

```
POST /api/orders/auto-create
{
    "user_id": 1,
    "product_ids": [1, 3, 5]
}

Response:
{
    "id": 123,
    "user_id": 1,
    "status": "PENDING",
    "items": [...],
    "total_amount": 299.99,
    "created_at": "2026-03-15T10:30:00Z"
}
```

### VNPay Payment Link API

```
GET /api/payments/vnpay-gen?orderId=123

Response:
{
    "order_id": 123,
    "payment_url": "https://sandbox.vnpayment.vn/..."
}
```

## Example Conversations

| User Message | Expected Behavior |
|-------------|-------------------|
| "I want to buy this jacket" | Search jacket → Create order → Get payment link |
| "Add the black blazer to my cart" | Search blazer → Add to cart → Confirm |
| "Purchase product 1 and product 3" | Create order with products 1,3 → Get payment link |
| "Checkout my order" | Get payment link for user's cart |

## Claude Code Development Notes

1. **Persistent cart**: Currently in-memory; consider Redis for production
2. **Order validation**: Add stock checking before order creation
3. **Multiple payment methods**: Add more payment gateways beyond VNPay
4. **Order history**: Track order status and history
5. **Discount codes**: Add promo code support

## Testing

```bash
# Health check
curl http://localhost:8003/health

# Test order creation
curl -X POST http://localhost:8003/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "I want to buy product 1"}],
      "metadata": {"user_id": "1"}
    }
  }'
```
