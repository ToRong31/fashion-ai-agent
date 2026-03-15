"""add_to_cart tool for Order Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class AddToCartTool(BaseTool):
    """Tool to add a product to the user's shopping cart."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "add_to_cart"

    @property
    def description(self) -> str:
        return "Add a product to the user's shopping cart"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "The product ID to add"},
                "product_name": {"type": "string", "description": "The product name"},
                "price": {"type": "number", "description": "The product price"},
                "quantity": {"type": "integer", "description": "Quantity to add (default 1)", "default": 1},
            },
            "required": ["product_id", "product_name", "price"],
        }

    async def execute(self, args: dict, context: dict) -> dict:
        cart_item = {
            "product_id": args["product_id"],
            "product_name": args["product_name"],
            "price": args["price"],
            "quantity": args.get("quantity", 1),
        }
        logger.info("add_to_cart", product_id=args["product_id"], name=args["product_name"])
        return {"status": "added", "item": cart_item}
