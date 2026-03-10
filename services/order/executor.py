import json
import uuid

import structlog
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Message, TextPart, DataPart
from openai import AsyncOpenAI

from agents.order.tools import OrderTools

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an order processing assistant for ToRoMe Store, a fashion clothing store.
Help users place orders, add items to cart, and get payment links.

IMPORTANT: You MUST use tools to fulfill requests. NEVER ask follow-up questions.

When a user wants to ADD TO CART:
1. Call search_products to find the product by name.
2. Call add_to_cart with the found product's id, name, and price.
3. Confirm what was added to the cart.

When a user wants to BUY/ORDER/CHECKOUT:
1. Call search_products to find the product by name.
2. Use create_order with the user's ID and the found product IDs.
3. Use get_payment_link to generate the VNPay payment link.
4. Present the order summary and payment link.

If the user_id is provided in brackets like [user_id=3], use that ID.
If not mentioned, default to user_id=1.
NEVER ask the user what they want — the task already tells you."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for clothing products to find their IDs and details",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product search query, e.g. 'black jeans', 'casual sneakers'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a product to the user's shopping cart. Use after searching to find the product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The product ID to add to cart",
                    },
                    "product_name": {
                        "type": "string",
                        "description": "The product name",
                    },
                    "price": {
                        "type": "number",
                        "description": "The product price",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add (default 1)",
                    },
                },
                "required": ["product_id", "product_name", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create a new order for a user with specified product IDs",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "The user's ID",
                    },
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of product IDs to include in the order",
                    },
                },
                "required": ["user_id", "product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payment_link",
            "description": "Generate a VNPay payment link for a created order",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "The order ID to generate the payment link for",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
]


