"""search_products tool for Order Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class SearchProductsTool(BaseTool):
    """Tool to search products by name/description to get IDs."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "search_products"

    @property
    def description(self) -> str:
        return "Search for clothing products to find their IDs and details before ordering"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product search query, e.g. 'black jeans', 'casual sneakers'",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: dict, context: dict) -> dict:
        query = args.get("query", "")
        logger.info("order_search_products", query=query)

        result = await self._backend.vector_search(query)
        return result.get("products", [])
