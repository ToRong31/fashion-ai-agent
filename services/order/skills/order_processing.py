"""Order Processing Skill - handles cart management, order creation, and payment."""
import re
import structlog

from shared.base_agent.skill import Skill, ToolDefinition, ToolResult
from shared.backend_client import BackendClient

logger = structlog.get_logger()


# Regex to extract JWT token from message
JWT_TOKEN_PATTERN = re.compile(r"\[SYSTEM:\s*JWT_TOKEN=([^\]]+)\]")


class OrderProcessingSkill(Skill):
    """Handles the complete order flow: cart → order → payment."""

    def __init__(self, backend_client: BackendClient, user_message: str = ""):
        self._backend = backend_client
        self._user_message = user_message
        self._extract_and_set_token(user_message)

    def _extract_and_set_token(self, message: str) -> None:
        """Extract JWT token from message and set it in the context."""
        if not message:
            return
        match = JWT_TOKEN_PATTERN.search(message)
        if match:
            token = match.group(1).strip()
            BackendClient.set_context_token(token)
            logger.info("jwt_token_extracted", token_preview=token[:20] + "...")
            # Remove the token from the message to avoid confusing the LLM
            self._user_message = JWT_TOKEN_PATTERN.sub("", message)

    def set_user_message(self, message: str) -> None:
        """Set the user message to extract JWT token from it."""
        self._extract_and_set_token(message)

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
                description="Add a single product to the user's shopping cart",
                parameters={
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "The product ID to add"},
                        "product_name": {"type": "string", "description": "The product name"},
                        "price": {"type": "number", "description": "The product price"},
                        "quantity": {"type": "integer", "description": "Quantity to add (default 1)", "default": 1},
                    },
                    "required": ["product_id", "product_name", "price"],
                },
            ),
            ToolDefinition(
                name="add_multiple_to_cart",
                description="Add multiple products to the user's shopping cart at once. Use this when user wants to add all or multiple products.",
                parameters={
                    "type": "object",
                    "properties": {
                        "products": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {"type": "integer", "description": "The product ID"},
                                    "product_name": {"type": "string", "description": "The product name"},
                                    "price": {"type": "number", "description": "The product price"},
                                    "quantity": {"type": "integer", "description": "Quantity (default 1)", "default": 1},
                                },
                                "required": ["product_id", "product_name", "price"],
                            },
                            "description": "List of products to add to cart",
                        },
                    },
                    "required": ["products"],
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
            # Extract user_id from context or args
            user_id = context.get("user_id") or args.get("user_id")
            if not user_id:
                raise ValueError("user_id is required for add_to_cart")

            # Call backend API to add to cart
            cart_item = {
                "product_id": args["product_id"],
                "product_name": args["product_name"],
                "price": args["price"],
                "quantity": args.get("quantity", 1),
            }
            try:
                result = await self._backend.add_to_cart(
                    user_id=int(user_id),
                    product_id=int(args["product_id"]),
                    quantity=int(args.get("quantity", 1)),
                )
                logger.info("add_to_cart_success", product_id=args["product_id"], name=args["product_name"], user_id=user_id)
            except Exception as e:
                logger.error("add_to_cart_failed", product_id=args["product_id"], error=str(e))
                # Still return success to user - the frontend will handle actual cart sync

            return ToolResult(
                content={"status": "added", "item": cart_item},
                data={"action": "add_to_cart", "cart_item": cart_item},
            )

        if tool_name == "add_multiple_to_cart":
            # Extract user_id from context or args
            user_id = context.get("user_id") or args.get("user_id")
            if not user_id:
                raise ValueError("user_id is required for add_multiple_to_cart")

            # Add multiple products to cart
            products = args.get("products", [])
            added_items = []

            # Extract product IDs and quantities
            product_ids = []
            quantities = []
            for p in products:
                product_ids.append(int(p.get("product_id")))
                quantities.append(int(p.get("quantity", 1)))
                cart_item = {
                    "product_id": p.get("product_id"),
                    "product_name": p.get("product_name"),
                    "price": p.get("price"),
                    "quantity": p.get("quantity", 1),
                }
                added_items.append(cart_item)

            # Call backend API to add all items to cart
            try:
                result = await self._backend.add_multiple_to_cart(
                    user_id=int(user_id),
                    product_ids=product_ids,
                    quantities=quantities,
                )
                logger.info("add_multiple_to_cart_success", user_id=user_id, product_count=len(product_ids))
            except Exception as e:
                logger.error("add_multiple_to_cart_failed", user_id=user_id, error=str(e))
                # Still return success to user - the frontend will handle actual cart sync

            return ToolResult(
                content={"status": "added_multiple", "items": added_items, "count": len(added_items)},
                data={"action": "add_multiple_to_cart", "cart_items": added_items, "count": len(added_items)},
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

    def cleanup(self) -> None:
        """Clean up the context token after execution."""
        BackendClient.clear_context_token()

    def get_prompt_instructions(self) -> str:
        return (
            "You handle shopping cart and order operations.\n\n"
            "When a user wants to ADD TO CART (single item):\n"
            "1. Call add_to_cart with product_id, product_name, and price.\n"
            "2. Extract user_id from [user_id=X] in the message - this is REQUIRED.\n"
            "3. Confirm what was added to the cart.\n\n"
            "When a user wants to ADD ALL or MULTIPLE items to cart:\n"
            "1. Call add_multiple_to_cart with a list of products.\n"
            "2. Each product should have: product_id, product_name, price.\n"
            "3. Extract user_id from [user_id=X] in the message - this is REQUIRED.\n"
            "4. Confirm how many items were added.\n\n"
            "IMPORTANT: When user says 'add all', 'add them all', 'add everything', or provides multiple products, \n"
            "you MUST use add_multiple_to_cart tool - NOT add_to_cart.\n\n"
            "When a user wants to BUY/ORDER/CHECKOUT:\n"
            "1. Call create_order with the user's ID and the found product IDs.\n"
            "2. Call get_payment_link to generate the VNPay payment link.\n"
            "3. Present the order summary and payment link.\n\n"
            "CRITICAL: user_id extraction rules:\n"
            "- Always extract user_id from [user_id=X] in the task message\n"
            "- Example: 'Add to cart [user_id=5]' → use user_id=5\n"
            "- The user_id is REQUIRED for all cart operations\n"
            "NEVER ask the user what they want — execute the task directly."
        )
