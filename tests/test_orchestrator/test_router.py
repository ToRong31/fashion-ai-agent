from agents.orchestrator.router import classify_intent


def test_search_intent_find():
    assert classify_intent("find me a black jacket") == "search"


def test_search_intent_show():
    assert classify_intent("show me casual shirts") == "search"


def test_search_intent_browse():
    assert classify_intent("browse summer dresses") == "search"


def test_stylist_intent_style():
    assert classify_intent("style me an outfit for winter") == "stylist"


def test_stylist_intent_recommend():
    assert classify_intent("recommend something to wear") == "stylist"


def test_stylist_intent_outfit():
    assert classify_intent("I need an outfit for a meeting") == "stylist"


def test_order_intent_buy():
    assert classify_intent("I want to buy this jacket") == "order"


def test_order_intent_purchase():
    assert classify_intent("purchase product 5") == "order"


def test_order_intent_checkout():
    assert classify_intent("checkout my cart") == "order"


def test_default_to_search():
    assert classify_intent("hello") == "search"


def test_empty_input():
    assert classify_intent("") == "search"
