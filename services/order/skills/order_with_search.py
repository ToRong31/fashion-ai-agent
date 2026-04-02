"""
Order with Search Skill - delegates product search to Search Agent via A2A.

This skill handles the complete order flow while delegating product search
to the Search Agent for better semantic search capabilities.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from shared.base_agent.skill import Skill, ToolDefinition, ToolResult
from shared.backend_client import BackendClient

logger = structlog.get_logger()


def _load_prompt(filename: str) -> str:
    yaml_path = Path(__file__).parent / "prompts" / filename
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["prompt"]


# Regex to extract JWT token from message
JWT_TOKEN_PATTERN = re.compile(r"\[SYSTEM:\s*JWT_TOKEN=([^\]]+)\]")


@dataclass
class SearchResult:
    """Product search result from Search Agent."""

    id: int
    name: str
    price: float
    image_url: str | None = None
    description: str | None = None


class A2ASearchClient:
    """
    A2A client for delegating search to Search Agent.

    This wraps the A2A protocol to call the Search Agent remotely.
    """

    def __init__(self, search_agent_url: str):
        self._search_agent_url = search_agent_url
        self._client = None

    async def search_products(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search for products via Search Agent using A2A protocol.

        Args:
            query: Search query string
            top_k: Number of results to return

        Returns:
            List of product dicts from Search Agent
        """
        import httpx
        from a2a.client import A2AClient
        from a2a.client.card_resolver import A2ACardResolver
        from a2a.types import SendMessageRequest, MessageSendParams, Message, TextPart

        try:
            async with httpx.AsyncClient(timeout=30) as httpx_client:
                # Get agent card
                card_resolver = A2ACardResolver(httpx_client, self._search_agent_url)
                card = await card_resolver.get_agent_card()

                # Create A2A client
                a2a_client = A2AClient(httpx_client, card, url=self._search_agent_url)

                # Build message request
                message_id = f"search_{id(self)}"
                payload = {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": query}],
                        "messageId": message_id,
                    }
                }

                request = SendMessageRequest(
                    id=message_id,
                    params=MessageSendParams.model_validate(payload),
                )

                # Send to Search Agent
                response = await a2a_client.send_message(request)

                # Extract products from response
                return self._extract_products(response)

        except Exception as e:
            logger.error("a2a_search_failed", query=query, error=str(e))
            raise

    def _extract_products(self, response) -> list[dict]:
        """Extract product data from A2A response."""
        from a2a.types import Message, Task

        result = response.root.result if hasattr(response, "root") else response

        # Try to get data from Message or Task
        if isinstance(result, Message):
            for part in result.parts:
                pv = part.root if hasattr(part, "root") else part
                if hasattr(pv, "data") and isinstance(pv.data, dict):
                    return pv.data.get("products", [])
        elif isinstance(result, Task):
            if result.status and result.status.message:
                for part in result.status.message.parts:
                    pv = part.root if hasattr(part, "root") else part
                    if hasattr(pv, "data") and isinstance(pv.data, dict):
                        return pv.data.get("products", [])
            if result.artifacts:
                for artifact in result.artifacts:
                    for part in artifact.parts:
                        pv = part.root if hasattr(part, "root") else part
                        if hasattr(pv, "data") and isinstance(pv.data, dict):
                            return pv.data.get("products", [])

        return []


class OrderWithSearchSkill(Skill):
    """
    Order processing skill that delegates product search to Search Agent via A2A.

    This approach:
    - Leverages Search Agent's semantic search capabilities
    - Avoids code duplication
    - Allows Search Agent to evolve independently
    - Enables consistent search experience across all agents
    """

    def __init__(
        self,
        backend_client: BackendClient,
        search_agent_url: str = "http://search:8001",
        user_message: str = "",
    ):
        self._backend = backend_client
        self._search_client = A2ASearchClient(search_agent_url)
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
            self._user_message = JWT_TOKEN_PATTERN.sub("", message)

    def set_user_message(self, message: str) -> None:
        """Set the user message to extract JWT token from it."""
        self._extract_and_set_token(message)

    @property
    def id(self) -> str:
        return "order-with-search"

    @property
    def name(self) -> str:
        return "Order with Search"

    @property
    def description(self) -> str:
        return (
            "Handles shopping cart, order creation, and payment link generation. "
            "Uses Search Agent for product discovery via A2A protocol."
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
            "Find white shirt and add to cart",
        ]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_and_select_product",
                description="""Search for products using Search Agent via A2A, then select the best match.
                Use this when user wants to find a specific product by name, color, or style.
                Returns product details needed for ordering.""",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Product search query (e.g., 'white shirt', 'black dress')",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (default 5)",
                            "default": 5,
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
                        "quantity": {"type": "integer", "description": "Quantity to add (default 1)", "default": 1},
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
        if tool_name == "search_and_select_product":
            return await self._search_via_agent(args["query"], args.get("top_k", 5))

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

    async def _search_via_agent(self, query: str, top_k: int) -> ToolResult:
        """
        Delegate search to Search Agent via A2A protocol.

        Falls back to direct backend search if Search Agent is unavailable.
        """
        try:
            # Call Search Agent via A2A
            products = await self._search_client.search_products(query, top_k)
            logger.info("a2a_search_success", query=query, count=len(products))

            return ToolResult(
                content=f"Found {len(products)} products: {self._format_products(products)}",
                data={"products": products},
            )

        except Exception as e:
            logger.warning("a2a_search_failed_fallback", query=query, error=str(e))

            # Fallback to direct backend search
            try:
                result = await self._backend.vector_search(query, top_k)
                products = result.get("products", [])
                logger.info("fallback_search_success", query=query, count=len(products))
                return ToolResult(
                    content=f"Found {len(products)} products (fallback): {self._format_products(products)}",
                    data={"products": products, "fallback": True},
                )
            except Exception as fallback_error:
                logger.error("fallback_search_also_failed", error=str(fallback_error))
                return ToolResult(
                    content="Sorry, I couldn't find products at the moment.",
                    data={"error": str(fallback_error)},
                )

    def _format_products(self, products: list[dict]) -> str:
        """Format products for display."""
        if not products:
            return "No products found"

        lines = []
        for i, p in enumerate(products[:5], 1):
            name = p.get("name", "Unknown")
            price = p.get("price", 0)
            product_id = p.get("id", "?")
            lines.append(f"{i}. {name} (ID: {product_id}) - ${price}")

        return "\n".join(lines)

    def cleanup(self) -> None:
        """Clean up the context token after execution."""
        BackendClient.clear_context_token()

    def get_prompt_instructions(self) -> str:
        return _load_prompt("order-with-search.yaml")