class OrderAgentExecutor(AgentExecutor):
    def __init__(self, tools: OrderTools, openai_client: AsyncOpenAI, model: str):
        self._tools = tools
        self._openai = openai_client
        self._model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_text, user_id, product_ids = self._extract_params(context.message)
        is_cart = self._is_cart_intent(user_text)
        logger.info("order_agent_executing", query=user_text, user_id=user_id, is_cart_intent=is_cart)

        # Inject known context into the user message
        context_note = ""
        if user_id:
            context_note += f" [user_id={user_id}]"
        if product_ids:
            context_note += f" [product_ids={product_ids}]"

        messages: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text + context_note},
        ]

        order_result: dict = {}
        payment_result: dict = {}
        cart_result: dict = {}

        try:
            tool_was_called = False
            for iteration in range(8):  # max tool-call iterations
                response = await self._openai.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                choice = response.choices[0]
                messages.append(choice.message)

                if choice.finish_reason == "stop":
                    if iteration == 0 and not tool_was_called:
                        logger.warning("order_llm_skipped_tools")
                        # Fallback: directly search + create order
                        final_text = await self._direct_order_fallback(
                            user_text, user_id, product_ids, event_queue
                        )
                        return
                    break

                if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                    for tool_call in choice.message.tool_calls:
                        fn = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Error parsing arguments."})
                            continue
                        tool_was_called = True

                        if fn == "search_products":
                            result = await self._tools.search_products(args["query"])
                            logger.info("tool_search_products", count=len(result))
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

                        elif fn == "add_to_cart":
                            cart_item = {
                                "product_id": args["product_id"],
                                "product_name": args["product_name"],
                                "price": args["price"],
                                "quantity": args.get("quantity", 1),
                            }
                            cart_result = cart_item
                            logger.info("tool_add_to_cart", product_id=args["product_id"], name=args["product_name"])
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"status": "added", "item": cart_item}),
                            })

                        elif fn == "create_order":
                            result = await self._tools.create_order(
                                user_id=args["user_id"],
                                product_ids=args["product_ids"],
                            )
                            order_result = result
                            logger.info("tool_create_order", order_id=result.get("id"))
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

                        elif fn == "get_payment_link":
                            result = await self._tools.get_payment_link(args["order_id"])
                            payment_result = result
                            logger.info("tool_get_payment_link", order_id=args["order_id"])
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            })

            final_text = self._extract_final_text(messages)
            data: dict = {}
            if cart_result:
                data["action"] = "add_to_cart"
                data["cart_item"] = cart_result
            if order_result:
                data["order"] = order_result
                data["payment_url"] = payment_result.get("payment_url", "")

            parts = [TextPart(text=final_text)]
            if data:
                parts.append(DataPart(data=data))
            await event_queue.enqueue_event(
                Message(
                    role="agent",
                    messageId=str(uuid.uuid4()),
                    parts=parts,
                )
            )
        except Exception as e:
            logger.error("order_agent_failed", error=str(e))
            await event_queue.enqueue_event(
                Message(
                    role="agent",
                    messageId=str(uuid.uuid4()),
                    parts=[TextPart(text=f"Order processing failed: {str(e)}")],
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        pass

    def _extract_params(self, message: Message | None) -> tuple[str, str | None, list[int]]:
        query = ""
        user_id = None
        product_ids: list[int] = []

        if not message:
            return query, user_id, product_ids

        for part in message.parts:
            pv = part.root if hasattr(part, "root") else part
            if hasattr(pv, "text") and pv.text:
                query = pv.text
            if hasattr(pv, "data") and isinstance(pv.data, dict):
                query = pv.data.get("query", query)
                user_id = pv.data.get("user_id")
                if "product_ids" in pv.data:
                    product_ids = pv.data["product_ids"]

        return query, str(user_id) if user_id else None, product_ids

    def _extract_final_text(self, messages: list) -> str:
        for m in reversed(messages):
            if hasattr(m, "role") and m.role == "assistant" and m.content:
                return m.content
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                return m["content"]
        return "Order processed."

    @staticmethod
    def _is_cart_intent(text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in [
            "add to cart", "add to my cart", "to their cart", "to the cart",
            "into cart", "into the cart", "cart",
            "thêm vào giỏ", "bỏ vào giỏ",
        ])

    @staticmethod
    def _extract_product_query(text: str) -> str:
        """Extract the product name from a user request like 'add Casual Denim Jacket to my cart'."""
        t = text
        # Strip context annotations
        import re
        t = re.sub(r'\[user_id=\d+\]', '', t).strip()
        # Remove cart/order keywords to get the product name
        for phrase in ["add to my cart", "add to cart", "thêm vào giỏ hàng", "thêm vào giỏ", "bỏ vào giỏ"]:
            t = t.lower().replace(phrase, "")
        # Remove leading "add " if present
        t = re.sub(r'^add\s+', '', t.strip(), flags=re.IGNORECASE)
        return t.strip() or text

    async def _direct_order_fallback(
        self, user_text: str, user_id: str | None, product_ids: list[int], event_queue: EventQueue
    ):
        """Fallback when LLM skips tools: directly search + add to cart or create order."""
        logger.info("direct_order_fallback", text=user_text[:100])

        if self._is_cart_intent(user_text):
            return await self._direct_cart_fallback(user_text, event_queue)

        # Order fallback: search → create order
        query = self._extract_product_query(user_text)
        try:
            products = await self._tools.search_products(query)
            if not products:
                await event_queue.enqueue_event(
                    Message(role="agent", messageId=str(uuid.uuid4()),
                            parts=[TextPart(text=f"No products found matching '{query}'.")])
                )
                return

            uid = int(user_id) if user_id else 1
            pids = product_ids or [products[0]["id"]]
            order = await self._tools.create_order(uid, pids)
            payment = await self._tools.get_payment_link(order["id"])

            items_text = ", ".join(p["name"] for p in products if p["id"] in pids)
            text = f"✅ Order created!\n\n**Items:** {items_text}\n**Total:** ${order.get('total_amount', 0)}\n**Payment link:** {payment.get('payment_url', 'N/A')}"

            await event_queue.enqueue_event(
                Message(role="agent", messageId=str(uuid.uuid4()),
                        parts=[TextPart(text=text), DataPart(data={"order": order, "payment_url": payment.get("payment_url", "")})])
            )
        except Exception as e:
            logger.error("direct_order_fallback_failed", error=str(e))
            await event_queue.enqueue_event(
                Message(role="agent", messageId=str(uuid.uuid4()),
                        parts=[TextPart(text=f"Order failed: {str(e)}")])
            )

    async def _direct_cart_fallback(self, user_text: str, event_queue: EventQueue):
        """Fallback for add-to-cart when LLM skips tools."""
        query = self._extract_product_query(user_text)
        logger.info("direct_cart_fallback", query=query)

        try:
            products = await self._tools.search_products(query)
            if not products:
                await event_queue.enqueue_event(
                    Message(role="agent", messageId=str(uuid.uuid4()),
                            parts=[TextPart(text=f"No products found matching '{query}'.")])
                )
                return

            product = products[0]
            cart_item = {
                "product_id": product["id"],
                "product_name": product["name"],
                "price": product.get("price", 0),
                "quantity": 1,
            }
            text = f"✅ Added **{product['name']}** (${product.get('price', 0)}) to your cart!"
            await event_queue.enqueue_event(
                Message(role="agent", messageId=str(uuid.uuid4()),
                        parts=[
                            TextPart(text=text),
                            DataPart(data={"action": "add_to_cart", "cart_item": cart_item}),
                        ])
            )
        except Exception as e:
            logger.error("direct_cart_fallback_failed", error=str(e))
            await event_queue.enqueue_event(
                Message(role="agent", messageId=str(uuid.uuid4()),
                        parts=[TextPart(text=f"Failed to add to cart: {str(e)}")])
            )
