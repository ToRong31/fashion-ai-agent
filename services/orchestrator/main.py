"""
Orchestrator main — skill-based A2A server.

Replaces the manual routing/planning/executing pattern with a skill-based agent.
Uses OrchestrationSkill for multi-agent coordination.
"""
import os

import structlog
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from shared.config import LLMSettings
from shared.base_agent.agent import BaseAgent
from shared.base_agent.executor import SkillBasedExecutor
from shared.base_agent.memory import MemoryStore
from services.orchestrator.schemas import ChatRequest, ChatResponse
from shared.logging_config import setup_logging
from services.orchestrator.conversation import SmartConversationManager, MessageRole
from services.orchestrator.routing_agent import RoutingAgent
from services.orchestrator.planning_agent import PlanningAgent
from services.orchestrator.plan_executor import PlanExecutor
from services.orchestrator.skills import OrchestrationSkill

logger = structlog.get_logger()

# Global instances (initialized in lifespan)
routing_agent: RoutingAgent | None = None
planning_agent: PlanningAgent | None = None
plan_executor: PlanExecutor | None = None
conversation_mgr: SmartConversationManager | None = None
orchestrator_agent: BaseAgent | None = None
skill_executor: SkillBasedExecutor | None = None

# Memory store for orchestrator sessions
_memory_store = MemoryStore()

ENABLE_MULTI_AGENT = os.getenv("ORCHESTRATOR_ENABLE_MULTI_AGENT", "true").lower() == "true"


def _parse_base_url(card_url: str) -> str:
    if "/.well-known/" in card_url:
        return card_url.rsplit("/.well-known/", 1)[0]
    return card_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    global routing_agent, planning_agent, plan_executor, conversation_mgr
    global orchestrator_agent, skill_executor

    agent_card_urls = [
        os.getenv("ORCHESTRATOR_SEARCH_AGENT_CARD_URL", "http://search:8001/.well-known/agent-card.json"),
        os.getenv("ORCHESTRATOR_STYLIST_AGENT_CARD_URL", "http://stylist:8002/.well-known/agent-card.json"),
        os.getenv("ORCHESTRATOR_ORDER_AGENT_CARD_URL", "http://order:8003/.well-known/agent-card.json"),
    ]
    agent_base_urls = [_parse_base_url(u) for u in agent_card_urls]

    # Initialize components
    routing_agent = await RoutingAgent.create(agent_base_urls)
    conversation_mgr = SmartConversationManager()

    # Initialize planning & execution for multi-agent
    if ENABLE_MULTI_AGENT:
        llm_settings = LLMSettings()
        planning_agent = PlanningAgent(openai_client=None, model=llm_settings.openai_model)
        planning_agent._openai = AsyncOpenAI(
            api_key=llm_settings.openai_api_key,
            base_url=llm_settings.openai_base_url or None,
        )
        plan_executor = PlanExecutor(routing_agent.remote_agent_connections)
        logger.info("multi_agent_planning_enabled", agents=routing_agent.list_remote_agents())

    # Build skill-based orchestrator agent
    orchestration_skill = OrchestrationSkill(
        routing_agent=routing_agent,
        planning_agent=planning_agent,
        plan_executor=plan_executor,
        conversation_mgr=conversation_mgr,
    )

    orchestrator_agent = BaseAgent(
        name="Orchestrator",
        description=(
            "Central orchestrator for ToRoMe Store AI assistant. "
            "Analyzes user intent, routes to appropriate agents, and coordinates multi-agent workflows."
        ),
    )
    orchestrator_agent.register_skill(orchestration_skill)

    # Build A2A server for orchestrator
    host = os.getenv("ORCHESTRATOR_HOST", "http://localhost")
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
    agent_card = orchestrator_agent.build_agent_card(host=host, port=port)

    llm_settings = LLMSettings()
    openai_client = AsyncOpenAI(
        api_key=llm_settings.openai_api_key,
        base_url=llm_settings.openai_base_url or None,
    )

    skill_executor = SkillBasedExecutor(
        agent=orchestrator_agent,
        openai_client=openai_client,
        model=llm_settings.openai_model,
        max_memory=10,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=skill_executor,
        task_store=InMemoryTaskStore(),
    )

    app.state.a2a_server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )

    logger.info(
        "orchestrator_ready",
        agents=routing_agent.list_remote_agents(),
        multi_agent_enabled=ENABLE_MULTI_AGENT,
        port=port,
    )
    yield
    logger.info("orchestrator_shutting_down")


app = FastAPI(
    title="ToRoMe AI Orchestrator",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Orchestrator A2A Server"}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    if hasattr(app.state, "a2a_server"):
        return app.state.a2a_server._agent_card
    return {"error": "Not initialized"}


# Legacy REST endpoint (used by gateway)
@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(None),
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    session_id = request.session_id or request.user_id
    memory = _memory_store.get_or_create(session_id, max_history=10)

    if token:
        memory.collected_data["_token"] = token

    logger.info(
        "chat_request",
        user_id=request.user_id,
        session_id=session_id,
        message=request.message[:100],
    )

    # Add to conversation manager
    conversation_mgr.add_message(request.user_id, MessageRole.USER, request.message)
    memory.add_user_message(request.message)

    try:
        # Execute via skill-based executor with memory
        final_text, collected_data = await skill_executor._tool_calling_loop(
            f"{request.message} [user_id={request.user_id}]",
            memory,
        )

        memory.add_assistant_message(final_text)
        memory.update_collected_data(collected_data)

        # Update conversation manager
        products = collected_data.get("products") if collected_data else None
        conversation_mgr.add_message(
            request.user_id,
            MessageRole.ASSISTANT,
            final_text,
            products=products,
            agent_used=collected_data.get("agent_used") if collected_data else None,
        )

        return ChatResponse(
            response=final_text,
            agent_used=collected_data.get("agent_used") if collected_data else None,
            data=collected_data,
        )

    except Exception as e:
        logger.error("chat_failed", error=str(e), user_id=request.user_id)
        raise HTTPException(status_code=500, detail=f"Internal AI error: {str(e)}")


@app.get("/health")
async def health():
    agents = routing_agent.list_remote_agents() if routing_agent else []
    return {"status": "ok", "service": "orchestrator", "agents": agents}


@app.get("/conversation/{user_id}")
async def get_conversation(user_id: str):
    if conversation_mgr:
        history = conversation_mgr.get_history_for_llm(user_id)
        return {"history": history}
    return {"history": []}


@app.delete("/conversation/{user_id}")
async def clear_conversation(user_id: str):
    _memory_store.clear(user_id)
    if conversation_mgr:
        conversation_mgr.clear(user_id)
    return {"status": "cleared", "user_id": user_id}


if __name__ == "__main__":
    setup_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        service_name="orchestrator",
    )
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
