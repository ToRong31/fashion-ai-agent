"""
SkillBasedExecutor — generic A2A executor following the official A2A SDK pattern.

Follows the CurrencyAgentExecutor sample:
  - Uses context.get_user_input(), context.current_task
  - Uses TaskUpdater for status updates and artifacts
  - Uses new_task, new_agent_text_message
  - Uses TaskState for state management
  - Routes LLM tool calls to the appropriate Skill
"""
import json

import structlog
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    Part,
    TaskState,
    TextPart,
    DataPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError
from openai import AsyncOpenAI

from agents.base.agent import BaseAgent

logger = structlog.get_logger()


class SkillBasedExecutor(AgentExecutor):
    """Generic executor that delegates tool calls to the appropriate skill."""

    def __init__(self, agent: BaseAgent, openai_client: AsyncOpenAI, model: str):
        self._agent = agent
        self._openai = openai_client
        self._model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        logger.info("executing", agent=self._agent.name, query=query[:100] if query else "")

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    "Processing your request...",
                    task.context_id,
                    task.id,
                ),
            )

            final_text, collected_data = await self._tool_calling_loop(query)

            parts: list[Part] = [Part(root=TextPart(text=final_text))]
            if collected_data:
                parts.append(Part(root=DataPart(data=collected_data)))

            await updater.add_artifact(parts)
            await updater.complete()

        except ServerError:
            raise
        except Exception as e:
            logger.error("execution_failed", agent=self._agent.name, error=str(e))
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())

    async def _tool_calling_loop(self, user_text: str) -> tuple[str, dict]:
        """Run the LLM <-> tool loop. Returns (final_text, collected_data)."""
        messages: list = [
            {"role": "system", "content": self._agent.build_system_prompt()},
            {"role": "user", "content": user_text},
        ]
        tools = self._agent.get_all_openai_tools()
        collected_data: dict = {}
        tool_was_called = False

        for iteration in range(8):
            response = await self._openai.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            choice = response.choices[0]
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                if iteration == 0 and not tool_was_called:
                    logger.warning("llm_skipped_tools", agent=self._agent.name)
                    fallback = await self._direct_fallback(user_text, collected_data)
                    if fallback:
                        return fallback, collected_data
                break

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": "Error parsing arguments."}
                        )
                        continue

                    tool_was_called = True
                    skill = self._agent.find_skill_for_tool(fn_name)
                    if not skill:
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": f"Unknown tool: {fn_name}"}
                        )
                        continue

                    result = await skill.execute_tool(fn_name, args)
                    logger.info("tool_executed", tool=fn_name, skill=skill.id)

                    if result.data:
                        collected_data.update(result.data)

                    content = (
                        json.dumps(result.content, ensure_ascii=False)
                        if not isinstance(result.content, str)
                        else result.content
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            else:
                break

        return self._extract_final_text(messages), collected_data

    async def _direct_fallback(self, user_text: str, collected_data: dict) -> str | None:
        """Fallback: execute the first skill's first tool directly with user text."""
        for skill in self._agent.skills:
            tool_defs = skill.get_tools()
            if not tool_defs:
                continue
            try:
                result = await skill.execute_tool(tool_defs[0].name, {"query": user_text})
                if result.data:
                    collected_data.update(result.data)
                if isinstance(result.content, str):
                    return result.content
                return json.dumps(result.content, ensure_ascii=False)
            except Exception as e:
                logger.warning("fallback_failed", skill=skill.id, error=str(e))
        return None

    @staticmethod
    def _extract_final_text(messages: list) -> str:
        for m in reversed(messages):
            if hasattr(m, "role") and m.role == "assistant" and m.content:
                return m.content
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return "Task completed."
