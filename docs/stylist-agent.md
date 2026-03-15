# Stylist Agent

> AI fashion stylist for coordinated outfit recommendations

## Purpose

The Stylist Agent provides **personalized fashion advice** and creates **coordinated outfit recommendations**. When users need styling help, this agent:
1. Fetches user preferences (size, color, style)
2. Searches for products matching the occasion/season
3. Recommends complete outfits with styling tips

## Development Context

- **File**: `services/stylist/agent.py`
- **Port**: 8002
- **Framework**: FastAPI + BaseAgent
- **LLM Integration**: OpenRouter (for outfit generation)

## How It Works

### Agent Registration

```
main.py → build_stylist_agent()
  │
  └─→ BaseAgent(name="Stylist Agent")
       └─→ register_skill(OutfitRecommendationSkill)
            │
            └─→ Agent Card published at /.well-known/agent.json
```

### Skill: OutfitRecommendationSkill

File: `services/stylist/skills/outfit_recommendation.py`

```python
class OutfitRecommendationSkill(Skill):
    id: "outfit-recommendation"
    name: "Outfit Recommendation"

    def get_tools(self):
        - search_products: Find products by style/occasion
        - get_product_catalog: Fetch all available products
        - get_user_preferences: Get user's size, color, style preferences

    async def execute_tool(tool_name, args):
        if tool_name == "search_products":
            → backend_client.vector_search()
        if tool_name == "get_product_catalog":
            → backend_client.get_products()
        if tool_name == "get_user_preferences":
            → backend_client.get_user(user_id)
```

### Tools

#### 1. search_products
```json
{
    "name": "search_products",
    "description": "Search for clothing products matching a specific description, style, occasion, or category",
    "parameters": {
        "query": "string - e.g. 'formal blazer', 'summer dress'",
        "top_k": "integer - max results (default 8)"
    }
}
```

#### 2. get_product_catalog
```json
{
    "name": "get_product_catalog",
    "description": "Fetch the complete product catalog for broad selection"
}
```

#### 3. get_user_preferences
```json
{
    "name": "get_user_preferences",
    "description": "Fetch user's stored style preferences",
    "parameters": {
        "user_id": "integer - The user's ID"
    }
}
```

### Prompt Instructions

```python
def get_prompt_instructions(self):
    return """
    You are a professional fashion stylist.

    Steps:
    1. Optionally fetch user preferences if user_id is known.
    2. Search for relevant products (by occasion, style, season, gender).
    3. Recommend a complete coordinated outfit using ONLY products from the catalog.
    4. Return a JSON object:
    {
      "outfit_name": "Name of the outfit",
      "occasion": "What occasion this outfit is for",
      "items": [
        {"product_id": 1, "name": "Product name", "price": 89.99, "role": "Role in outfit"}
      ],
      "reasoning": "Why these items work together",
      "styling_tips": "Additional styling advice"
    }

    Use real product IDs from search results.
    Always recommend a complete outfit (top + bottom + shoes at minimum).
    """
```

## User Preferences

The Stylist Agent personalizes recommendations based on stored user preferences:

```json
{
    "user_id": 1,
    "preferences": {
        "size": "M",
        "color": "black",
        "style": "minimal"
    }
}
```

Preferences are stored in the backend's `users.preferences` JSONB column.

## A2A Protocol

### Agent Card

```json
{
    "name": "Stylist Agent",
    "description": "AI fashion stylist that creates coordinated outfit recommendations based on user preferences, occasion, and season",
    "skills": [{
        "id": "outfit-recommendation",
        "name": "Outfit Recommendation",
        "description": "AI fashion stylist for coordinated outfit suggestions",
        "tags": ["stylist", "outfit", "fashion-advice", "recommendation", "style", "wear", "suggest"],
        "examples": [
            "Style me an outfit for a winter meeting",
            "What should I wear for a casual date?",
            "Recommend a formal look for an interview"
        ]
    }]
}
```

## Tags & Intent Matching

```python
tags = ["stylist", "outfit", "fashion-advice", "recommendation", "style", "wear", "suggest"]
```

| Tag | Example Triggers |
|-----|------------------|
| stylist | "style me", "stylist" |
| outfit | "outfit", "look" |
| recommend | "recommend", "suggestion" |
| style | "what to wear", "how to style" |
| wear | "what to wear" |

## Example Conversations

| User Message | Expected Behavior |
|-------------|-------------------|
| "Style me an outfit for a winter meeting" | Fetches preferences + searches winter professional wear + recommends outfit |
| "What should I wear for a casual date?" | Searches casual date options + recommends coordinated look |
| "Recommend a formal look for an interview" | Searches formal wear + suggests professional outfit |
| "I need a summer outfit" | Searches summer clothing + creates complete outfit |

## Backend Integration

### User Preferences API
```
GET /api/users/{user_id}

Response:
{
    "id": 1,
    "username": "demo_user",
    "preferences": {
        "size": "M",
        "color": "black",
        "style": "minimal"
    }
}
```

### Product Catalog API
```
GET /api/products

Response:
{
    "products": [...]
}
```

## Claude Code Development Notes

1. **Adding more personalization**: Store additional preferences (budget, brand preferences) in user profile
2. **Seasonal recommendations**: Add season detection based on date/time
3. **Body type styling**: Add body type to preferences for better recommendations
4. **Multi-occasion**: Support multiple occasions in single recommendation
5. **Price filtering**: Add budget parameter to outfit search

## Testing

```bash
# Health check
curl http://localhost:8002/health

# Test outfit recommendation
curl -X POST http://localhost:8002/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Style me an outfit for a winter meeting"}],
      "metadata": {"user_id": "1"}
    }
  }'
```
