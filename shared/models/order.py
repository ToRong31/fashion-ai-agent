from pydantic import BaseModel


class AutoCreateOrderRequest(BaseModel):
    user_id: int
    product_ids: list[int]


class Order(BaseModel):
    id: int
    user_id: int
    status: str
    total_amount: float
    vnpay_ref: str | None = None


class PaymentLink(BaseModel):
    order_id: int
    payment_url: str
