"""
Search Agent Executor — runs an OpenAI-based agent with search_products tool.

Pattern follows the A2A sample: LLM + domain tools.
LLM decides when to call search_products and formats the results.
Falls back to direct tool call if LLM doesn't invoke the tool.
"""
import json
import uuid

import structlog
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Message, TextPart, DataPart
from openai import AsyncOpenAI

from agents.search.tools import SearchTools

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a product search assistant for ToRoMe Store, a fashion clothing store.
When a user asks to find or browse products, use the search_products tool immediately.
ALWAYS call search_products — never answer from your own knowledge about products.
Do NOT format the results yourself — just call the tool and return."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search for clothing products in the ToRoMe Store catalog. "
                "Supports queries by product type, color, style, occasion, season, gender, or material."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'black dress for party', 'winter jacket men', 'casual sneakers'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5, max 20)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    }
]


class SearchAgentExecutor(AgentExecutor):
    def __init__(self, tools: SearchTools, openai_client: AsyncOpenAI, model: str):
        self._tools = tools
        self._openai = openai_client
        self._model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_text = self._extract_text(context.message)
        logger.info("search_agent_executing", query=user_text)

        try:
            # Primary path: LLM tool-calling loop
            _, products = await self._llm_tool_loop(user_text)
        except Exception as e:
            logger.warning("llm_tool_loop_failed", error=str(e))
            # Fallback: direct search
            products = await self._tools.search_products(query=user_text, top_k=10)
            logger.info("direct_search_fallback", count=len(products))

        # Always format results ourselves — never let LLM hallucinate/reformat
        result_text = self._format_products_table(products)

        await event_queue.enqueue_event(
            Message(
                role="agent",
                messageId=str(uuid.uuid4()),
                parts=[
                    TextPart(text=result_text),
                    DataPart(data={"products": products}),
                ],
            )
        )

    async def _llm_tool_loop(self, user_text: str) -> tuple[str, list[dict]]:
        """Run LLM with search_products tool. LLM calls tool and formats results."""
        messages: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        products_found: list[dict] = []

        for iteration in range(5):
            response = await self._openai.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            choice = response.choices[0]
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                # If LLM answered without calling tool on first iteration, fallback
                if iteration == 0 and not products_found:
                    logger.warning("search_llm_skipped_tool")
                    raise RuntimeError("LLM did not call search_products tool")
                break

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tool_call in choice.message.tool_calls:
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Error parsing arguments.",
                        })
                        continue

                    result = await self._tools.search_products(
                        query=args.get("query", user_text),
                        top_k=args.get("top_k", 5),
                    )
                    products_found = result
                    logger.info("tool_search_products", count=len(result))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

        final_text = self._extract_final_text(messages)
        return final_text, products_found

    @staticmethod
    def _format_products_table(products: list[dict]) -> str:
        """Format products as a markdown table — consistent, parseable by frontend."""
        if not products:
            return "No products found. Try different keywords!"

        lines = [
            "**Search Results**",
            "",
            "| # | Product Name | Price | Description |",
            "|---|------------|-------|-------------|",
        ]
        for p in products:
            pid = p.get("id", "?")
            name = p.get("name", "Unknown")
            price = f"${p.get('price', 0)}"
            desc = (p.get("description", "") or "")[:80]
            lines.append(f"| {pid} | {name} | {price} | {desc} |")

        return "\n".join(lines)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        pass

    def _extract_text(self, message: Message | None) -> str:
        if not message:
            return ""
        for part in message.parts:
            pv = part.root if hasattr(part, "root") else part
            if hasattr(pv, "text") and pv.text:
                return pv.text
            if hasattr(pv, "data") and isinstance(pv.data, dict):
                return pv.data.get("query", "")
        return ""

    @staticmethod
    def _extract_final_text(messages: list) -> str:
        for m in reversed(messages):
            if hasattr(m, "role") and m.role == "assistant" and m.content:
                return m.content
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return "Search complete."

