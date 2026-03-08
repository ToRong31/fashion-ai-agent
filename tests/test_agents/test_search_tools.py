import pytest

from agents.search.tools import SearchTools


@pytest.mark.asyncio
async def test_search_products_returns_results(mock_backend_client):
    tools = SearchTools(mock_backend_client)
    results = await tools.search_products("black jacket")

    assert len(results) == 3
    mock_backend_client.vector_search.assert_called_once_with("black jacket", 5)


@pytest.mark.asyncio
async def test_search_products_custom_top_k(mock_backend_client):
    tools = SearchTools(mock_backend_client)
    await tools.search_products("dress", top_k=10)

    mock_backend_client.vector_search.assert_called_once_with("dress", 10)


@pytest.mark.asyncio
async def test_search_products_propagates_error(mock_backend_client):
    mock_backend_client.vector_search.side_effect = Exception("Connection failed")
    tools = SearchTools(mock_backend_client)

    with pytest.raises(Exception, match="Connection failed"):
        await tools.search_products("jacket")
