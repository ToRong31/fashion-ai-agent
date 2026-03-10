"""
OrderProcessingSkill — handles cart management, order creation, and payment.

Tools:
  - search_products: find products by name/description to get IDs
  - add_to_cart: add a product to the user's shopping cart
  - create_order: create an order with specified product IDs
  - get_payment_link: generate a VNPay payment link for an order
"""
import structlog

from shared.base.skill import Skill, ToolDefinition, ToolResult
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class OrderProcessingSkill(Skill):
    """Handles the complete order flow: cart → order → payment."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def id(self) -> str:
        return "order-processing"

    @property
    def name(self) -> str:
        return "Order Processing"

    @property
    def description(self) -> str:
        return (
            "Handles shopping cart, order creation, and payment link generation. "
            "Supports adding items to cart, placing orders, and VNPay checkout."
        )

    @property
    def tags(self) -> list[str]:
        return ["order", "buy", "purchase", "checkout", "cart", "payment", "add to cart", "mua", "giỏ hàng"]

    @property
    def examples(self) -> list[str]:
        return [
            "I want to buy this jacket",
            "Add the black blazer to my cart",
            "Purchase product 1 and product 3",
            "Checkout my order",
        ]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_products",
                description="Search for clothing products to find their IDs and details before ordering",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Product search query, e.g. 'black jeans', 'casual sneakers'",
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="add_to_cart",
                description="Add a product to the user's shopping cart",
                parameters={
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "The product ID to add"},
                        "product_name": {"type": "string", "description": "The product name"},
                        "price": {"type": "number", "description": "The product price"},
                        "quantity": {"type": "integer", "description": "Quantity to add (default 1)"},
                    },
                    "required": ["product_id", "product_name", "price"],
                },
            ),
            ToolDefinition(
                name="create_order",
                description="Create a new order for a user with specified product IDs",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "The user's ID"},
                        "product_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of product IDs to include in the order",
                        },
                    },
                    "required": ["user_id", "product_ids"],
                },
            ),
            ToolDefinition(
                name="get_payment_link",
                description="Generate a VNPay payment link for a created order",
                parameters={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "integer", "description": "The order ID"},
                    },
                    "required": ["order_id"],
                },
            ),
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "search_products":
            result = await self._backend.vector_search(args["query"])
            products = result.get("products", [])
            logger.info("order_search_products", query=args["query"], count=len(products))
            return ToolResult(content=products)

        if tool_name == "add_to_cart":
            cart_item = {
                "product_id": args["product_id"],
                "product_name": args["product_name"],
                "price": args["price"],
                "quantity": args.get("quantity", 1),
            }
            logger.info("add_to_cart", product_id=args["product_id"], name=args["product_name"])
            return ToolResult(
                content={"status": "added", "item": cart_item},
                data={"action": "add_to_cart", "cart_item": cart_item},
            )

        if tool_name == "create_order":
            result = await self._backend.auto_create_order(args["user_id"], args["product_ids"])
            logger.info("order_created", order_id=result.get("id"))
            return ToolResult(content=result, data={"order": result})

        if tool_name == "get_payment_link":
            result = await self._backend.get_payment_link(args["order_id"])
            logger.info("payment_link_generated", order_id=args["order_id"])
            return ToolResult(
                content=result,
                data={"payment_url": result.get("payment_url", "")},
            )

        raise ValueError(f"Unknown tool: {tool_name}")

    def get_prompt_instructions(self) -> str:
        return (
            "You handle shopping cart and order operations.\n\n"
            "When a user wants to ADD TO CART:\n"
            "1. Call search_products to find the product by name.\n"
            "2. Call add_to_cart with the found product's id, name, and price.\n"
            "3. Confirm what was added to the cart.\n\n"
            "When a user wants to BUY/ORDER/CHECKOUT:\n"
            "1. Call search_products to find the product by name.\n"
            "2. Call create_order with the user's ID and the found product IDs.\n"
            "3. Call get_payment_link to generate the VNPay payment link.\n"
            "4. Present the order summary and payment link.\n\n"
            "If user_id is provided in brackets like [user_id=3], use that ID.\n"
            "If not mentioned, default to user_id=1.\n"
            "NEVER ask the user what they want — execute the task directly."
        )
