import pytest

import app.config_store as config_store


@pytest.mark.asyncio
async def test_load_routes_creates_keys_for_all_methods(monkeypatch):
    class FakeCollection:
        def find(self):
            async def _iter():
                yield {
                    "prefix": "/orders",
                    "target_base": "https://orders.local",
                    "methods": ["GET", "POST"],
                    "plugins": [],
                }

            return _iter()

    monkeypatch.setattr(config_store, "routes_collection", FakeCollection())

    await config_store.load_routes()

    assert "GET:/orders" in config_store._routes_cache
    assert "POST:/orders" in config_store._routes_cache


def test_match_route_considers_http_method(monkeypatch):
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/users/{id}": {"prefix": "/users/{id}", "methods": ["GET"]},
            "POST:/users/{id}": {"prefix": "/users/{id}", "methods": ["POST"]},
        },
    )

    get_route = config_store.match_route("GET:/users/123")
    post_route = config_store.match_route("POST:/users/123")
    delete_route = config_store.match_route("DELETE:/users/123")

    assert get_route["methods"] == ["GET"]
    assert post_route["methods"] == ["POST"]
    assert delete_route is None


def test_get_available_routes_deduplicates_same_route_for_multiple_methods(monkeypatch):
    route = {
        "prefix": "/products",
        "target_base": "https://catalog.local",
        "methods": ["GET", "POST"],
        "plugins": [],
    }
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/products": route,
            "POST:/products": route,
        },
    )

    routes = config_store.get_available_routes()

    assert len(routes) == 1
    assert routes[0]["methods"] == ["GET", "POST"]
    assert routes[0]["prefix"] == "/products"
