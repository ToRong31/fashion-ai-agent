"""
Plan Executor — executes multi-agent execution plans.

This module provides:
- PlanExecutor: Executes ExecutionPlan with single, sequential, or parallel modes
- Handles context passing between sequential steps
- Aggregates results from multiple agents
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from services.orchestrator.planning_agent import ExecutionMode, ExecutionPlan, ExecutionStep

logger = structlog.get_logger()


@dataclass
class ExecutionResult:
    """Result from executing a single step."""

    step_id: str
    agent_name: str
    text: str
    data: dict | None = None
    error: str | None = None


class PlanExecutor:
    """
    Executes execution plans with support for single, sequential, and parallel modes.
    """

    def __init__(self, agent_connections: dict[str, Any]):
        """
        Initialize with remote agent connections.

        Args:
            agent_connections: Dict mapping agent names to their connection objects
                              that have a `send_message` method
        """
        self._connections = agent_connections

    async def execute(self, plan: ExecutionPlan, context: dict) -> dict:
        """
        Execute the plan and return combined results.

        Args:
            plan: The execution plan to execute
            context: Context including user_id, token, etc.

        Returns:
            Dict with:
            - results: Dict mapping step_id to ExecutionResult
            - mode: The execution mode used
            - agents_used: List of agent names used
        """
        logger.info("plan_execution_start", mode=plan.mode.value, steps=len(plan.steps))

        if plan.mode == ExecutionMode.SINGLE:
            return await self._execute_single(plan.steps[0], context)

        elif plan.mode == ExecutionMode.SEQUENTIAL:
            return await self._execute_sequential(plan.steps, context)

        elif plan.mode == ExecutionMode.PARALLEL:
            return await self._execute_parallel(plan.steps, context)

        else:
            raise ValueError(f"Unknown execution mode: {plan.mode}")

    async def _execute_single(self, step: ExecutionStep, context: dict) -> dict:
        """Execute a single step and return the result."""

        logger.info("executing_single_step", agent=step.agent_name, task=step.task[:50])

        try:
            result = await self._send_to_agent(step.agent_name, step.task, context)
            return {
                "results": {step.step_id: result},
                "mode": ExecutionMode.SINGLE.value,
                "agents_used": [step.agent_name],
                "text": result.text,
                "data": result.data,
            }
        except Exception as e:
            logger.error("single_step_failed", agent=step.agent_name, error=str(e))
            return {
                "results": {
                    step.step_id: ExecutionResult(
                        step_id=step.step_id,
                        agent_name=step.agent_name,
                        text="",
                        error=str(e),
                    )
                },
                "mode": ExecutionMode.SINGLE.value,
                "agents_used": [step.agent_name],
                "text": f"Error: {str(e)}",
                "data": None,
            }

    async def _execute_sequential(
        self, steps: list[ExecutionStep], context: dict
    ) -> dict:
        """
        Execute steps in order, passing context between steps.

        For example:
        1. Search Agent finds products
        2. Order Agent uses the product info to add to cart
        """
        results: dict[str, ExecutionResult] = {}
        accumulated_context = context.copy()
        all_text_parts = []
        all_data: dict = {}
        agents_used = []

        for step in steps:
            logger.info(
                "executing_sequential_step",
                step_id=step.step_id,
                agent=step.agent_name,
                depends_on=step.depends_on,
            )

            # Build task with context from previous steps
            task = self._build_task_with_context(step, results, accumulated_context)

            try:
                result = await self._send_to_agent(step.agent_name, task, context)
                results[step.step_id] = result
                agents_used.append(step.agent_name)

                # Accumulate text and data
                if result.text:
                    all_text_parts.append(result.text)
                if result.data:
                    all_data[step.step_id] = result.data

                # Update accumulated context for next step
                accumulated_context.update({
                    f"step_{step.step_id}_result": result.data or {},
                    f"step_{step.step_id}_text": result.text,
                })

            except Exception as e:
                logger.error("sequential_step_failed", step_id=step.step_id, error=str(e))
                results[step.step_id] = ExecutionResult(
                    step_id=step.step_id,
                    agent_name=step.agent_name,
                    text="",
                    error=str(e),
                )
                all_text_parts.append(f"Error in step {step.step_id}: {str(e)}")
                # Continue with next step even if this one failed

        # Combine all text results
        combined_text = "\n\n".join(all_text_parts)

        return {
            "results": results,
            "mode": ExecutionMode.SEQUENTIAL.value,
            "agents_used": agents_used,
            "text": combined_text,
            "data": all_data,
        }

    async def _execute_parallel(self, steps: list[ExecutionStep], context: dict) -> dict:
        """
        Execute independent steps in parallel.

        For example:
        - Search for white shirts AND black pants simultaneously
        """
        results: dict[str, ExecutionResult] = {}
        all_text_parts = []
        all_data: dict = {}
        agents_used = []

        # Create tasks for parallel execution
        async def execute_step(step: ExecutionStep) -> tuple[str, ExecutionResult]:
            logger.info("executing_parallel_step", step_id=step.step_id, agent=step.agent_name)
            try:
                result = await self._send_to_agent(step.agent_name, step.task, context)
                return step.step_id, result
            except Exception as e:
                logger.error("parallel_step_failed", step_id=step.step_id, error=str(e))
                return step.step_id, ExecutionResult(
                    step_id=step.step_id,
                    agent_name=step.agent_name,
                    text="",
                    error=str(e),
                )

        # Execute all steps in parallel
        task_coroutines = [execute_step(step) for step in steps]
        step_results = await asyncio.gather(*task_coroutines, return_exceptions=True)

        # Process results
        for i, step in enumerate(steps):
            result = step_results[i]
            if isinstance(result, Exception):
                logger.error("parallel_task_exception", step_id=step.step_id, error=str(result))
                results[step.step_id] = ExecutionResult(
                    step_id=step.step_id,
                    agent_name=step.agent_name,
                    text="",
                    error=str(result),
                )
                all_text_parts.append(f"Error: {str(result)}")
            else:
                step_id, exec_result = result
                results[step_id] = exec_result
                agents_used.append(step.agent_name)

                if exec_result.text:
                    all_text_parts.append(exec_result.text)
                if exec_result.data:
                    all_data[step_id] = exec_result.data

        # Combine all text results
        combined_text = "\n\n---\n\n".join(all_text_parts)

        return {
            "results": results,
            "mode": ExecutionMode.PARALLEL.value,
            "agents_used": list(set(agents_used)),  # Deduplicate
            "text": combined_text,
            "data": all_data,
        }

    def _build_task_with_context(
        self,
        step: ExecutionStep,
        previous_results: dict[str, ExecutionResult],
        accumulated_context: dict,
    ) -> str:
        """
        Build the task string for a step, incorporating previous results.

        For sequential workflows, this passes product info from Search Agent
        to Order Agent. Supports single and multi-product operations.
        """
        import json

        task = step.task

        # First, check if step has context with products (from planning)
        if step.context and "product_ids" in step.context:
            product_ids = step.context.get("product_ids", [])
            products = step.context.get("all_products") or step.context.get("products", [])

            if products and len(products) > 0:
                # Format all products for the task
                product_info = self._format_products_for_task(products)

                # Build products JSON for add_multiple_to_cart tool
                products_json = json.dumps([
                    {
                        "product_id": p.get("id"),
                        "product_name": p.get("name"),
                        "price": p.get("price"),
                    }
                    for p in products if p.get("id")
                ])

                if len(product_ids) > 1:
                    # Multi-product: use add_multiple_to_cart
                    task = task + f"""\n\nProducts to add:
{product_info}

