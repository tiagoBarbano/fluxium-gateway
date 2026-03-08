import json

import pytest

import app.main as main_module


async def _invoke_asgi(asgi_app, scope):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await asgi_app(scope, receive, send)
    return messages


@pytest.mark.asyncio
async def test_get_routes_returns_routes_list(monkeypatch):
    monkeypatch.setattr(
        "app.main.get_available_routes",
        lambda: [
            {
                "prefix": "/ws/{cep}/json/",
                "target_base": "https://viacep.com.br",
                "methods": ["GET", "POST"],
            }
        ],
    )

    asgi_app = main_module.app.app
    messages = await _invoke_asgi(
        asgi_app,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/routes",
            "raw_path": b"/routes",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
    )

    start = messages[0]
    body = messages[1]

    assert start["status"] == 200
    payload = json.loads(body["body"].decode())
    assert payload["routes"][0]["prefix"] == "/ws/{cep}/json/"
    assert payload["route_patterns"] == ["GET /ws/{cep}/json/", "POST /ws/{cep}/json/"]


@pytest.mark.asyncio
async def test_routes_rejects_non_get_methods():
    asgi_app = main_module.app.app
    messages = await _invoke_asgi(
        asgi_app,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/routes",
            "raw_path": b"/routes",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
    )

    start = messages[0]
    headers = dict(start["headers"])

    assert start["status"] == 405
    assert headers[b"allow"] == b"GET"
