from a2a.types import AgentCard, AgentSkill, AgentCapabilities


def build_stylist_agent_card(host: str = "http://localhost", port: int = 8002) -> AgentCard:
    return AgentCard(
        name="Stylist Agent",
        description=(
            "AI fashion stylist that creates coordinated outfit recommendations "
            "based on user preferences, occasion, and season."
        ),
        url=f"{host}:{port}",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        skills=[
            AgentSkill(
                id="outfit-recommendation",
                name="Outfit Recommendation",
                description="Recommend coordinated outfit combinations based on user needs",
                tags=["stylist", "outfit", "fashion-advice", "recommendation"],
                examples=[
                    "Style me an outfit for a winter meeting",
                    "What should I wear for a casual date?",
                    "Recommend a formal look for an interview",
                ],
            ),
        ],
        defaultInputModes=["text/plain", "application/json"],
        defaultOutputModes=["application/json"],
    )
