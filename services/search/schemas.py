from pydantic import BaseModel


class Product(BaseModel):
    id: int
    name: str
    description: str
    price: float
    stock_quantity: int
    metadata: dict | None = None


class VectorSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class VectorSearchResponse(BaseModel):
    products: list[Product]
