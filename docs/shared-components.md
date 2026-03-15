# Shared Components

> Reusable modules shared across all agents

## Overview

The `shared/` directory contains common infrastructure used by all agents:

```
shared/
├── base_agent/           # Agent framework
│   ├── agent.py         # BaseAgent class
│   ├── skill.py         # Skill abstract class
│   ├── tool.py          # Tool definitions
│   ├── yaml_loader.py   # Config loading
│   └── executor.py     # Tool execution
├── models/              # Data models
│   ├── product.py       # Product model
│   ├── user.py         # User model
│   ├── order.py        # Order model
│   └── agent.py        # Agent models
├── backend_client.py    # Backend API client
├── config.py            # Configuration
└── logging_config.py   # Logging setup
```

---

## BaseAgent

File: `shared/base_agent/agent.py`

The `BaseAgent` class is the foundation for all worker agents. It provides:

### Features

1. **Skill Registration**: Register multiple skills
2. **Tool Aggregation**: Collect tools from all skills
3. **System Prompt Building**: Combine skill instructions
4. **A2A Agent Card**: Auto-generate agent metadata

### Class Definition

```python
class BaseAgent:
    def __init__(self, name: str, description: str, version: str = "0.1.0")

    # Skill management
    def register_skill(self, skill: Skill) -> None
    def get_skill(self, skill_id: str) -> Skill | None
    def find_skill_for_tool(self, tool_name: str) -> Skill | None

    # Tool aggregation
    def get_all_openai_tools(self) -> list[dict]

    # System prompt
    def build_system_prompt(self) -> str

    # A2A
    def build_agent_card(self, host: str, port: int) -> AgentCard
```

### Usage Example

```python
from shared.base_agent.agent import BaseAgent
from my_skill import MySkill

agent = BaseAgent(
    name="My Agent",
    description="What my agent does"
)
agent.register_skill(MySkill())

# Get A2A card for publishing
card = agent.build_agent_card(host="http://myagent", port=8000)
```

---

## Skill (Abstract Class)

File: `shared/base_agent/skill.py`

The `Skill` class defines the interface for agent capabilities.

### Abstract Methods

```python
class Skill:
    @property
    def id(self) -> str:
        """Unique skill identifier"""

    @property
    def name(self) -> str:
        """Human-readable skill name"""

    @property
    def description(self) -> str:
        """What the skill does"""

    @property
    def tags(self) -> list[str]:
        """Keywords for intent matching"""

    @property
    def examples(self) -> list[str]:
        """Example user messages"""

    def get_tools(self) -> list[ToolDefinition]:
        """Return list of available tools"""

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute a tool and return result"""

    def get_prompt_instructions(self) -> str:
        """Instructions for the LLM"""
```

### ToolDefinition

```python
class ToolDefinition(BaseModel):
    name: str                          # Tool name
    description: str                    # What it does
    parameters: dict                    # JSON Schema for params
```

### ToolResult

```python
class ToolResult(BaseModel):
    content: Any                        # Display content
    data: dict | None = None           # Structured data
```

### Example Skill

```python
class MySkill(Skill):
    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def id(self) -> str:
        return "my-skill"

    @property
    def name(self) -> str:
        return "My Skill"

    @property
    def description(self) -> str:
        return "Does something useful"

    @property
    def tags(self) -> list[str]:
        return ["do", "something", "useful"]

    @property
    def examples(self) -> list[str]:
        return ["Do something for me"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="do_something",
                description="Do something useful",
                parameters={"type": "object", "properties": {}}
            )
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "do_something":
            # ... do work
            return ToolResult(content="Done!")
        raise ValueError(f"Unknown tool: {tool_name}")

    def get_prompt_instructions(self) -> str:
        return "Instructions for the LLM..."
```

---

## BackendClient

File: `shared/backend_client.py`

HTTP client for communicating with the Spring Boot backend.

### Methods

```python
class BackendClient:
    async def vector_search(query: str, top_k: int = 5) -> dict
    async def get_product(product_id: int) -> dict
    async def get_products() -> dict
    async def get_user(user_id: int) -> dict
    async def update_user_profile(user_id: int, preferences: dict) -> dict
    async def auto_create_order(user_id: int, product_ids: list[int]) -> dict
    async def get_payment_link(order_id: int) -> dict
```

