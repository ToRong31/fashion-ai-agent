"""
Planning Agent — analyzes user requests and creates execution plans for multi-agent workflows.

This module provides:
- ExecutionMode: SINGLE, SEQUENTIAL, PARALLEL execution modes
- ExecutionStep: A single step in an execution plan
- ExecutionPlan: Complete execution plan with mode and steps
- PlanningAgent: LLM-based planner that analyzes requests and creates plans
"""
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

if TYPE_CHECKING:
    from services.orchestrator.conversation import Message

logger = structlog.get_logger()


def _load_planning_prompt() -> dict:
    yaml_path = Path(__file__).parent / "skills" / "prompts" / "planning.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class ExecutionMode(Enum):
    """Execution mode for multi-agent workflows."""

    SINGLE = "single"  # Traditional: one agent
    SEQUENTIAL = "sequential"  # Multi-step, one agent at a time
    PARALLEL = "parallel"  # Multiple agents simultaneously


@dataclass
class ExecutionStep:
    """A single step in the execution plan."""

    step_id: str
    agent_name: str  # search, order, stylist
    task: str
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on
    context: dict = field(default_factory=dict)  # Passed from previous steps


@dataclass
class ExecutionPlan:
    """Complete execution plan for a user request."""

    mode: ExecutionMode
    steps: list[ExecutionStep]
    estimated_response: str = ""  # How to present results


# Common multi-agent patterns for regex-based planning
MULTI_AGENT_PATTERNS = {
    # "find X and add to cart" → search + order
    r"find\s+(.+?)\s+and\s+(add to cart|add to my cart|buy|thêm vào giỏ|mua)": {
        "mode": ExecutionMode.SEQUENTIAL,
        "steps": [
            {"agent": "Search Agent", "template": "Find {match_group_1}"},
            {"agent": "Order Agent", "template": "Add the best matching product to cart"},
        ],
    },
    # "find X and checkout" → search + order + payment
    r"find\s+(.+?)\s+and\s+(checkout|buy now|purchase|thanh toán|mua ngay)": {
        "mode": ExecutionMode.SEQUENTIAL,
        "steps": [
            {"agent": "Search Agent", "template": "Find {match_group_1}"},
            {"agent": "Order Agent", "template": "Create order from the found product and get payment link"},
        ],
    },
    # "find X and style" → search + stylist
    r"find\s+(.+?)\s+and\s+(style|recommend|outfit|gợi ý|phong cách)": {
        "mode": ExecutionMode.SEQUENTIAL,
        "steps": [
            {"agent": "Search Agent", "template": "Find {match_group_1}"},
            {"agent": "Stylist Agent", "template": "Style recommendations for the found products"},
        ],
    },
    # "show me X and Y" → parallel search
    r"(show me|find|search)\s+(.+?)\s+(and|also)\s+(.+?)": {
        "mode": ExecutionMode.PARALLEL,
        "steps": [
            {"agent": "Search Agent", "template": "Find {match_group_2}"},
            {"agent": "Search Agent", "template": "Find {match_group_4}"},
        ],
    },
}


