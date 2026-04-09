import pytest

import app.config_store as config_store


@pytest.mark.asyncio
async def test_load_routes_creates_keys_for_all_methods(monkeypatch):
    class FakeCollection:
        def find(self):
            async def _iter():
                yield {
                    "tenant_id": "tenant-a",
                    "prefix": "/orders",
                    "target_base": "https://orders.local",
                    "methods": ["GET", "POST"],
                    "plugins": [],
                }

            return _iter()

    monkeypatch.setattr(config_store, "routes_collection", FakeCollection())

    await config_store.load_routes()

    assert "GET:/tenant-a/orders" in config_store._routes_cache
    assert "POST:/tenant-a/orders" in config_store._routes_cache


@pytest.mark.asyncio
async def test_load_routes_does_not_duplicate_tenant_when_prefix_already_contains_it(monkeypatch):
    class FakeCollection:
        def find(self):
            async def _iter():
                yield {
                    "tenant_id": "tiago.ventura-sandbox",
                    "prefix": "/tiago.ventura-sandbox/users/{id}",
                    "target_base": "https://users.local",
                    "methods": ["GET"],
                    "plugins": [],
                }

            return _iter()

    monkeypatch.setattr(config_store, "routes_collection", FakeCollection())

    await config_store.load_routes()

    assert "GET:/tiago.ventura-sandbox/users/{id}" in config_store._routes_cache
    assert "GET:/tiago.ventura-sandbox/tiago.ventura-sandbox/users/{id}" not in config_store._routes_cache


def test_match_route_considers_http_method(monkeypatch):
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/tenant-a/users/{id}": {"prefix": "/users/{id}", "methods": ["GET"]},
            "POST:/tenant-a/users/{id}": {"prefix": "/users/{id}", "methods": ["POST"]},
        },
    )

    get_route, _ = config_store.match_route("GET:/tenant-a/users/123")
    post_route, _ = config_store.match_route("POST:/tenant-a/users/123")
    delete_route, _ = config_store.match_route("DELETE:/tenant-a/users/123")

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
            "GET:/tenant-a/products": route,
            "POST:/tenant-a/products": route,
        },
    )

    routes = config_store.get_available_routes()

    assert len(routes) == 1
    assert routes[0]["methods"] == ["GET", "POST"]
    assert routes[0]["prefix"] == "/products"


def test_match_route_supports_regex_path_params(monkeypatch):
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/tiago.ventura-sandbox/ws/{cep:\\d{8}}/json/": {
                "prefix": "/ws/{cep:\\d{8}}/json/",
                "methods": ["GET"],
            },
        },
    )

    matched_route, matched_params = config_store.match_route("GET:/tiago.ventura-sandbox/ws/02001000/json/")
    not_matched_route, _ = config_store.match_route("GET:/tiago.ventura-sandbox/ws/abc/json/")

    assert matched_route is not None
    assert matched_params == {"cep": "02001000"}
    assert not_matched_route is None


def test_match_route_supports_simple_path_params_with_tenant_slug(monkeypatch):
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/tiago.ventura-sandbox/users/{id}": {
                "prefix": "/users/{id}",
                "methods": ["GET"],
            },
        },
    )

    matched, params = config_store.match_route("GET:/tiago.ventura-sandbox/users/1")

    assert matched is not None
    assert params == {"id": "1"}


def test_match_route_ignores_trailing_slash_in_template_paths(monkeypatch):
    monkeypatch.setattr(
        config_store,
        "_routes_cache",
        {
            "GET:/tenant-a/users/{id}": {
                "prefix": "/users/{id}",
                "methods": ["GET"],
            },
        },
    )

    matched, params = config_store.match_route("GET:/tenant-a/users/1/")

    assert matched is not None
    assert params == {"id": "1"}
