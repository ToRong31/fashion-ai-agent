"""Product Search Skill - semantic vector search over the fashion product catalog."""
from pathlib import Path

import structlog
import yaml

from shared.base_agent.skill import Skill, ToolDefinition, ToolResult
from shared.backend_client import BackendClient

logger = structlog.get_logger()


def _load_prompt(filename: str) -> str:
    yaml_path = Path(__file__).parent / "prompts" / filename
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["prompt"]


class ProductSearchSkill(Skill):
    """Search the product catalog using semantic/vector search."""

    def __init__(self, backend_client: BackendClient):
        self._backend = backend_client

    @property
    def id(self) -> str:
        return "product-search"

    @property
    def name(self) -> str:
        return "Product Search"

    @property
    def description(self) -> str:
        return "Search for fashion products by natural language query"

    @property
    def tags(self) -> list[str]:
        return ["search", "products", "fashion", "catalog", "find", "browse"]

    @property
    def examples(self) -> list[str]:
        return [
            "Find me a black jacket",
            "Show me casual summer dresses",
            "I need formal shoes",
        ]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_products",
                description=(
                    "Search for clothing products in the ToRoMe Store catalog. "
                    "Supports queries by product type, color, style, occasion, season, gender, or material."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query, e.g. 'black dress for party', 'winter jacket men'",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default 5, max 20)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            )
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name != "search_products":
            raise ValueError(f"Unknown tool: {tool_name}")

        query = args["query"]
        top_k = args.get("top_k", 5)
        logger.info("searching_products", query=query, top_k=top_k)

        result = await self._backend.vector_search(query, top_k)
        products = result.get("products", [])
        logger.info("search_results", count=len(products))

        return ToolResult(
            content=products,
            data={"products": products},
        )

    def get_prompt_instructions(self) -> str:
        return _load_prompt("product-search.yaml")
