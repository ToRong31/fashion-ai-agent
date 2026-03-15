"""get_payment_link tool for Order Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class GetPaymentLinkTool(BaseTool):
    """Tool to generate a VNPay payment link for a created order."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "get_payment_link"

    @property
    def description(self) -> str:
        return "Generate a VNPay payment link for a created order"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "The order ID"},
            },
            "required": ["order_id"],
        }

    async def execute(self, args: dict, context: dict) -> dict:
        order_id = args["order_id"]
        logger.info("get_payment_link", order_id=order_id)

        result = await self._backend.get_payment_link(order_id)
        return result
