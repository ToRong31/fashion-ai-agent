from services.orchestrator.state import MasterState


def test_master_state_creation():
    state: MasterState = {
        "raw_user_input": "find me a jacket",
        "user_id": "1",
        "context_to_send": {"query": "find me a jacket"},
        "next_node": "search_node",
        "final_response": "",
        "agent_used": "search",
        "error": None,
        "conversation_history": [],
    }
    assert state["raw_user_input"] == "find me a jacket"
    assert state["next_node"] == "search_node"


def test_master_state_partial():
    state: MasterState = {
        "raw_user_input": "hello",
        "user_id": "1",
    }
    assert state["raw_user_input"] == "hello"
    assert "final_response" not in state
