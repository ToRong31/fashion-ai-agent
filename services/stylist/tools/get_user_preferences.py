"""get_user_preferences tool for Stylist Agent."""
import structlog
from shared.base_agent.tool import BaseTool
from shared.backend_client import BackendClient

logger = structlog.get_logger()


class GetUserPreferencesTool(BaseTool):
    """Tool to fetch user's stored style preferences."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def name(self) -> str:
        return "get_user_preferences"

    @property
    def description(self) -> str:
        return "Fetch a user's stored style preferences (preferred size, color, style) to personalise the outfit"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "The user's ID"},
            },
            "required": ["user_id"],
        }

    async def execute(self, args: dict, context: dict) -> dict:
        user_id = args.get("user_id", 1)
        logger.info("stylist_get_user_preferences", user_id=user_id)

        user_data = await self._backend.get_user(user_id)
        return user_data.get("preferences", {})
