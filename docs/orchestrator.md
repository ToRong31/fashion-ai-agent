# Orchestrator Agent

> Central routing intelligence that classifies user intent and delegates to specialized agents

## Purpose

The Orchestrator is the **entry point** for all AI chat requests. It:
1. Receives user messages from the frontend
2. Classifies intent (search, stylist, or order)
3. Routes to the appropriate agent via A2A protocol
4. Returns the agent's response to the user

## Development Context

- **File**: `services/orchestrator/main.py`
- **Port**: 8000
- **Framework**: FastAPI
- **Dependencies**: OpenAI (tool-calling), Google A2A SDK

## How It Works

### 1. Startup (Agent Discovery)

```
main.py:29-46 → lifespan()
  └─→ RoutingAgent.create()
       └─→ A2ACardResolver.get_agent_card() for each agent
            └─→ Builds agent roster from discovered skills
```

On startup, the Orchestrator:
1. Reads agent card URLs from environment variables
2. Uses A2A `AgentCardResolver` to discover each agent's capabilities
3. Builds a roster of available agents with their skills

### 2. Request Flow

```
POST /chat → chat()
  │
  ├─→ ConversationManager.add_message()     # Store user message
  ├─→ ConversationManager.get_history()      # Get conversation history
  │
  └─→ RoutingAgent.run()
       │
       ├─→ LLM with tools (primary path)
       │    └─→ send_message() → Remote Agent via A2A
       │
       └─→ Keyword fallback (if LLM fails)
            └─→ classify_intent() in router.py
```

### 3. Intent Classification

The Router uses **two strategies**:

#### Primary: LLM Tool-Calling
- LLM receives system prompt with agent roster
- LLM calls `send_message` tool with agent name + task
- Orchestrator forwards to remote agent via A2A

#### Fallback: Keyword Matching
File: `services/orchestrator/router.py`

```python
_ORDER_KEYWORDS = {"buy", "purchase", "checkout", "order", "add to cart", ...}
_STYLIST_KEYWORDS = {"style", "recommend", "outfit", "wear", ...}
# Default: "search"
```

If LLM doesn't call a tool (or fails), keywords determine routing.

## Key Components

### ConversationManager
Manages conversation history per user for context-aware responses.

```python
# services/orchestrator/conversation.py
class ConversationManager:
    def add_message(user_id, role, content)
    def get_history(user_id) -> list[dict]
```

### RoutingAgent
The core routing engine using OpenAI tool-calling.

```python
# services/orchestrator/routing_agent.py
class RoutingAgent:
    async def run(user_message, user_id, conversation_history) -> dict
    async def send_message(agent_name, task) -> dict
    async def _keyword_fallback(user_message, user_id) -> dict
```

### RemoteAgentConnection
A2A client wrapper for communicating with worker agents.

```python
# services/orchestrator/remote_agent_connection.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Process user message, route to agent |
| GET | `/health` | Health check + available agents |
| GET | `/conversation/{user_id}` | Get conversation history |

### Chat Request/Response

```python
# Request
{
    "user_id": "1",
    "message": "Find me a black jacket"
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
| `ORCHESTRATOR_MAX_CONVERSATION_HISTORY` | 20 | Max history size |
| `ORCHESTRATOR_SEARCH_AGENT_CARD_URL` | http://search:8001/.well-known/agent.json | Agent card URL |
| `ORCHESTRATOR_STYLIST_AGENT_CARD_URL` | http://stylist:8002/.well-known/agent.json | Agent card URL |
| `ORCHESTRATOR_ORDER_AGENT_CARD_URL` | http://order:8003/.well-known/agent.json | Agent card URL |

## Claude Code Development Notes

When extending the Orchestrator:

1. **Adding new agents**: Add card URL to docker-compose.yml and update `_agents_roster` building logic
2. **Custom routing logic**: Modify `router.py: classify_intent()` for keyword-based fallback
3. **System prompt**: Edit `routing_agent.py: root_instruction()` to change agent selection behavior
4. **Conversation context**: Adjust `ConversationManager` in `conversation.py` for longer/shorter history

## Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test routing
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "1", "message": "Find formal dresses"}'
```
