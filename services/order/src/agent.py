"""Order Agent — shopping cart, order creation, and payment."""
from shared.base.agent import BaseAgent
from order.src.skills.order_processing import OrderProcessingSkill
from shared.backend_client import BackendClient


def build_order_agent(backend_client: BackendClient) -> BaseAgent:
    agent = BaseAgent(
        name="Order Agent",
        description=(
            "Creates orders and generates payment links for product purchases. "
            "Handles cart management and the complete checkout flow from order creation "
            "to VNPay integration."
        ),
    )
    agent.register_skill(OrderProcessingSkill(backend_client))
    return agent
