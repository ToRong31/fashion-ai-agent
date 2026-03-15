"""search_products tool for Search Agent."""
import structlog
from shared.base_agent.tool import BaseTool, ToolDefinition
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class SearchProductsTool(BaseTool):
    """Tool to search products via vector search."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "search_products"

    @property
    def description(self) -> str:
        return (
            "Search for clothing products in the ToRoMe Store catalog. "
            "Supports queries by product type, color, style, occasion, season, gender, or material."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'black dress for party', 'winter jacket men'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 5, max 20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: dict, context: dict) -> dict:
        query = args.get("query", "")
        top_k = args.get("top_k", 5)
        logger.info("search_products_executed", query=query, top_k=top_k)

        result = await self._backend.vector_search(query, top_k)
        return result