class PlanningAgent:
    """
    Analyzes user request and creates execution plan.

    Uses both regex patterns (fast) and LLM-based planning (flexible) to determine
    whether a request needs single-agent or multi-agent handling.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        self._openai = openai_client
        self._model = model
        self._use_llm = openai_client is not None

    async def create_plan(
        self,
        user_message: str,
        context: dict | None = None,
        conversation_history: list["Message"] = None,
    ) -> ExecutionPlan:
        """
        Analyze request and create execution plan with conversation context.

        The planner uses the conversation history to understand what products
        the user is referring to (e.g., "add all" = all products from previous search).

        Args:
            user_message: The user's input message
            context: Optional context (user_id, token, etc.)
            conversation_history: Conversation history with structured data (products)

        Returns:
            ExecutionPlan with mode, steps, and estimated response
        """
        context = context or {}
        conversation_history = conversation_history or []

        # Get products from conversation history
        all_products = self._extract_products_from_history(conversation_history)

        # Check if user wants all items and we have products
        if self._wants_all_items(user_message) and all_products:
            return await self._plan_add_all(user_message, all_products, context)

        # Check if user is selecting specific items (e.g., "add item 1, 3, 5")
        selected_items = self._extract_item_selections(user_message, all_products)
        if selected_items:
            return await self._plan_add_specific_items(
                user_message, selected_items, context
            )

        # Check if user wants to continue a search+action flow
        if self._is_continuation(user_message) and all_products:
            return await self._plan_with_previous_products(
                user_message, all_products, context
            )

        # First, try regex-based pattern matching (fast path)
        plan = self._try_pattern_matching(user_message)
        if plan:
            logger.info("plan_created_from_pattern", mode=plan.mode.value, steps=len(plan.steps))
            return plan

        # Fall back to LLM-based planning
        if self._use_llm:
            plan = await self._create_plan_llm(user_message, context, all_products)
            logger.info("plan_created_from_llm", mode=plan.mode.value, steps=len(plan.steps))
            return plan

        # Default to single-agent (search)
        return ExecutionPlan(
            mode=ExecutionMode.SINGLE,
            steps=[ExecutionStep(step_id="1", agent_name="Search Agent", task=user_message)],
            estimated_response="Search results",
        )

    def _extract_products_from_history(
        self, history: list["Message"]
    ) -> list[dict]:
        """Extract products from conversation history."""
        for msg in reversed(history):
            if msg.products:
                return msg.products
        return []

    def _wants_all_items(self, message: str) -> bool:
        """Check if user wants all items."""
        all_keywords = [
            "all", "tất cả", "every", "add all", "add everything",
            "get all", "mua tất cả", "thêm tất cả", "all of them",
            "all items", "every item"
        ]
        lower = message.lower()
        return any(kw in lower for kw in all_keywords)

    def _extract_item_selections(
        self, message: str, available_products: list[dict]
    ) -> list[dict] | None:
        """Extract specific item selections (e.g., 'item 1, 3, 5')."""
        import re

        lower = message.lower()

        # Pattern for "item 1, 3, 5" or "items 1-5" or "products 1 and 2"
        patterns = [
            r"item[s]?\s+([\d,\s\-and]+)",  # item 1, 3, 5
            r"product[s]?\s+([\d,\s\-and]+)",  # product 1 and 3
            r"#([\d,\s\-and]+)",  # #1, #3
            r"(\d+)(?:,|and|\s+)(?:and\s+)?(\d+)",  # 1 and 3
        ]

        for pattern in patterns:
            matches = re.findall(pattern, lower)
            if matches:
                # Parse the numbers
                numbers = []
                for match in matches:
                    # Handle different match formats
                    if isinstance(match, str):
                        # Split by comma, space, or 'and'
                        parts = re.split(r"[,\s]+|and", match)
                        numbers.extend([int(p.strip()) for p in parts if p.strip().isdigit()])
                    elif isinstance(match, tuple):
                        numbers.extend([int(p) for p in match if p.isdigit()])

                if numbers:
                    # Get selected products
                    selected = []
                    for idx in numbers:
                        if 0 < idx <= len(available_products):
                            selected.append(available_products[idx - 1])  # 1-indexed

                    if selected:
                        return selected

        return None

    def _is_continuation(self, message: str) -> bool:
        """Check if this is a continuation of previous action."""
        continuation_keywords = [
            "add to cart", "add them", "add to my cart",
            "buy them", "purchase", "checkout", "thanh toán",
            "giỏ hàng", "mua ngay"
        ]
        lower = message.lower()
        return any(kw in lower for kw in continuation_keywords)

    async def _plan_add_all(
        self,
        user_message: str,
        products: list[dict],
        context: dict,
    ) -> ExecutionPlan:
        """Plan to add all products to cart."""

        # Extract all product IDs
        product_ids = [p.get("id") for p in products if p.get("id")]

        if not product_ids:
            # No valid products, fall back to search
            return ExecutionPlan(
                mode=ExecutionMode.SINGLE,
                steps=[ExecutionStep(step_id="1", agent_name="Search Agent", task=user_message)],
            )

        user_id = context.get("user_id", 1)

        # Format product info for Order Agent
        product_info = self._format_products_for_order(products)

        # Build the products list as JSON for the tool
        products_json = json.dumps([
            {
                "product_id": p.get("id"),
                "product_name": p.get("name"),
                "price": p.get("price"),
            }
            for p in products if p.get("id")
        ])

        user_id = context.get("user_id", 1)

        # SEQUENTIAL: Order Agent with all products
        return ExecutionPlan(
            mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="1",
                    agent_name="Order Agent",
                    task=f"""Add ALL {len(products)} products to cart using add_multiple_to_cart tool.

Products to add:
{product_info}

IMPORTANT: You MUST use the add_multiple_to_cart tool (NOT add_to_cart) with this exact products list:
{products_json}

