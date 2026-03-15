"""get_product_catalog tool for Stylist Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class GetProductCatalogTool(BaseTool):
    """Tool to fetch the complete product catalog."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "get_product_catalog"

    @property
    def description(self) -> str:
        return "Fetch the complete product catalog — use when you need a broad selection of all available items"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, args: dict, context: dict) -> dict:
        logger.info("stylist_get_catalog")
        result = await self._backend.get_products()
        return result.get("products", [])
