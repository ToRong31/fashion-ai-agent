"""Search Agent — product catalog search via semantic vector search."""
from agents.base.agent import BaseAgent
from agents.search.skills.product_search import ProductSearchSkill
from shared.backend_client import BackendClient


def build_search_agent(backend_client: BackendClient) -> BaseAgent:
    agent = BaseAgent(
        name="Search Agent",
        description=(
            "Searches the fashion product catalog using semantic vector search. "
            "Finds products matching user queries by style, color, category, or description."
        ),
    )
    agent.register_skill(ProductSearchSkill(backend_client))
    return agent
