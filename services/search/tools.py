import structlog

from shared.backend_client import BackendClient

logger = structlog.get_logger()


class SearchTools:
    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    async def search_products(self, query: str, top_k: int = 5) -> list[dict]:
        logger.info("searching_products", query=query, top_k=top_k)
        try:
            result = await self._backend.vector_search(query, top_k)
            products = result.get("products", [])
            logger.info("search_results", count=len(products))
            return products
        except Exception as e:
            logger.error("search_failed", error=str(e))
            raise
