# Search Agent

> Semantic vector search for fashion product catalog

## Purpose

The Search Agent handles **product discovery** requests. When users want to find specific items (clothes, shoes, accessories), this agent:
1. Accepts natural language queries
2. Performs semantic vector search via Elasticsearch
3. Returns relevant products with details

## Development Context

- **File**: `services/search/agent.py`
- **Port**: 8001
- **Framework**: FastAPI + BaseAgent
- **Backend Integration**: Elasticsearch vector search

## How It Works

### Agent Registration

```
main.py → build_search_agent()
  │
  └─→ BaseAgent(name="Search Agent")
       └─→ register_skill(ProductSearchSkill)
            │
            └─→ Agent Card published at /.well-known/agent.json
```

### Skill: ProductSearchSkill

File: `services/search/skills/product_search.py`

```python
class ProductSearchSkill(Skill):
    id: "product-search"
    name: "Product Search"

    def get_tools(self):
        - search_products: Vector search over product catalog

    async def execute_tool("search_products", args):
        └─→ backend_client.vector_search(query, top_k)
             └─→ POST /api/products/vector-search
```

### Tool Definition

```json
{
    "name": "search_products",
    "description": "Search for clothing products in the ToRoMe Store catalog.
                    Supports queries by product type, color, style, occasion, season, gender, or material.",
    "parameters": {
        "query": "string - Search query, e.g. 'black dress for party'",
        "top_k": "integer - Max results (default 5, max 20)"
    }
}
```

### Prompt Instructions

```
Use the `search_products` tool to find products in the catalog.
After getting results, present them in a markdown table:

| # | Product Name | Price | Description |
|---|------------|-------|-------------|

ALWAYS call search_products — never make up product data.
```

## A2A Protocol

### Agent Card

The Search Agent publishes its capabilities via A2A:

```json
{
    "name": "Search Agent",
    "description": "Searches the fashion product catalog using semantic vector search.",
    "skills": [{
        "id": "product-search",
        "name": "Product Search",
        "description": "Search for fashion products by natural language query",
        "tags": ["search", "products", "fashion", "catalog", "find", "browse"],
        "examples": [
            "Find me a black jacket",
            "Show me casual summer dresses",
            "I need formal shoes"
        ]
    }]
}
```

### Message Flow

```
Orchestrator                    Search Agent
     │                               │
     │──send_message(task)─────────►│
     │                               │
     │  A2A Message/Task Response   │
     │◄───[product results]──────────│
     │                               │
```

## Backend Integration

### Vector Search API

```
POST /api/products/vector-search
{
    "query": "black winter jacket",
    "top_k": 5
}

Response:
{
    "products": [
        {
            "id": 1,
            "name": "Black Winter Jacket",
            "price": 129.99,
            "description": "Warm winter jacket...",
            "category": "outerwear",
            "color": "black",
            ...
        }
    ]
}
```

### Backend Client

File: `shared/backend_client.py`

```python
class BackendClient:
    async def vector_search(self, query: str, top_k: int = 5) -> dict:
        response = await client.post(
            "/api/products/vector-search",
            json={"query": query, "top_k": top_k}
        )
        return response.json()
```

## Tags & Intent Matching

The Search Agent uses these tags for keyword-based fallback routing:

```python
tags = ["search", "products", "fashion", "catalog", "find", "browse"]
```

| Tag | Example Triggers |
|-----|------------------|
| search | "search for", "find" |
| products | "product", "item" |
| catalog | "catalog", "available" |
| find | "find me", "looking for" |
| browse | "show me", "what do you have" |

## Example Conversations

| User Message | Expected Behavior |
|-------------|-------------------|
| "Find me a black jacket" | Calls search_products with query="black jacket" |
| "Show me casual summer dresses" | Calls search_products with query="casual summer dresses" |
| "I need formal shoes" | Calls search_products with query="formal shoes" |

## Claude Code Development Notes

1. **Adding new search fields**: Update backend's Elasticsearch mapping + add to ProductSearchSkill tool params
2. **Custom result formatting**: Modify `get_prompt_instructions()` in ProductSearchSkill
3. **Search ranking tuning**: Adjust backend's vector search weights (category, color, price)
4. **Pagination**: Add offset/limit params to search_products tool

## Testing

```bash
# Health check
curl http://localhost:8001/health

# Direct A2A message test
curl -X POST http://localhost:8001/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Find casual summer dresses"}]
    }
  }'
```
