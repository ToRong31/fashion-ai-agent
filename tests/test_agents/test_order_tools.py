import pytest

from services.order.tools.create_order import CreateOrderTool
from services.order.tools.get_payment_link import GetPaymentLinkTool
from services.order.tools.search_products import SearchProductsTool


@pytest.mark.asyncio
async def test_create_order(mock_backend_client):
    tool = CreateOrderTool(mock_backend_client)
    result = await tool.execute({"user_id": 1, "product_ids": [1, 5]}, {})

    assert result["id"] == 1
    assert result["status"] == "created"
    mock_backend_client.auto_create_order.assert_called_once_with(1, [1, 5])


@pytest.mark.asyncio
async def test_get_payment_link(mock_backend_client):
    tool = GetPaymentLinkTool(mock_backend_client)
    result = await tool.execute({"order_id": 1}, {})

    assert "payment_url" in result
    assert "vnpayment" in result["payment_url"]
    mock_backend_client.get_payment_link.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_search_products(mock_backend_client):
    tool = SearchProductsTool(mock_backend_client)
    results = await tool.execute({"query": "black jacket"}, {})

    assert len(results) == 3
    mock_backend_client.vector_search.assert_called_once()
