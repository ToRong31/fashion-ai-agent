from a2a.types import AgentCard, AgentSkill, AgentCapabilities


def build_order_agent_card(host: str = "http://localhost", port: int = 8003) -> AgentCard:
    return AgentCard(
        name="Order Agent",
        description=(
            "Creates orders and generates payment links for product purchases. "
            "Handles the complete checkout flow from order creation to VNPay integration."
        ),
        url=f"{host}:{port}",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        skills=[
            AgentSkill(
                id="create-order",
                name="Create Order",
                description="Create an order and generate a payment link for selected products",
                tags=["order", "buy", "purchase", "payment", "checkout"],
                examples=[
                    "I want to buy this jacket",
                    "Purchase product 1 and product 3",
                    "Buy the black blazer",
                ],
            ),
        ],
        defaultInputModes=["text/plain", "application/json"],
        defaultOutputModes=["application/json"],
    )
