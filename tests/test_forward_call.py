from types import SimpleNamespace

import pytest

from app.main import foward_call


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"ok"):
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def read(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request_kwargs = None

    def request(self, **kwargs):
        self.request_kwargs = kwargs
        return self.response


@pytest.mark.asyncio
async def test_forward_call_passes_headers_and_returns_response(monkeypatch):
    response = FakeResponse(status=200, body=b"{\"ok\":true}")
    session = FakeSession(response)

    async def fake_get_session():
        return session

    monkeypatch.setattr("app.main.SessionManager.get_session", fake_get_session)

    context = SimpleNamespace(extra={"upstream_headers": {"authorization": "Bearer out"}})
    route = {"target_base": "https://upstream.local", "prefix": "/proxy"}
    scope = {"method": "GET"}

    result = await foward_call(
        scope=scope,
        path="/resource",
        route=route,
        context=context,
        request_body=b"",
    )

    assert result.status == 200
    assert result.body == b"{\"ok\":true}"
    assert session.request_kwargs["url"] == "https://upstream.local/resource"
    assert session.request_kwargs["headers"]["authorization"] == "Bearer out"
    assert context.response is response


@pytest.mark.asyncio
async def test_forward_call_does_not_set_context_response_for_non_200(monkeypatch):
    response = FakeResponse(status=502, body=b"bad gateway")
    session = FakeSession(response)

    async def fake_get_session():
        return session

    monkeypatch.setattr("app.main.SessionManager.get_session", fake_get_session)

    context = SimpleNamespace(extra={})
    route = {"target_base": "https://upstream.local", "prefix": "/proxy"}
    scope = {"method": "POST"}

    result = await foward_call(
        scope=scope,
        path="/resource",
        route=route,
        context=context,
        request_body=b"payload",
    )

    assert result.status == 502
    assert not hasattr(context, "response")


@pytest.mark.asyncio
async def test_forward_call_forwards_query_string(monkeypatch):
    response = FakeResponse(status=200, body=b"ok")
    session = FakeSession(response)

    async def fake_get_session():
        return session

    monkeypatch.setattr("app.main.SessionManager.get_session", fake_get_session)

    context = SimpleNamespace(extra={})
    route = {"target_base": "https://upstream.local", "prefix": "/proxy"}
    scope = {"method": "GET", "query_string": b"limit=10&offset=20"}

    await foward_call(
        scope=scope,
        path="/resource",
        route=route,
        context=context,
        request_body=b"",
    )

    assert session.request_kwargs["url"] == "https://upstream.local/resource?limit=10&offset=20"
