from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str | None = None
    token: str | None = None  # JWT token for authenticated backend calls


class ChatResponse(BaseModel):
    response: str
    agent_used: str | None = None
    data: dict | None = None
