import os

import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from shared.config import LLMSettings
from shared.models.agent import ChatRequest, ChatResponse
from shared.logging_config import setup_logging
from services.orchestrator.conversation import ConversationManager, EnhancedConversationManager, MessageRole
from services.orchestrator.routing_agent import RoutingAgent
from services.orchestrator.planning_agent import PlanningAgent, ExecutionMode
from services.orchestrator.plan_executor import PlanExecutor
from services.orchestrator.workflow_state import WorkflowStateManager

logger = structlog.get_logger()

routing_agent: RoutingAgent | None = None
planning_agent: PlanningAgent | None = None
plan_executor: PlanExecutor | None = None
conversation_mgr = ConversationManager(
    max_history=int(os.getenv("ORCHESTRATOR_MAX_CONVERSATION_HISTORY", "20"))
)
enhanced_conversation_mgr = EnhancedConversationManager(
    max_history=int(os.getenv("ORCHESTRATOR_MAX_CONVERSATION_HISTORY", "20"))
)
workflow_mgr = WorkflowStateManager(
    timeout_seconds=int(os.getenv("ORCHESTRATOR_WORKFLOW_TIMEOUT_SECONDS", "300"))
)

# Enable multi-agent planning (can be disabled via env var)
ENABLE_MULTI_AGENT = os.getenv("ORCHESTRATOR_ENABLE_MULTI_AGENT", "true").lower() == "true"
# Enable context-aware planning (can be disabled via env var)
ENABLE_CONTEXT_AWARE = os.getenv("ORCHESTRATOR_ENABLE_CONTEXT_AWARE", "true").lower() == "true"


def _parse_base_url(card_url: str) -> str:
    if "/.well-known/" in card_url:
        return card_url.rsplit("/.well-known/", 1)[0]
    return card_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    global routing_agent, planning_agent, plan_executor

    agent_card_urls = [
        os.getenv("ORCHESTRATOR_SEARCH_AGENT_CARD_URL", "http://search:8001/.well-known/agent.json"),
        os.getenv("ORCHESTRATOR_STYLIST_AGENT_CARD_URL", "http://stylist:8002/.well-known/agent.json"),
        os.getenv("ORCHESTRATOR_ORDER_AGENT_CARD_URL", "http://order:8003/.well-known/agent.json"),
    ]
    agent_base_urls = [_parse_base_url(u) for u in agent_card_urls]

    routing_agent = await RoutingAgent.create(agent_base_urls)

    # Initialize planning agent and executor for multi-agent workflows
    if ENABLE_MULTI_AGENT:
        llm_settings = LLMSettings()
        openai_client = AsyncOpenAI(
            api_key=llm_settings.openai_api_key,
            base_url=llm_settings.openai_base_url or None,
        )
        planning_agent = PlanningAgent(openai_client=openai_client, model=llm_settings.openai_model)
        plan_executor = PlanExecutor(routing_agent.remote_agent_connections)
        logger.info(
            "multi_agent_planning_enabled",
            agents=routing_agent.list_remote_agents(),
        )

    logger.info(
        "orchestrator_ready",
        agents=routing_agent.list_remote_agents(),
        multi_agent_enabled=ENABLE_MULTI_AGENT,
        port=int(os.getenv("ORCHESTRATOR_PORT", "8000")),
    )
    yield
    logger.info("orchestrator_shutting_down")


app = FastAPI(
    title="ToRoMe AI Orchestrator",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(None),
):
    # Extract JWT token from Authorization header
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    logger.info("chat_request", user_id=request.user_id, message=request.message[:100], has_token=bool(token))

    # Add to both conversation managers for compatibility
    conversation_mgr.add_message(request.user_id, "user", request.message)
    history = conversation_mgr.get_history(request.user_id)

    # Get workflow state for context-aware planning
    workflow_state = None
    if ENABLE_CONTEXT_AWARE:
        workflow_state = workflow_mgr.get_or_create(request.user_id, request.message)

    try:
        # Check if multi-agent planning is enabled and can handle this request
        if ENABLE_MULTI_AGENT and planning_agent and plan_executor:
            # Get conversation history for context-aware planning
            conv_history = []
            if ENABLE_CONTEXT_AWARE:
                conv_history = enhanced_conversation_mgr.get_history(request.user_id)

            # Create execution plan with full context
            context = {"user_id": request.user_id, "token": token}
            plan = await planning_agent.create_plan(
                request.message,
                context,
                conversation_history=conv_history,
                workflow_state=workflow_state,
            )
            logger.info(
                "execution_plan_created",
                mode=plan.mode.value,
                steps=len(plan.steps),
                user_id=request.user_id,
            )

            # Execute the plan
            if plan.mode == ExecutionMode.SINGLE:
                # For single mode, use the existing routing agent for consistency
                result = await routing_agent.run(
                    user_message=request.message,
                    user_id=request.user_id,
                    conversation_history=history[:-1],
                    token=token,
                )
            else:
                # Multi-agent execution
                execution_result = await plan_executor.execute(plan, context)
                result = {
                    "response": execution_result["text"],
                    "agent_used": ", ".join(execution_result.get("agents_used", [])),
                    "data": execution_result.get("data"),
                }
        else:
            # Fall back to original routing behavior
            result = await routing_agent.run(
                user_message=request.message,
                user_id=request.user_id,
                conversation_history=history[:-1],
                token=token,
            )

        # Extract products from result for conversation tracking
        products = None
        if result.get("data") and "products" in result["data"]:
            products = result["data"]["products"]

        # Update conversation and workflow state
        conversation_mgr.add_message(request.user_id, "assistant", result["response"])

        if ENABLE_CONTEXT_AWARE:
            # Update enhanced conversation with structured data
            enhanced_conversation_mgr.add_message(
                request.user_id,
                MessageRole.USER,
                request.message,
            )
            enhanced_conversation_mgr.add_message(
                request.user_id,
                MessageRole.ASSISTANT,
                result["response"],
                products=products,
                agent_used=result.get("agent_used", ""),
            )

            # Update workflow state with search results
            if products:
                workflow_mgr.update_search_results(request.user_id, products)
                logger.info("workflow_state_updated", user_id=request.user_id, products_count=len(products))

        return ChatResponse(
            response=result["response"],
            agent_used=result.get("agent_used"),
            data=result.get("data"),
        )
    except Exception as e:
        logger.error("chat_failed", error=str(e), user_id=request.user_id)
        raise HTTPException(status_code=500, detail="Internal AI error")


@app.get("/health")
async def health():
    agents = routing_agent.list_remote_agents() if routing_agent else []
    return {"status": "ok", "service": "orchestrator", "agents": agents}


@app.get("/conversation/{user_id}")
async def get_conversation(user_id: str):
    return {"history": conversation_mgr.get_history(user_id)}


if __name__ == "__main__":
    setup_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        service_name="orchestrator",
    )
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
