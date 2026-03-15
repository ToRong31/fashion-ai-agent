_ORDER_KEYWORDS = {"buy", "purchase", "checkout", "order", "add to cart", "cart", "thêm vào giỏ", "mua"}
_STYLIST_KEYWORDS = {"style", "recommend", "outfit", "wear", "suggest", "advice"}


def classify_intent(text: str) -> str:
    lower = text.lower()

    for keyword in _ORDER_KEYWORDS:
        if keyword in lower:
            return "order"

    for keyword in _STYLIST_KEYWORDS:
        if keyword in lower:
            return "stylist"

    return "search"
