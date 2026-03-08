import structlog

from shared.backend_client import BackendClient

logger = structlog.get_logger()


class OrderTools:
    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    async def create_order(self, user_id: int, product_ids: list[int]) -> dict:
        logger.info("creating_order", user_id=user_id, product_ids=product_ids)
        try:
            result = await self._backend.auto_create_order(user_id, product_ids)
            logger.info("order_created", order_id=result.get("id"))
            return result
        except Exception as e:
            logger.error("order_creation_failed", error=str(e))
            raise

    async def get_payment_link(self, order_id: int) -> dict:
        logger.info("generating_payment_link", order_id=order_id)
        try:
            result = await self._backend.get_payment_link(order_id)
            logger.info("payment_link_generated", order_id=order_id)
            return result
        except Exception as e:
            logger.error("payment_link_failed", error=str(e))
            raise

    async def search_products(self, query: str) -> list[dict]:
        logger.info("order_agent_searching", query=query)
        result = await self._backend.vector_search(query)
        return result.get("products", [])