Product IDs: {product_ids}

IMPORTANT: Use add_multiple_to_cart tool with this exact products list:
{products_json}"""
                else:
                    # Single product: use add_to_cart
                    task = task + f"\n\nProduct to add:\n{product_info}\n\nProduct ID: {product_ids[0]}"

        # If there are previous results, incorporate them into the task
        elif previous_results:
            # Get the last result
            last_result = list(previous_results.values())[-1]

            # If the last result has product data, include it
            if last_result.data:
                data = last_result.data

                # Check for products in data
                if "products" in data and data["products"]:
                    products = data["products"]
                    if isinstance(products, list) and len(products) > 0:
                        # Format all products, not just the first one
                        product_info = self._format_products_for_task(products)
                        product_ids = [p.get("id") for p in products if p.get("id")]
                        task = task + f"\n\nProducts found:\n{product_info}\n\nProduct IDs: {product_ids}"

                # Check for cart item
                if "cart_item" in data:
                    cart_item = data["cart_item"]
                    task = task + f"\n\nCart context: {cart_item}"

                # Check for order
                if "order" in data:
                    order = data["order"]
                    task = task + f"\n\nOrder context: Order ID {order.get('id')}"

        return task

    def _format_products_for_task(self, products: list[dict]) -> str:
        """Format products for task description."""
        lines = []
        for i, p in enumerate(products, 1):
            pid = p.get("id", "?")
            name = p.get("name", "Unknown")
            price = p.get("price", 0)
            lines.append(f"{i}. ID:{pid} - {name} - ${price}")
        return "\n".join(lines)

    async def _send_to_agent(self, agent_name: str, task: str, context: dict) -> ExecutionResult:
        """
        Send task to a remote agent via A2A.

        Args:
            agent_name: Name of the agent to call
            task: Task description
            context: Context including user_id, token

        Returns:
            ExecutionResult with text and optional data
        """
        import uuid
        from a2a.types import SendMessageRequest, MessageSendParams

        if agent_name not in self._connections:
            raise ValueError(f"Agent '{agent_name}' not found. Available: {list(self._connections.keys())}")

        # Add user_id to task if present in context
        if "user_id" in context and context["user_id"]:
            user_id = context["user_id"]
            task = f"{task} [user_id={user_id}]"

        # Add JWT token if present in context
        if "token" in context and context["token"]:
            token = context["token"]
            task = f"{task} [SYSTEM: JWT_TOKEN={token}]"

        # Get the connection and send message
        connection = self._connections[agent_name]

        # Build A2A request
        message_id = uuid.uuid4().hex
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
            }
        }
        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams.model_validate(payload),
        )

        # Send message via A2A
        response = await connection.send_message(request)

        # Extract text and data from response (using same logic as RoutingAgent)
        from services.orchestrator.routing_agent import RoutingAgent

        result_data = response.root.result if hasattr(response, "root") else response
        text = RoutingAgent._extract_text_from_result(result_data)
        data = RoutingAgent._extract_data_from_result(result_data)

        return ExecutionResult(
            step_id="",  # Will be set by caller
            agent_name=agent_name,
            text=text,
            data=data,
        )
