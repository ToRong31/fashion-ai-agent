# Orchestrator Agent

> Central orchestrator that classifies user intent and delegates to specialized agents via A2A protocol

## Purpose

The Orchestrator is the **entry point** for all AI chat requests. It:
1. Receives user messages from the frontend
2. Classifies intent using OrchestrationSkill
3. Routes to the appropriate agent via A2A protocol
4. Returns the agent's response to the user

## Development Context

- **File**: `services/orchestrator/main.py`
- **Port**: 8000
- **Framework**: FastAPI + A2A SDK
- **Pattern**: Skill-based agent with ReAct loop

## Architecture

### Directory Structure

```
services/orchestrator/
├── main.py                     # FastAPI app + A2A server, skill-based entry point
├── schemas.py                  # ChatRequest, ChatResponse
├── conversation.py             # SmartConversationManager (last 3 pairs + summary)
├── routing_agent.py            # A2A client — sends messages to worker agents
├── planning_agent.py           # Creates ExecutionPlan (SINGLE/SEQUENTIAL/PARALLEL)
├── plan_executor.py            # Executes plans via A2A
├── remote_agent_connection.py  # A2A client wrapper
│
├── skills/
│   └── orchestration.py        # OrchestrationSkill (LLM sees this as tools)
│
└── tools/
    ├── route_tool.py           # route_to_agent → single worker agent
    ├── plan_tool.py            # plan_and_execute → multi-agent plan
    └── history_tool.py         # get_conversation_history
```

### Pattern: Skill-based Agent

```
BaseAgent (Orchestrator)
    └── OrchestrationSkill
            ├── route_to_agent          (tools/route_tool.py)
            ├── plan_and_execute       (tools/plan_tool.py)
            └── get_conversation_history (tools/history_tool.py)
```

Every skill follows the same pattern:
- `Skill` class defines metadata + tool definitions + prompt
- `tools/*.py` contains actual implementation
- `SkillBasedExecutor` runs the ReAct loop

## Request Flow

### A2A Path (external callers)

```
POST / → A2A Server
  └─→ SkillBasedExecutor.execute()
       └─→ _tool_calling_loop() [ReAct]
            └─→ OrchestrationSkill.execute_tool()
                 └─→ tools/route_tool.py → routing_agent.run() → A2A → Worker Agent
                      OR
                 └─→ tools/plan_tool.py → planning_agent → plan_executor → A2A → Worker Agents
```

### REST Path (gateway)

```
POST /chat
  └─→ skill_executor._tool_calling_loop()
       └─→ (same as above)
```

## Key Components

### OrchestrationSkill

Coordinates multi-agent workflows.

**Tools:**
- `route_to_agent` — delegate to single worker agent
- `plan_and_execute` — analyze intent + run multi-agent plan
- `get_conversation_history` — retrieve conversation context

### SmartConversationManager

Manages conversation with sliding window (last 3 pairs + summary).

```python
# services/orchestrator/conversation.py
class SmartConversationManager:
    def add_message(user_id, role, content, products=...)
    def get_history(user_id) -> list[Message]
    def get_history_for_llm(user_id) -> list[dict]
```

### AgentMemory

Self-contained memory per session (for worker agents and orchestrator).

```python
# shared/base_agent/memory.py
class AgentMemory:
    messages: list[Message]       # Conversation history
    tool_calls: list[ToolCall]    # Tool execution log
    collected_data: dict          # Intermediate results
```

### RoutingAgent

A2A client — sends messages to worker agents via Google A2A SDK.

```python
# services/orchestrator/routing_agent.py
class RoutingAgent:
    async def run(user_message, user_id, conversation_history) -> dict
    async def send_message(agent_name, task) -> dict
```

### PlanningAgent

Creates execution plans for multi-agent workflows.

```python
# services/orchestrator/planning_agent.py
class ExecutionMode(Enum):
    SINGLE = "single"      # One agent
    SEQUENTIAL = "sequential"  # Chain of agents
    PARALLEL = "parallel"     # Simultaneous agents

class ExecutionPlan:
    mode: ExecutionMode
    steps: list[ExecutionStep]
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | A2A server endpoint |
| GET | `/.well-known/agent-card.json` | Agent card for discovery |
| POST | `/chat` | Process user message (REST, used by gateway) |
| GET | `/health` | Health check + available agents |
| GET | `/conversation/{user_id}` | Get conversation history |
| DELETE | `/conversation/{user_id}` | Clear conversation memory |

### Chat Request/Response

```python
# Request
{
    "user_id": "1",
    "message": "Find me a black jacket",
    "session_id": "optional-session-id"
}

# Response
{
    "response": "Here are some black jackets...",
    "agent_used": "Search Agent",
    "data": { "products": [...] }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_PORT` | 8000 | Service port |
| `ORCHESTRATOR_HOST` | http://localhost | Service host |
| `ORCHESTRATOR_MAX_CONVERSATION_HISTORY` | 20 | Max history size |
| `ORCHESTRATOR_ENABLE_MULTI_AGENT` | true | Enable multi-agent planning |
| `ORCHESTRATOR_SEARCH_AGENT_CARD_URL` | http://search:8001/.well-known/agent-card.json | Agent card URL |
| `ORCHESTRATOR_STYLIST_AGENT_CARD_URL` | http://stylist:8002/.well-known/agent-card.json | Agent card URL |
| `ORCHESTRATOR_ORDER_AGENT_CARD_URL` | http://order:8003/.well-known/agent-card.json | Agent card URL |

## Adding New Tools/Skills

### To add a new tool:

1. Create `tools/new_tool.py`:
```python
from shared.base_agent.skill import ToolDefinition, ToolResult

def get_new_tool_definition() -> ToolDefinition:
    return ToolDefinition(name="new_tool", ...)

async def execute_new_tool(args: dict, ...) -> ToolResult:
    # Implementation
    return ToolResult(content="...", data={...})
```

2. Update `skills/orchestration.py`:
```python
from services.orchestrator.tools.new_tool import get_new_tool_definition, execute_new_tool

def get_tools(self) -> list[ToolDefinition]:
    return [
        get_route_tool_definition(),
        get_plan_tool_definition(),
        get_new_tool_definition(),  # Add here
    ]

async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
    if tool_name == "new_tool":
        return await execute_new_tool(args, ...)
```

## Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test routing (REST)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "Find formal dresses"}'
```
