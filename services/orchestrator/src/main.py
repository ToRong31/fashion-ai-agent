import os

import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.models.agent import ChatRequest, ChatResponse
from shared.logging_config import setup_logging
from services.orchestrator.src.conversation import ConversationManager
from services.orchestrator.src.routing_agent import RoutingAgent

logger = structlog.get_logger()

routing_agent: RoutingAgent | None = None
conversation_mgr = ConversationManager(
    max_history=int(os.getenv("ORCHESTRATOR_MAX_CONVERSATION_HISTORY", "20"))
)


def _parse_base_url(card_url: str) -> str:
    if "/.well-known/" in card_url:
        return card_url.rsplit("/.well-known/", 1)[0]
    return card_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    global routing_agent

    agent_card_urls = [
        os.getenv("ORCHESTRATOR_SEARCH_AGENT_CARD_URL", "http://search:8001/.well-known/agent.json"),
        os.getenv("ORCHESTRATOR_STYLIST_AGENT_CARD_URL", "http://stylist:8002/.well-known/agent.json"),
        os.getenv("ORCHESTRATOR_ORDER_AGENT_CARD_URL", "http://order:8003/.well-known/agent.json"),
    ]
    agent_base_urls = [_parse_base_url(u) for u in agent_card_urls]

    routing_agent = await RoutingAgent.create(agent_base_urls)
    logger.info(
        "orchestrator_ready",
        agents=routing_agent.list_remote_agents(),
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
async def chat(request: ChatRequest):
    logger.info("chat_request", user_id=request.user_id, message=request.message[:100])

    conversation_mgr.add_message(request.user_id, "user", request.message)
    history = conversation_mgr.get_history(request.user_id)

    try:
        result = await routing_agent.run(
            user_message=request.message,
            user_id=request.user_id,
            conversation_history=history[:-1],
        )
        conversation_mgr.add_message(request.user_id, "assistant", result["response"])
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
