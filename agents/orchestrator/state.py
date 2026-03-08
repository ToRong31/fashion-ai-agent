from typing import Any, TypedDict


class MasterState(TypedDict, total=False):
    raw_user_input: str
    user_id: str
    context_to_send: dict[str, Any]
    next_node: str
    final_response: str
    agent_used: str
    error: str | None
    conversation_history: list[dict]