Call add_multiple_to_cart with the products list above. [user_id={user_id}]""",
                    context={"product_ids": product_ids, "all_products": products, "add_all": True, "user_id": user_id},
                ),
            ],
            estimated_response=f"Added all {len(products)} products to cart",
        )

    async def _plan_add_specific_items(
        self,
        user_message: str,
        selected_products: list[dict],
        context: dict,
    ) -> ExecutionPlan:
        """Plan to add specific selected items to cart."""

        product_ids = [p.get("id") for p in selected_products if p.get("id")]
        product_info = self._format_products_for_order(selected_products)
        user_id = context.get("user_id", 1)

        return ExecutionPlan(
            mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="1",
                    agent_name="Order Agent",
                    task=f"Add these specific products to cart:\n\n{product_info}\n\nProduct IDs: {product_ids} [user_id={user_id}]",
                    context={"product_ids": product_ids, "selected_products": selected_products, "user_id": user_id},
                ),
            ],
            estimated_response=f"Added {len(selected_products)} products to cart",
        )

    async def _plan_with_previous_products(
        self,
        user_message: str,
        products: list[dict],
        context: dict,
    ) -> ExecutionPlan:
        """Plan action with previous search results."""

        product_ids = [p.get("id") for p in products if p.get("id")]
        product_info = self._format_products_for_order(products)
        user_id = context.get("user_id", 1)

        # Determine action based on message
        if any(kw in user_message.lower() for kw in ["cart", "add", "thêm", "giỏ"]):
            action = "add to cart"
        elif any(kw in user_message.lower() for kw in ["checkout", "buy", "mua", "thanh toán"]):
            action = "checkout"
        else:
            action = "add to cart"

        return ExecutionPlan(
            mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="1",
                    agent_name="Order Agent",
                    task=f"{action.capitalize()} with these products:\n\n{product_info}\n\nProduct IDs: {product_ids} [user_id={user_id}]",
                    context={"product_ids": product_ids, "products": products, "user_id": user_id},
                ),
            ],
            estimated_response=f"{action} completed with {len(products)} products",
        )

    def _format_products_for_order(self, products: list[dict]) -> str:
        """Format products for Order Agent task."""
        lines = []
        for i, p in enumerate(products, 1):
            pid = p.get("id", "?")
            name = p.get("name", "Unknown")
            price = p.get("price", 0)
            lines.append(f"{i}. ID:{pid} - {name} - ${price}")
        return "\n".join(lines)

    def _try_pattern_matching(self, user_message: str) -> ExecutionPlan | None:
        """Try to match user message against known multi-agent patterns."""
        lower = user_message.lower()

        for pattern, plan_config in MULTI_AGENT_PATTERNS.items():
            match = re.search(pattern, lower)
            if match:
                mode = plan_config["mode"]
                steps_config = plan_config["steps"]

                # Build steps with actual query
                steps = []
                for i, step_config in enumerate(steps_config):
                    task = step_config["template"]

                    # Replace {match_group_X} with actual matched content
                    for group_idx in range(1, len(match.groups()) + 1):
                        placeholder = f"{{match_group_{group_idx}}}"
                        if placeholder in task and match.group(group_idx):
                            task = task.replace(placeholder, match.group(group_idx))

                    # For sequential mode, add dependency on previous step
                    depends_on = []
                    if mode == ExecutionMode.SEQUENTIAL and i > 0:
                        depends_on = [f"{i}"]

                    steps.append(
                        ExecutionStep(
                            step_id=str(i + 1),
                            agent_name=step_config["agent"],
                            task=task,
                            depends_on=depends_on,
                        )
                    )

                return ExecutionPlan(
                    mode=mode,
                    steps=steps,
                    estimated_response=self._build_response_template(mode, steps),
                )

        return None

    def _build_response_template(self, mode: ExecutionMode, steps: list[ExecutionStep]) -> str:
        """Build estimated response template based on execution mode."""
        if mode == ExecutionMode.SINGLE:
            return "Search results from {agent}"

        if mode == ExecutionMode.SEQUENTIAL:
            agent_names = [s.agent_name for s in steps]
            return f"Results from {' → '.join(agent_names)}"

        if mode == ExecutionMode.PARALLEL:
            return "Combined search results"

        return "Results"

    async def _create_plan_llm(
        self,
        user_message: str,
        context: dict,
        products: list[dict] = None,
    ) -> ExecutionPlan:
        """Use LLM to analyze and create execution plan with optional product context."""

        products = products or []

        # Build product context if available
        product_context = ""
        if products:
            product_context = f"""

CURRENT PRODUCTS IN CONTEXT (from previous search):
{self._format_products_for_order(products)}

If the user wants to "add all" or "add them", use these products.
If the user selects specific items (e.g., "item 1, 3, 5"), use those specific products.
"""

        system_prompt = f"""
{_load_planning_prompt()["prompt"]}

{product_context}
"""

        response = await self._openai.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
        )

        try:
            result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as e:
            logger.error("llm_plan_parse_failed", error=str(e), content=response.choices[0].message.content)
            # Default to single-agent search
            return ExecutionPlan(
                mode=ExecutionMode.SINGLE,
                steps=[ExecutionStep(step_id="1", agent_name="Search Agent", task=user_message)],
            )

        # Parse the LLM response into ExecutionPlan
        mode_str = result.get("mode", "SINGLE")
        mode = ExecutionMode(mode_str.lower())

        steps = []
        for step_data in result.get("steps", []):
            step = ExecutionStep(
                step_id=step_data.get("step_id", "1"),
                agent_name=step_data.get("agent_name", "Search Agent"),
                task=step_data.get("task", user_message),
            )

            # If Order Agent and we have products, add them to context
            if step.agent_name == "Order Agent" and products:
                product_ids = [p.get("id") for p in products if p.get("id")]
                step.context = {"product_ids": product_ids, "products": products}

            steps.append(step)

        return ExecutionPlan(
            mode=mode,
            steps=steps,
            estimated_response=self._build_response_template(mode, steps),
        )
