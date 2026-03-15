import pytest

from services.search.tools.search_products import SearchProductsTool


@pytest.mark.asyncio
async def test_search_products_returns_results(mock_backend_client):
    tool = SearchProductsTool(mock_backend_client)
    results = await tool.execute({"query": "black jacket", "top_k": 5}, {})

    assert len(results) == 3
    mock_backend_client.vector_search.assert_called_once_with("black jacket", 5)


@pytest.mark.asyncio
async def test_search_products_custom_top_k(mock_backend_client):
    tool = SearchProductsTool(mock_backend_client)
    await tool.execute({"query": "dress", "top_k": 10}, {})

    mock_backend_client.vector_search.assert_called_once_with("dress", 10)


@pytest.mark.asyncio
async def test_search_products_propagates_error(mock_backend_client):
    mock_backend_client.vector_search.side_effect = Exception("Connection failed")
    tool = SearchProductsTool(mock_backend_client)

    with pytest.raises(Exception, match="Connection failed"):
        await tool.execute({"query": "jacket"}, {})
