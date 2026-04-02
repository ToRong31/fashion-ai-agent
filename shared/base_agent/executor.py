"""
SkillBasedExecutor — generic A2A executor following the official A2A SDK pattern.

Features:
  - Uses context.get_user_input(), context.current_task
  - Uses TaskUpdater for status updates and artifacts
  - Routes LLM tool calls to the appropriate Skill
  - Self-contained AgentMemory per session
  - ReAct loop with goal tracking and tool call history
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

from shared.base_agent.agent import BaseAgent
from shared.base_agent.memory import MemoryStore, AgentMemory

logger = structlog.get_logger()

# Global memory store (shared across all executors in same process)
_memory_store = MemoryStore()


class SkillBasedExecutor(AgentExecutor):
    """Generic executor that delegates tool calls to the appropriate skill."""

    def __init__(self, agent: BaseAgent, openai_client: AsyncOpenAI, model: str, max_memory: int = 10):
        self._agent = agent
        self._openai = openai_client
        self._model = model
        self._max_memory = max_memory

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        session_id = context.session_id or "default"

        logger.info("executing", agent=self._agent.name, query=query[:100] if query else "", session_id=session_id)

        # Get or create memory for this session
        memory = _memory_store.get_or_create(session_id, max_history=self._max_memory)
        memory.add_user_message(query)

        # Pass user message to skills for JWT token extraction
        for skill in self._agent.skills:
            if hasattr(skill, "set_user_message"):
                skill.set_user_message(query)

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    f"🔄 {self._agent.name} is processing your request...",
                    task.context_id,
                    task.id,
                ),
            )

            final_text, collected_data = await self._tool_calling_loop(query, memory)

            # Store assistant response in memory
            memory.add_assistant_message(final_text)
            memory.update_collected_data(collected_data)

            logger.info(
                "execution_completed",
                agent=self._agent.name,
                session_id=session_id,
                tool_calls=len(memory.tool_calls),
                messages=len(memory.messages),
            )

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

    async def _tool_calling_loop(self, user_text: str, memory: AgentMemory) -> tuple[str, dict]:
        """Run the ReAct loop: Think → Tool Call → Execute → Observe → repeat."""
        # Build messages with system prompt + memory context
        system_prompt = self._agent.build_system_prompt()

        # Inject memory context into system prompt
        if memory.messages:
            memory_context = self._build_memory_context(memory)
            system_prompt += f"\n\n## Conversation History\n{memory_context}"

        messages: list = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        tools = self._agent.get_all_openai_tools()
        tool_was_called = False

        for iteration in range(8):
            logger.info("react_iteration", agent=self._agent.name, iteration=iteration)

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
                    fallback = await self._direct_fallback(user_text, memory)
                    if fallback:
                        return fallback, memory.collected_data
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

                    try:
                        result = await skill.execute_tool(fn_name, args)
                        # Record in memory
                        memory.add_tool_call(fn_name, args, result.content, success=True)
                        if result.data:
                            memory.update_collected_data(result.data)
                    except Exception as e:
                        logger.error("tool_failed", tool=fn_name, error=str(e))
                        memory.add_tool_call(fn_name, args, str(e), success=False)
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {str(e)}"}
                        )
                        continue
                    finally:
                        # Clean up context after skill execution (e.g., JWT tokens)
                        if hasattr(skill, "cleanup"):
                            skill.cleanup()

                    logger.info("tool_executed", tool=fn_name, skill=skill.id)
                    content = (
                        json.dumps(result.content, ensure_ascii=False)
                        if not isinstance(result.content, str)
                        else result.content
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            else:
                break

        return self._extract_final_text(messages), memory.collected_data

    def _build_memory_context(self, memory: AgentMemory) -> str:
        """Build a context string from memory for the system prompt."""
        lines = []
        lines.append("## Previous Conversation:")
        for msg in memory.get_recent_messages(4):
            if msg.role.value == "user":
                lines.append(f"User: {msg.content}")
            elif msg.role.value == "assistant":
                lines.append(f"Assistant: {msg.content}")

        if memory.tool_calls:
            lines.append(f"\n## Tools Already Called ({len(memory.tool_calls)} total):")
            lines.append(memory.get_tool_call_summary())

        if memory.collected_data:
            lines.append(f"\n## Data Collected:")
            lines.append(memory.get_data_summary())

        return "\n".join(lines)

    async def _direct_fallback(self, user_text: str, memory: AgentMemory) -> str | None:
        """Fallback: execute the first skill's first tool directly with user text."""
        for skill in self._agent.skills:
            tool_defs = skill.get_tools()
            if not tool_defs:
                continue
            try:
                result = await skill.execute_tool(tool_defs[0].name, {"query": user_text})
                memory.add_tool_call(tool_defs[0].name, {"query": user_text}, result.content, success=True)
                if result.data:
                    memory.update_collected_data(result.data)
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
