"""
Routing agent — orchestrates worker agents using OpenAI tool-calling.

Pattern adapted from the A2A multi-agent sample (host_agent/routing_agent.py):
  - LLM decides which remote agent to call via `send_message` tool
  - Tool result goes back to LLM for processing & presentation
  - Keyword-based fallback when model doesn't support tool calling
"""
import json
import uuid
from pathlib import Path

import httpx
import structlog
import yaml
from openai import AsyncOpenAI

from a2a.client import A2ACardResolver
from a2a.types import (
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Message,
    Task,
)

from shared.config import LLMSettings
from services.orchestrator.remote_agent_connection import RemoteAgentConnections

logger = structlog.get_logger()


def _load_routing_prompt() -> dict:
    yaml_path = Path(__file__).parent / "skills" / "prompts" / "routing.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class RoutingAgent:
    """Discovers remote A2A worker agents and routes user requests via LLM tool-calling."""

    def __init__(self):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, object] = {}
        self._agents_roster: str = ""
        self._openai: AsyncOpenAI | None = None
        self._model: str = ""

    # ------------------------------------------------------------------
    # Factory (mirrors sample's RoutingAgent.create)
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls, remote_agent_addresses: list[str]) -> "RoutingAgent":
        instance = cls()
        await instance._async_init_components(remote_agent_addresses)
        return instance

    async def _async_init_components(self, remote_agent_addresses: list[str]) -> None:
        llm_settings = LLMSettings()
        self._openai = AsyncOpenAI(
            api_key=llm_settings.openai_api_key,
            base_url=llm_settings.openai_base_url or None,
        )
        self._model = llm_settings.openai_model

        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()
                    connection = RemoteAgentConnections(agent_card=card, agent_url=address)
                    self.remote_agent_connections[card.name] = connection
                    self.cards[card.name] = card
                    logger.info("agent_discovered", name=card.name, url=address)
                except httpx.ConnectError as e:
                    logger.error("agent_connect_failed", url=address, error=str(e))
                except Exception as e:
                    logger.error("agent_init_failed", url=address, error=str(e))

        # Build roster string from agent skills — LLM sees exactly what
        # each agent can do so it picks the right one.
        agent_info = []
        for card in self.cards.values():
            skills_desc = []
            all_tags: list[str] = []
            all_examples: list[str] = []
            for skill in (card.skills or []):
                skills_desc.append(f"  - {skill.name}: {skill.description}")
                all_tags.extend(skill.tags or [])
                all_examples.extend(skill.examples or [])
            entry = {
                "name": card.name,
                "description": card.description,
                "skills": [
                    {"id": s.id, "name": s.name, "description": s.description,
                     "tags": s.tags or [], "examples": s.examples or []}
                    for s in (card.skills or [])
                ],
            }
            agent_info.append(json.dumps(entry, ensure_ascii=False))
        self._agents_roster = "\n".join(agent_info)
        logger.info("routing_agent_ready", agents=list(self.remote_agent_connections.keys()))

    # ------------------------------------------------------------------
    # Public helpers (mirrors sample's list_remote_agents)
    # ------------------------------------------------------------------

    def list_remote_agents(self) -> list[dict]:
        return [
            {"name": card.name, "description": card.description}
            for card in self.cards.values()
        ]

    # ------------------------------------------------------------------
    # System prompt (mirrors sample's root_instruction)
    # ------------------------------------------------------------------

    def root_instruction(self, user_id: str | None = None) -> str:
        available_names = list(self.remote_agent_connections.keys())
        user_ctx = f"Current user_id: {user_id}." if user_id else ""
        prompt_cfg = _load_routing_prompt()
        prompt_tpl = prompt_cfg["prompt"]
        return prompt_tpl.format(
            user_ctx=user_ctx,
            agents_roster=self._agents_roster,
            available_names=available_names,
        )

    # ------------------------------------------------------------------
    # send_message — mirrors sample's send_message tool
    # Sends task to remote agent via A2A, returns text response.
    # ------------------------------------------------------------------

    async def send_message(self, agent_name: str, task: str) -> dict:
        """Send a task to a named remote agent via A2A protocol.

        Args:
            agent_name: Exact name of the agent (must match agent card name).
            task: Full task description with all necessary context.

        Returns:
            Dict with 'text' and optional 'data' from the remote agent.
        """
        if agent_name not in self.remote_agent_connections:
            available = list(self.remote_agent_connections.keys())
            raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

        # Include JWT token in task for authenticated backend calls
        token_context = ""
        if hasattr(self, "_current_token") and self._current_token:
            token_context = f"\n\n[SYSTEM: JWT_TOKEN={self._current_token}]"

        client = self.remote_agent_connections[agent_name]
        message_id = uuid.uuid4().hex

        payload: dict = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task + token_context}],
                "messageId": message_id,
            }
        }

        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams.model_validate(payload),
        )

        logger.info("routing_to_agent", agent=agent_name, task_preview=task[:100])
        response: SendMessageResponse = await client.send_message(request)
        logger.info("send_response_type", type=type(response.root).__name__)

        if not isinstance(response.root, SendMessageSuccessResponse):
            # Log full error content for debugging
            error_detail = response.root.model_dump_json(exclude_none=True) if hasattr(response.root, "model_dump_json") else str(response.root)
            logger.error("agent_error_response", agent=agent_name, detail=error_detail[:500])
            raise RuntimeError(f"Agent '{agent_name}' returned a non-success response: {error_detail[:200]}")

        result = response.root.result
        logger.info("a2a_result_type", result_type=type(result).__name__)
        if isinstance(result, Task):
            has_status_msg = bool(result.status and result.status.message)
            has_artifacts = bool(result.artifacts)
            if has_status_msg:
                part_types = [type(p.root).__name__ if hasattr(p, "root") else type(p).__name__ for p in result.status.message.parts]
                logger.info("a2a_task_parts", location="status.message", part_types=part_types)
            if has_artifacts:
                for i, a in enumerate(result.artifacts):
                    pt = [type(p.root).__name__ if hasattr(p, "root") else type(p).__name__ for p in a.parts]
                    logger.info("a2a_task_parts", location=f"artifacts[{i}]", part_types=pt)
        elif isinstance(result, Message):
            part_types = [type(p.root).__name__ if hasattr(p, "root") else type(p).__name__ for p in result.parts]
            logger.info("a2a_message_parts", part_types=part_types)

        text = self._extract_text_from_result(result)
        data = self._extract_data_from_result(result)
        logger.info("agent_response_received", agent=agent_name, length=len(text), has_data=data is not None, preview=text[:200])
        return {"text": text, "data": data}

    @staticmethod
    def _extract_data_from_result(result) -> dict | None:
        """Extract DataPart data from A2A Message or Task response."""
        def _parts_data(parts) -> dict | None:
            for part in parts:
                pv = part.root if hasattr(part, "root") else part
                if hasattr(pv, "data") and isinstance(pv.data, dict):
                    return pv.data
            return None

        if isinstance(result, Message):
            return _parts_data(result.parts)
        if isinstance(result, Task):
            if result.status and result.status.message:
                return _parts_data(result.status.message.parts)
            if result.artifacts:
                for a in result.artifacts:
                    d = _parts_data(a.parts)
                    if d:
                        return d
        return None

    @staticmethod
    def _extract_text_from_result(result) -> str:
        """Extract text from A2A Message or Task response."""

        def _parts_text(parts) -> str:
            texts = []
            for part in parts:
                pv = part.root if hasattr(part, "root") else part
                if hasattr(pv, "text") and pv.text:
                    texts.append(pv.text)
            return "\n".join(texts)

        if isinstance(result, Message):
            return _parts_text(result.parts)
        if isinstance(result, Task):
            if result.status and result.status.message:
                return _parts_text(result.status.message.parts)
            if result.artifacts:
                return "\n".join(_parts_text(a.parts) for a in result.artifacts)
        return "Agent completed the task."

    # ------------------------------------------------------------------
    # Main entry — OpenAI tool-calling loop (equivalent to ADK Runner)
    #
    # Like the sample's ADK Runner:
    #   1. LLM receives system prompt + history + user message + tools
    #   2. LLM calls send_message → we forward to remote agent
    #   3. Tool result goes back to LLM → LLM produces final response
    #   4. Falls back to keyword routing if LLM can't do tool calling
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        user_id: str | None,
        conversation_history: list[dict],
        token: str | None = None,
    ) -> dict:
        # Store token for passing to remote agents
        self._current_token = token
        available_names = list(self.remote_agent_connections.keys())
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_message",
                    "description": (
                        "Send a task to a specialized remote agent and get the result. "
                        f"Available agents: {available_names}"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_name": {
                                "type": "string",
                                "description": f"Exact agent name. One of: {available_names}",
                            },
                            "task": {
                                "type": "string",
                                "description": "Full task description with all context for the agent.",
                            },
                        },
                        "required": ["agent_name", "task"],
                    },
                },
            }
        ]

        messages: list = [{"role": "system", "content": self.root_instruction(user_id)}]
        messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": user_message})

        agent_used: str | None = None
        agent_data: dict | None = None

        for iteration in range(6):
            try:
                response = await self._openai.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.error("llm_call_failed", error=str(e), iteration=iteration)
                return await self._keyword_fallback(user_message, user_id)

            choice = response.choices[0]
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                if iteration == 0 and agent_used is None:
                    # LLM answered without calling tool → fall back to keyword routing
                    logger.warning("llm_skipped_tool_call", message=user_message[:100])
                    return await self._keyword_fallback(user_message, user_id)
                break

            elif choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tool_call in choice.message.tool_calls:
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        logger.error("tool_args_parse_failed", raw=tool_call.function.arguments[:200], error=str(e))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Error parsing arguments."})
                        continue

                    agent_name: str = args["agent_name"]
                    task_text: str = args["task"]
                    if user_id:
                        task_text = f"{task_text} [user_id={user_id}]"

                    try:
                        send_result = await self.send_message(agent_name, task_text)
                        agent_used = agent_name
                        result_text = send_result["text"]
                        if send_result.get("data"):
                            agent_data = send_result["data"]
                    except Exception as e:
                        logger.error("send_message_failed", agent=agent_name, error=str(e))
                        result_text = f"Error forwarding to {agent_name}: {str(e)}"

                    # Feed result back to LLM (like ADK does — LLM processes & presents)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result_text})
                # Loop continues — LLM will process the tool result

            else:
                break

        final_text = self._extract_final_text(messages)
        return {"response": final_text, "agent_used": agent_used, "data": agent_data}

    # ------------------------------------------------------------------
    # Keyword fallback (for models without tool-calling support)
    # ------------------------------------------------------------------

    async def _keyword_fallback(self, user_message: str, user_id: str | None) -> dict:
        """Fallback: match user message against agent skills tags."""
        lower = user_message.lower()
        best_agent: str | None = None
        best_score = 0

        for card in self.cards.values():
            score = 0
            for skill in (card.skills or []):
                for tag in (skill.tags or []):
                    if tag.lower() in lower:
                        score += 2
                for example in (skill.examples or []):
                    # Check if any significant words from example appear in user message
                    example_words = {w for w in example.lower().split() if len(w) > 3}
                    score += len(example_words & set(lower.split()))
            if score > best_score:
                best_score = score
                best_agent = card.name

        # Default to first agent if no match
        if not best_agent:
            best_agent = next(iter(self.remote_agent_connections), None)
            if best_agent is None:
                return {"response": "No agents available.", "agent_used": None}

        task = user_message
        if user_id:
            task = f"{task} [user_id={user_id}]"

        logger.info("skill_based_fallback_routing", agent=best_agent, score=best_score)
        try:
            send_result = await self.send_message(best_agent, task)
        except Exception as e:
            logger.error("keyword_fallback_failed", agent=best_agent, error=str(e))
            return {"response": f"Unable to process request: {str(e)}", "agent_used": best_agent}

        return {
            "response": send_result["text"],
            "agent_used": best_agent,
            "data": send_result.get("data"),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_final_text(messages: list) -> str:
        for m in reversed(messages):
            if hasattr(m, "role") and m.role == "assistant" and m.content:
                return m.content
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return "Unable to process request."
