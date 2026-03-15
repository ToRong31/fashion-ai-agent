# API Reference

> Complete API documentation for the Fashion AI Agent system

## Orchestrator (Port 8000)

Main entry point for all AI chat requests.

### Endpoints

#### POST /chat

Process user message and route to appropriate agent.

**Request:**
```json
{
    "user_id": "1",
    "message": "Find me a black jacket"
}
```

**Response:**
```json
{
    "response": "Here are some black jackets...",
    "agent_used": "Search Agent",
    "data": {
        "products": [
            {
                "id": 1,
                "name": "Black Winter Jacket",
                "price": 129.99,
                "description": "..."
            }
        ]
    }
}
```

#### GET /health

Health check with available agents.

**Response:**
```json
{
    "status": "ok",
    "service": "orchestrator",
    "agents": [
        {"name": "Search Agent", "description": "..."},
        {"name": "Stylist Agent", "description": "..."},
        {"name": "Order Agent", "description": "..."}
    ]
}
```

#### GET /conversation/{user_id}

Get conversation history for a user.

**Response:**
```json
{
    "history": [
        {"role": "user", "content": "Find me a jacket"},
        {"role": "assistant", "content": "Here are some jackets..."}
    ]
}
```

---

## A2A Protocol (Worker Agents)

Each worker agent (ports 8001-8003) exposes A2A endpoints.

### Agent Card

#### GET /.well-known/agent.json

Returns agent capabilities in A2A format.

**Response:**
```json
{
    "name": "Search Agent",
    "description": "Searches the fashion product catalog...",
    "url": "http://search:8001/",
    "version": "0.1.0",
    "capabilities": {
        "streaming": false,
        "pushNotifications": false
    },
    "skills": [
        {
            "id": "product-search",
            "name": "Product Search",
            "description": "Search for fashion products...",
            "tags": ["search", "products", ...],
            "examples": ["Find me a black jacket", ...]
        }
    ],
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["application/json"]
}
```

### Send Message

#### POST /

Send a task to the agent.

**Request:**
```json
{
    "message": {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "text": "Find me a black jacket"
            }
        ],
        "messageId": "abc123"
    }
}
```

**Response (Success):**
```json
{
    "jsonrpc": "2.0",
    "id": "abc123",
    "result": {
        "id": "task-456",
        "status": {
            "message": {
                "role": "agent",
                "parts": [
                    {
                        "type": "text",
                        "text": "Here are some black jackets..."
                    }
                ]
            }
        }
    }
}
```

---

## Data Types

### ChatRequest
```python
class ChatRequest(BaseModel):
    user_id: str
    message: str
```

### ChatResponse
```python
class ChatResponse(BaseModel):
    response: str
    agent_used: str | None = None
    data: dict | None = None
```

### ToolDefinition
```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict
```

### ToolResult
```python
class ToolResult(BaseModel):
    content: Any
    data: dict | None = None
```

---

## Error Responses

### 400 Bad Request
```json
{
    "detail": "Invalid request format"
}
```

### 500 Internal Server Error
```json
{
    "detail": "Internal AI error"
}
```

---

## Integration with Backend

The AI Agents communicate with the Spring Boot backend at port 9000.

### Backend API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/products` | List all products |
| GET | `/api/products/{id}` | Get product details |
| POST | `/api/products/vector-search` | Semantic search |
| GET | `/api/users/{id}` | Get user info |
| PATCH | `/api/users/profile` | Update user preferences |
| POST | `/api/orders/auto-create` | Create order |
| GET | `/api/payments/vnpay-gen` | Generate payment link |

### Vector Search Request
```
POST /api/products/vector-search
{
    "query": "black winter jacket",
    "top_k": 5
}
```

### Create Order Request
```
POST /api/orders/auto-create
{
    "user_id": 1,
    "product_ids": [1, 2, 3]
}
```

---

## WebSocket (Future)

Not currently implemented but planned for streaming responses.

---

## Rate Limits

- No rate limits currently enforced
- Consider adding rate limiting in production

## Authentication

Currently none. For production:
- Add JWT validation at gateway
- Pass user context via A2A message metadata
