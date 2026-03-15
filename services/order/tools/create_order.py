"""create_order tool for Order Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class CreateOrderTool(BaseTool):
    """Tool to create a new order for a user with specified product IDs."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "create_order"

    @property
    def description(self) -> str:
        return "Create a new order for a user with specified product IDs"

    @property
    def parameters(self) -> dict:
        return {
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
        }

    async def execute(self, args: dict, context: dict) -> dict:
        user_id = args["user_id"]
        product_ids = args["product_ids"]
        logger.info("create_order", user_id=user_id, product_ids=product_ids)

        result = await self._backend.auto_create_order(user_id, product_ids)
        return result
