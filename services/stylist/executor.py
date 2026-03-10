import json
import uuid

import structlog
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Message, TextPart, DataPart
from openai import AsyncOpenAI

from agents.stylist.tools import StylistTools

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a professional fashion stylist for ToRoMe Store.
Help users build coordinated outfits from our product catalog.

You have access to these tools:
- search_products: Find specific items (e.g. "black blazer formal", "white sneakers casual")
- get_product_catalog: Fetch the full product catalog when you need a wide selection
- get_user_preferences: Fetch a user's stored style preferences (size, color, style)

Steps to follow:
1. Optionally fetch user preferences if a user_id is known
2. Search for relevant products matching the user's request (occasion, style, season, gender)
3. Recommend a complete, coordinated outfit using ONLY products from the catalog
4. Return a JSON object in this exact structure:
{
  "outfit_name": "Name of the outfit",
  "occasion": "What occasion this outfit is for",
  "items": [
    {"product_id": 1, "name": "Product name", "price": 89.99, "role": "What role this plays in the outfit"}
  ],
  "reasoning": "Brief explanation of why these items work together",
  "styling_tips": "Any additional styling advice"
}

Use real product IDs from the search results. Always recommend a complete outfit (top + bottom + shoes at minimum)."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for clothing products matching a specific description, style, occasion, or category",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'formal blazer', 'summer dress', 'casual sneakers men'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max results to return (default 8)",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_catalog",
            "description": "Fetch the complete product catalog — use when you need a broad selection of all available items",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_preferences",
            "description": "Fetch a user's stored style preferences (preferred size, color, style) to personalise the outfit",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "The user's ID",
                    }
                },
                "required": ["user_id"],
            },
        },
    },
]


class StylistAgentExecutor(AgentExecutor):
    def __init__(self, tools: StylistTools, openai_client: AsyncOpenAI, model: str):
        self._tools = tools
        self._openai = openai_client
        self._model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_text, user_id = self._extract_params(context.message)
        logger.info("stylist_agent_executing", query=user_text, user_id=user_id)

        context_note = f" [user_id={user_id}]" if user_id else ""
        messages: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text + context_note},
        ]

        outfit: dict = {}

        try:
            tool_was_called = False
            for iteration in range(8):  # max tool-call iterations
                response = await self._openai.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                choice = response.choices[0]
                messages.append(choice.message)

                if choice.finish_reason == "stop":
                    # If LLM answered without calling any tool, do direct search
                    if iteration == 0 and not tool_was_called:
                        logger.warning("stylist_llm_skipped_tools, running direct search")
                        result = await self._tools.search_products(query=user_text, top_k=10)
                        final_text = f"Here are products matching your request:\n{json.dumps(result, ensure_ascii=False, indent=2)}"
                        messages.append({"role": "assistant", "content": final_text})
                    break

                if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                    for tool_call in choice.message.tool_calls:
                        fn = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Error parsing arguments."})
                            continue
                        tool_was_called = True

                        if fn == "search_products":
                            result = await self._tools.search_products(
                                query=args["query"],
                                top_k=args.get("top_k", 8),
                            )
                            logger.info("tool_search_products", count=len(result))
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

                        elif fn == "get_product_catalog":
                            result = await self._tools.get_product_catalog()
                            logger.info("tool_get_catalog", count=len(result))
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

                        elif fn == "get_user_preferences":
                            result = await self._tools.get_user_preferences(args["user_id"])
                            logger.info("tool_get_preferences", user_id=args["user_id"])
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

            # Parse outfit JSON from final assistant message
            final_text = self._extract_final_text(messages)
            outfit = self._parse_outfit_json(final_text)

            text_summary = self._format_outfit_text(outfit, final_text)
            await event_queue.enqueue_event(
                Message(
                    role="agent",
                    messageId=str(uuid.uuid4()),
                    parts=[
                        TextPart(text=text_summary),
                        DataPart(data=outfit),
                    ],
                )
            )
        except Exception as e:
            logger.error("stylist_agent_failed", error=str(e))
            await event_queue.enqueue_event(
                Message(
                    role="agent",
                    messageId=str(uuid.uuid4()),
                    parts=[TextPart(text=f"Styling recommendation failed: {str(e)}")],
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        pass

    def _extract_params(self, message: Message | None) -> tuple[str, str | None]:
        query = ""
        user_id = None
        if not message:
            return query, user_id
        for part in message.parts:
            pv = part.root if hasattr(part, "root") else part
            if hasattr(pv, "text") and pv.text:
                query = pv.text
            if hasattr(pv, "data") and isinstance(pv.data, dict):
                query = pv.data.get("query", query)
                user_id = pv.data.get("user_id")
        return query, str(user_id) if user_id else None

    def _extract_final_text(self, messages: list) -> str:
        for m in reversed(messages):
            if hasattr(m, "role") and m.role == "assistant" and m.content:
                return m.content
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return ""

    def _parse_outfit_json(self, text: str) -> dict:
        try:
            raw = text
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            # Find JSON object boundaries
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {}

    def _format_outfit_text(self, outfit: dict, fallback: str) -> str:
        if not outfit:
            return fallback
        parts = [f"Outfit: {outfit.get('outfit_name', 'Custom Outfit')}"]
        parts.append(f"Occasion: {outfit.get('occasion', 'General')}")
        parts.append("")
        for item in outfit.get("items", []):
            parts.append(f"- {item.get('name', '')} (${item.get('price', '')}) — {item.get('role', '')}")
        parts.append("")
        parts.append(f"Why this works: {outfit.get('reasoning', '')}")
        if outfit.get("styling_tips"):
            parts.append(f"Tips: {outfit['styling_tips']}")
        return "\n".join(parts)
