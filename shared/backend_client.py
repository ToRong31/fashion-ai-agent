import contextvars
import httpx
import structlog

from shared.config import BackendSettings

logger = structlog.get_logger()

# Context variable to store JWT token for the current request
_current_token: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_token", default=None)


class BackendClient:
    """Async HTTP client for calling the Spring Boot backend APIs."""

    def __init__(self, settings: BackendSettings | None = None, token: str | None = None):
        self._settings = settings or BackendSettings()
        self._token = token
        self._client: httpx.AsyncClient | None = None

    def set_token(self, token: str) -> None:
        """Set JWT token for authenticated requests."""
        self._token = token

    def clear_token(self) -> None:
        """Clear JWT token."""
        self._token = None

    def get_effective_token(self) -> str | None:
        """Get the effective token: instance token or context token."""
        if self._token:
            return self._token
        return _current_token.get()

    @staticmethod
    def set_context_token(token: str | None) -> None:
        """Set token in the current context (for request-scoped tokens)."""
        _current_token.set(token)

    @staticmethod
    def clear_context_token() -> None:
        """Clear token from the current context."""
        _current_token.set(None)

    async def _get_client(self) -> httpx.AsyncClient:
        # Get effective token from instance or context
        effective_token = self.get_effective_token()

        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if effective_token:
                headers["Authorization"] = f"Bearer {effective_token}"
            self._client = httpx.AsyncClient(
                base_url=self._settings.base_url,
                timeout=self._settings.timeout,
                headers=headers,
            )
        else:
            # Update headers if token changed
            if effective_token:
                self._client.headers["Authorization"] = f"Bearer {effective_token}"
            elif "Authorization" in self._client.headers:
                del self._client.headers["Authorization"]
        return self._client

    async def vector_search(self, query: str, top_k: int = 5) -> dict:
        client = await self._get_client()
        response = await client.post(
            "/api/products/vector-search",
            json={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        return response.json()

    async def get_product(self, product_id: int) -> dict:
        client = await self._get_client()
        response = await client.get(f"/api/products/{product_id}")
        response.raise_for_status()
        return response.json()

    async def get_products(self) -> dict:
        client = await self._get_client()
        response = await client.get("/api/products")
        response.raise_for_status()
        return response.json()

    async def get_user(self, user_id: int) -> dict:
        client = await self._get_client()
        response = await client.get(f"/api/users/{user_id}")
        response.raise_for_status()
        return response.json()

    async def update_user_profile(self, user_id: int, preferences: dict) -> dict:
        client = await self._get_client()
        response = await client.patch(
            "/api/users/profile",
            json={"user_id": user_id, "preferences": preferences},
        )
        response.raise_for_status()
        return response.json()

    async def auto_create_order(self, user_id: int, product_ids: list[int]) -> dict:
        client = await self._get_client()
        response = await client.post(
            "/api/orders/auto-create",
            json={"user_id": user_id, "product_ids": product_ids},
        )
        response.raise_for_status()
        return response.json()

    async def get_payment_link(self, order_id: int) -> dict:
        client = await self._get_client()
        response = await client.get(
            "/api/payments/vnpay-gen",
            params={"orderId": order_id},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
