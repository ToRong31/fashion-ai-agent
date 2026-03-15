"""Order Agent — handles cart management, order creation, and payment."""
import os

from shared.base_agent.agent import BaseAgent
from services.order.skills.order_processing import OrderProcessingSkill
from services.order.skills.order_with_search import OrderWithSearchSkill
from shared.backend_client import BackendClient


def build_order_agent(
    backend_client: BackendClient,
    use_a2a_search: bool = False,
    search_agent_url: str | None = None,
) -> BaseAgent:
    """
    Build Order Agent with optional A2A search delegation.

    Args:
        backend_client: Backend client for API calls
        use_a2a_search: If True, use Search Agent via A2A for product search
        search_agent_url: URL of Search Agent (default: http://search:8001)

    Returns:
        Configured Order Agent
    """
    agent = BaseAgent(
        name="Order Agent",
        description=(
            "Handles shopping cart, order creation, and payment link generation. "
            "Supports adding items to cart, placing orders, and VNPay checkout."
        ),
    )

    # Check env var for A2A search mode
    use_a2a = use_a2a_search or os.getenv("ORDER_AGENT_USE_A2A_SEARCH", "false").lower() == "true"
    search_url = search_agent_url or os.getenv("SEARCH_AGENT_URL", "http://search:8001")

    if use_a2a:
        # Use the new skill that delegates to Search Agent via A2A
        agent.register_skill(
            OrderWithSearchSkill(
                backend_client=backend_client,
                search_agent_url=search_url,
            )
        )
    else:
        # Use original skill with direct backend search
        agent.register_skill(OrderProcessingSkill(backend_client))

    return agent
