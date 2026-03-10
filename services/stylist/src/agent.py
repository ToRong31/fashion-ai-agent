"""Stylist Agent — AI fashion stylist for outfit recommendations."""
from shared.base.agent import BaseAgent
from stylist.src.skills.outfit_recommendation import OutfitRecommendationSkill
from shared.backend_client import BackendClient


def build_stylist_agent(backend_client: BackendClient) -> BaseAgent:
    agent = BaseAgent(
        name="Stylist Agent",
        description=(
            "AI fashion stylist that creates coordinated outfit recommendations "
            "based on user preferences, occasion, and season."
        ),
    )
    agent.register_skill(OutfitRecommendationSkill(backend_client))
    return agent
