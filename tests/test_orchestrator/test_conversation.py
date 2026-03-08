from agents.orchestrator.conversation import ConversationManager


def test_add_and_get_messages():
    mgr = ConversationManager(max_history=10)
    mgr.add_message("user1", "user", "hello")
    mgr.add_message("user1", "assistant", "hi there")

    history = mgr.get_history("user1")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}


def test_separate_users():
    mgr = ConversationManager()
    mgr.add_message("user1", "user", "msg1")
    mgr.add_message("user2", "user", "msg2")

    assert len(mgr.get_history("user1")) == 1
    assert len(mgr.get_history("user2")) == 1
    assert mgr.get_history("user1")[0]["content"] == "msg1"
    assert mgr.get_history("user2")[0]["content"] == "msg2"


def test_max_history_truncation():
    mgr = ConversationManager(max_history=3)
    for i in range(5):
        mgr.add_message("user1", "user", f"message {i}")

    history = mgr.get_history("user1")
    assert len(history) == 3
    assert history[0]["content"] == "message 2"
    assert history[2]["content"] == "message 4"


def test_clear_history():
    mgr = ConversationManager()
    mgr.add_message("user1", "user", "hello")
    mgr.clear("user1")

    assert len(mgr.get_history("user1")) == 0


def test_get_history_returns_copy():
    mgr = ConversationManager()
    mgr.add_message("user1", "user", "hello")

    history = mgr.get_history("user1")
    history.append({"role": "user", "content": "should not appear"})

    assert len(mgr.get_history("user1")) == 1


def test_empty_history():
    mgr = ConversationManager()
    assert mgr.get_history("nonexistent") == []
