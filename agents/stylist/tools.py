import structlog

from shared.backend_client import BackendClient

logger = structlog.get_logger()


class StylistTools:
    """Pure backend API wrappers — no LLM logic here."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    async def search_products(self, query: str, top_k: int = 8) -> list[dict]:
        logger.info("stylist_searching_products", query=query, top_k=top_k)
        try:
            result = await self._backend.vector_search(query, top_k)
            products = result.get("products", [])
            logger.info("stylist_search_results", count=len(products))
            return products
        except Exception as e:
            logger.error("stylist_search_failed", error=str(e))
            raise

    async def get_product_catalog(self) -> list[dict]:
        logger.info("stylist_fetching_catalog")
        result = await self._backend.get_products()
        products = result.get("products", [])
        logger.info("catalog_fetched", count=len(products))
        return products

    async def get_user_preferences(self, user_id: int) -> dict:
        logger.info("fetching_user_preferences", user_id=user_id)
        try:
            user_data = await self._backend.get_user(user_id)
            return user_data.get("preferences", {})
        except Exception as e:
            logger.warning("failed_to_fetch_preferences", user_id=user_id, error=str(e))
            return {}
