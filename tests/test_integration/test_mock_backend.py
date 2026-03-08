import pytest
from httpx import ASGITransport, AsyncClient

from mock_backend.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_products():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert len(data["products"]) > 0


@pytest.mark.asyncio
async def test_vector_search():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/products/vector-search",
            json={"query": "black jacket", "top_k": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert len(data["products"]) <= 3


@pytest.mark.asyncio
async def test_get_product():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/products/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1


@pytest.mark.asyncio
async def test_get_product_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/products/9999")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/users/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert "preferences" in data


@pytest.mark.asyncio
async def test_auto_create_order():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/orders/auto-create",
            json={"user_id": 1, "product_ids": [1, 2]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["total_amount"] > 0
        assert len(data["items"]) == 2
