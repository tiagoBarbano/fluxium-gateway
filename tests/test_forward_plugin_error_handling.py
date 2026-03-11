import json

import pytest

import app.main as main_module
from app.plugins.errors import ValidationFailedError


async def _invoke_asgi(asgi_app, scope):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await asgi_app(scope, receive, send)
    return messages


@pytest.mark.asyncio
async def test_forward_plugin_error_returns_plugin_status(monkeypatch):
    monkeypatch.setattr("app.main.match_route", lambda key: {"prefix": "/x", "target_base": "http://up"})

    async def fake_run_before(context):
        return None

    async def fake_run_forward(context, call_upstream):
        raise ValidationFailedError("bad payload")

    async def fake_run_after(context):
        return None

    monkeypatch.setattr(main_module.plugins, "run_before", fake_run_before)
    monkeypatch.setattr(main_module.plugins, "run_forward", fake_run_forward)
    monkeypatch.setattr(main_module.plugins, "run_after", fake_run_after)

    asgi_app = main_module.app.app
    messages = await _invoke_asgi(
        asgi_app,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/x",
            "raw_path": b"/x",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
    )

    start = messages[0]
    body = messages[1]

    assert start["status"] == 400
    payload = json.loads(body["body"].decode())
    assert payload["code"] == "VALIDATION_FAILED"
