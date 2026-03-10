from a2a.types import AgentCard, AgentSkill, AgentCapabilities


def build_search_agent_card(host: str = "http://localhost", port: int = 8001) -> AgentCard:
    return AgentCard(
        name="Search Agent",
        description=(
            "Searches the fashion product catalog using semantic vector search. "
            "Finds products matching user queries by style, color, category, or description."
        ),
        url=f"{host}:{port}",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        skills=[
            AgentSkill(
                id="product-search",
                name="Product Search",
                description="Search for fashion products by natural language query",
                tags=["search", "products", "fashion", "catalog"],
                examples=[
                    "Find me a black jacket",
                    "Show me casual summer dresses",
                    "I need formal shoes",
                ],
            ),
        ],
        defaultInputModes=["text/plain", "application/json"],
        defaultOutputModes=["application/json"],
    )
