import pytest
from unittest.mock import AsyncMock

from shared.backend_client import BackendClient
from mock_backend.seed_data import PRODUCTS, USERS


@pytest.fixture
def mock_backend_client():
    client = AsyncMock(spec=BackendClient)
    client.vector_search.return_value = {"products": PRODUCTS[:3]}
    client.get_products.return_value = {"products": PRODUCTS}
    client.get_product.return_value = PRODUCTS[0]
    client.get_user.return_value = {
        "id": USERS[0]["id"],
        "username": USERS[0]["username"],
        "preferences": USERS[0]["preferences"],
    }
    client.auto_create_order.return_value = {
        "id": 1,
        "user_id": 1,
        "status": "created",
        "total_amount": 159.98,
        "items": [
            {"product_id": 1, "name": "Classic Black Blazer", "price": 89.99},
            {"product_id": 5, "name": "Casual Denim Jacket", "price": 69.99},
        ],
        "vnpay_ref": "VNPAY-1",
    }
    client.get_payment_link.return_value = {
        "order_id": 1,
        "payment_url": "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?orderId=1&amount=159.98",
    }
    return client
