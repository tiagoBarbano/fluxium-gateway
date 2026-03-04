from types import SimpleNamespace

import pytest

from app.plugins.forward_auth import ForwardAuthPlugin, TOKEN_CACHE


class FakeTokenResponse:
    def __init__(self, status=200, body=None):
        self.status = status
        self._body = body or {"access_token": "token-1", "expires_in": 300}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._body


class FakeSession:
    def __init__(self, tokens):
        self.tokens = tokens
        self.calls = 0

    def post(self, token_url, data=None, timeout=None):
        body = self.tokens[min(self.calls, len(self.tokens) - 1)]
        self.calls += 1
        return FakeTokenResponse(body=body)


@pytest.mark.asyncio
async def test_forward_auth_propagate_mode_copies_header(make_context, make_response):
    plugin = ForwardAuthPlugin()
    context = make_context(headers=[(b"authorization", b"Bearer in-token")])

    async def call_next():
        return make_response()

    response = await plugin.around_request(
        context,
        call_next,
        {"mode": "propagate", "source_header": "authorization", "target_header": "authorization"},
    )

    assert response.status == 200
    assert context.extra["upstream_headers"]["authorization"] == "Bearer in-token"


@pytest.mark.asyncio
async def test_forward_auth_static_mode_sets_fixed_token(make_context, make_response):
    plugin = ForwardAuthPlugin()
    context = make_context()

    async def call_next():
        return make_response()

    await plugin.around_request(
        context,
        call_next,
        {"mode": "static", "token": "abc", "scheme": "Bearer"},
    )

    assert context.extra["upstream_headers"]["authorization"] == "Bearer abc"


@pytest.mark.asyncio
async def test_forward_auth_oauth_mode_refreshes_on_401_for_get(monkeypatch, make_context, make_response):
    plugin = ForwardAuthPlugin()
    TOKEN_CACHE.clear()
    context = make_context(method="GET")

    fake_session = FakeSession(
        tokens=[
            {"access_token": "token-1", "expires_in": 300},
            {"access_token": "token-2", "expires_in": 300},
        ]
    )

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr("app.plugins.forward_auth.SessionManager.get_session", fake_get_session)

    calls = {"n": 0}

    async def call_next():
        calls["n"] += 1
        if calls["n"] == 1:
            return make_response(status=401)
        return make_response(status=200)

    response = await plugin.around_request(
        context,
        call_next,
        {
            "mode": "oauth2_client_credentials",
            "token_url": "https://idp/token",
            "client_id": "client",
            "client_secret": "secret",
            "refresh_on_401": True,
        },
    )

    assert response.status == 200
    assert calls["n"] == 2
    assert context.extra["upstream_headers"]["authorization"] == "Bearer token-2"


@pytest.mark.asyncio
async def test_forward_auth_oauth_mode_skips_retry_on_post(monkeypatch, make_context, make_response):
    plugin = ForwardAuthPlugin()
    TOKEN_CACHE.clear()
    context = make_context(method="POST")

    fake_session = FakeSession(tokens=[{"access_token": "token-1", "expires_in": 300}])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr("app.plugins.forward_auth.SessionManager.get_session", fake_get_session)

    calls = {"n": 0}

    async def call_next():
        calls["n"] += 1
        return make_response(status=401)

    response = await plugin.around_request(
        context,
        call_next,
        {
            "mode": "oauth2_client_credentials",
            "token_url": "https://idp/token",
            "client_id": "client",
            "client_secret": "secret",
            "refresh_on_401": True,
        },
    )

    assert response.status == 401
    assert calls["n"] == 1
