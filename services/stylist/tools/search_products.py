"""search_products tool for Stylist Agent."""
import structlog
from shared.base_agent.tool import BaseTool
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
        return "Search for clothing products matching a specific description, style, occasion, or category"

    @property
    def parameters(self) -> dict:
        return {
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
        }

    async def execute(self, args: dict, context: dict) -> dict:
        query = args.get("query", "")
        top_k = args.get("top_k", 8)
        logger.info("stylist_search_products", query=query, top_k=top_k)

        result = await self._backend.vector_search(query, top_k)
        return result.get("products", [])
