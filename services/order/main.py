import logging
import os
import sys

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from openai import AsyncOpenAI

from shared.config import BackendSettings, LLMSettings
from shared.backend_client import BackendClient
from shared.logging_config import setup_logging
from shared.base_agent.executor import SkillBasedExecutor
from services.order.agent import build_order_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    port = int(os.getenv("ORDER_AGENT_PORT", "8003"))
    host = os.getenv("ORDER_AGENT_HOST", "http://localhost")

    setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"), service_name="order-agent")

    try:
        llm = LLMSettings()
        backend_client = BackendClient(BackendSettings())
        openai_client = AsyncOpenAI(api_key=llm.openai_api_key, base_url=llm.openai_base_url)

        agent = build_order_agent(backend_client)
        executor = SkillBasedExecutor(agent, openai_client, model=llm.openai_model)

        agent_card = agent.build_agent_card(host=host, port=port)
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        uvicorn.run(server.build(), host="0.0.0.0", port=port)

    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
