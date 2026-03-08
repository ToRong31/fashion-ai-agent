import pytest

from agents.order.tools import OrderTools


@pytest.mark.asyncio
async def test_create_order(mock_backend_client):
    tools = OrderTools(mock_backend_client)
    result = await tools.create_order(user_id=1, product_ids=[1, 5])

    assert result["id"] == 1
    assert result["status"] == "created"
    mock_backend_client.auto_create_order.assert_called_once_with(1, [1, 5])


@pytest.mark.asyncio
async def test_get_payment_link(mock_backend_client):
    tools = OrderTools(mock_backend_client)
    result = await tools.get_payment_link(order_id=1)

    assert "payment_url" in result
    assert "vnpayment" in result["payment_url"]
    mock_backend_client.get_payment_link.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_search_products(mock_backend_client):
    tools = OrderTools(mock_backend_client)
    results = await tools.search_products("black jacket")

    assert len(results) == 3
    mock_backend_client.vector_search.assert_called_once()
