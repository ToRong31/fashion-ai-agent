"""Outfit Recommendation Skill - AI fashion stylist for coordinated outfit suggestions."""
import structlog

from shared.base_agent.skill import Skill, ToolDefinition, ToolResult
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class OutfitRecommendationSkill(Skill):
    """Creates coordinated outfit recommendations from the product catalog."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def id(self) -> str:
        return "outfit-recommendation"

    @property
    def name(self) -> str:
        return "Outfit Recommendation"

    @property
    def description(self) -> str:
        return (
            "AI fashion stylist that creates coordinated outfit recommendations "
            "based on user preferences, occasion, and season"
        )

    @property
    def tags(self) -> list[str]:
        return ["stylist", "outfit", "fashion-advice", "recommendation", "style", "wear", "suggest"]

    @property
    def examples(self) -> list[str]:
        return [
            "Style me an outfit for a winter meeting",
            "What should I wear for a casual date?",
            "Recommend a formal look for an interview",
        ]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_products",
                description="Search for clothing products matching a specific description, style, occasion, or category",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query, e.g. 'formal blazer', 'summer dress', 'casual sneakers men'",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Max results to return (default 8)",
                            "default": 8,
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="get_product_catalog",
                description="Fetch the complete product catalog — use when you need a broad selection of all available items",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="get_user_preferences",
                description="Fetch a user's stored style preferences (preferred size, color, style) to personalise the outfit",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "The user's ID"},
                    },
                    "required": ["user_id"],
                },
            ),
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "search_products":
            result = await self._backend.vector_search(args["query"], args.get("top_k", 8))
            products = result.get("products", [])
            logger.info("stylist_search", query=args["query"], count=len(products))
            return ToolResult(content=products)

        if tool_name == "get_product_catalog":
            result = await self._backend.get_products()
            products = result.get("products", [])
            logger.info("catalog_fetched", count=len(products))
            return ToolResult(content=products)

        if tool_name == "get_user_preferences":
            user_data = await self._backend.get_user(args["user_id"])
            prefs = user_data.get("preferences", {})
            logger.info("user_preferences_fetched", user_id=args["user_id"])
            return ToolResult(content=prefs)

        raise ValueError(f"Unknown tool: {tool_name}")

    def get_prompt_instructions(self) -> str:
        return (
            "You are a professional fashion stylist.\n\n"
            "Steps:\n"
            "1. Optionally fetch user preferences if user_id is known.\n"
            "2. Search for relevant products (by occasion, style, season, gender).\n"
            "3. Recommend a complete coordinated outfit using ONLY products from the catalog.\n"
            "4. Return a JSON object:\n"
            "```json\n"
            "{\n"
            '  "outfit_name": "Name of the outfit",\n'
            '  "occasion": "What occasion this outfit is for",\n'
            '  "items": [\n'
            '    {"product_id": 1, "name": "Product name", "price": 89.99, "role": "Role in outfit"}\n'
            "  ],\n"
            '  "reasoning": "Why these items work together",\n'
            '  "styling_tips": "Additional styling advice"\n'
            "}\n"
            "```\n\n"
            "Use real product IDs from search results.\n"
            "Always recommend a complete outfit (top + bottom + shoes at minimum)."
        )