### Usage

```python
from shared.backend_client import BackendClient
from shared.config import BackendSettings

# Initialize with settings
settings = BackendSettings()
client = BackendClient(settings)

# Make API calls
result = await client.vector_search("black jacket", top_k=5)
products = result.get("products", [])

# Always close when done
await client.close()
```

---

## Configuration

File: `shared/config.py`

### Settings Classes

```python
class BackendSettings:
    base_url: str          # Backend API URL (default: http://localhost:9000)
    timeout: float        # Request timeout (default: 30s)

class LLMSettings:
    openai_api_key: str   # OpenAI API key
    openai_base_url: str  # Base URL (for OpenRouter)
    openai_model: str     # Model name

class AgentSettings:
    host: str             # Agent host
    port: int             # Agent port
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_BASE_URL` | http://localhost:9000 | Backend API URL |
| `OPENAI_API_KEY` | - | OpenAI API key |
| `OPENAI_BASE_URL` | - | OpenAI-compatible base URL |
| `OPENAI_MODEL` | gpt-4o-mini | Model to use |
| `{AGENT}_PORT` | - | Agent port (SEARCH_AGENT_PORT, etc.) |

---

## Data Models

### Product

```python
class Product(BaseModel):
    id: int
    name: str
    price: float
    description: str | None
    category: str | None
    color: str | None
    # ... other fields
```

### User

```python
class User(BaseModel):
    id: int
    username: str
    email: str | None
    preferences: dict  # JSONB: {size, color, style}
```

### Order

```python
class Order(BaseModel):
    id: int
    user_id: int
    status: str        # PENDING, PAID, etc.
    items: list
    total_amount: float
    created_at: datetime
```

---

## Logging

File: `shared/logging_config.py`

```python
def setup_logging(
    log_level: str = "INFO",
    service_name: str = "agent"
):
    """Configure structured logging with structlog"""
```

### Usage

```python
from shared.logging_config import setup_logging
import structlog

logger = structlog.get_logger()

setup_logging(log_level="DEBUG", service_name="my-agent")
logger.info("something_happened", key="value")
```

---

## Creating a New Agent

### Step 1: Create Service Directory

```
services/
├── new_agent/
│   ├── __init__.py
│   ├── agent.py      # Build agent
│   ├── main.py       # FastAPI app
│   ├── skills/      # Skills
│   │   ├── __init__.py
│   │   └── new_skill.py
│   └── tools/       # Tool implementations
│       ├── __init__.py
│       └── my_tool.py
```

### Step 2: Create Skill

```python
# services/new_agent/skills/new_skill.py
from shared.base_agent.skill import Skill, ToolDefinition, ToolResult

class NewSkill(Skill):
    @property
    def id(self) -> str:
        return "new-skill"

    # ... implement other properties

    def get_tools(self) -> list[ToolDefinition]:
        return [...]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        ...
```

### Step 3: Build Agent

```python
# services/new_agent/agent.py
from shared.base_agent.agent import BaseAgent
from shared.backend_client import BackendClient
from services.new_agent.skills.new_skill import NewSkill

def build_new_agent(backend_client: BackendClient) -> BaseAgent:
    agent = BaseAgent(
        name="New Agent",
        description="What it does"
    )
    agent.register_skill(NewSkill(backend_client))
    return agent
```

### Step 4: Create FastAPI App

```python
# services/new_agent/main.py
from fastapi import FastAPI
from a2a.server import A2AServer
from shared.config import AgentSettings
from shared.backend_client import BackendClient
from services.new_agent.agent import build_new_agent

app = FastAPI()
settings = AgentSettings()
backend = BackendClient()
agent = build_new_agent(backend)

# Add A2A server
a2a_server = A2AServer(
    agent_card=agent.build_agent_card(settings.host, settings.port),
    agent_executor=agent
)
app.mount("/", a2a_server.app)
```

### Step 5: Add to Docker Compose

```yaml
# docker-compose.yml
services:
  new_agent:
    build: ./services/new_agent
    ports:
      - "8004:8004"
    environment:
      - NEW_AGENT_PORT=8004
```

---

## Testing Shared Components

```bash
# Test backend client
pytest tests/test_backend_client.py

# Test base agent
pytest tests/test_base_agent.py

# Run all tests
pytest tests/
```
