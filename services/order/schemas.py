from pydantic import BaseModel


class Product(BaseModel):
    id: int
    name: str
    description: str
    price: float
    stock_quantity: int
    metadata: dict | None = None


class Order(BaseModel):
    id: int
    user_id: int
    status: str
    total_amount: float
    vnpay_ref: str | None = None


class AutoCreateOrderRequest(BaseModel):
    user_id: int
    product_ids: list[int]


class PaymentLink(BaseModel):
    order_id: int
    payment_url: str
