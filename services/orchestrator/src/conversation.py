from collections import defaultdict


class ConversationManager:
    def __init__(self, max_history: int = 20):
        self._max_history = max_history
        self._histories: dict[str, list[dict]] = defaultdict(list)

    def add_message(self, user_id: str, role: str, content: str) -> None:
        self._histories[user_id].append({"role": role, "content": content})
        if len(self._histories[user_id]) > self._max_history:
            self._histories[user_id] = self._histories[user_id][-self._max_history:]

    def get_history(self, user_id: str) -> list[dict]:
        return list(self._histories.get(user_id, []))

    def clear(self, user_id: str) -> None:
        self._histories.pop(user_id, None)
