from types import SimpleNamespace

import pytest

from app.plugins.errors import JWTInvalidScopeError
from app.plugins.oauth import KeycloakOAuth2Plugin


@pytest.mark.asyncio
async def test_oauth_sets_context_fields_when_valid(monkeypatch):
    plugin = KeycloakOAuth2Plugin(
        issuer="https://idp.local/realms/x",
        audience="gateway-api",
        required_scopes=["pricing.read"],
    )

    class FakeKey:
        key = "public-key"

    payload = {
        "sub": "user-1",
        "azp": "client-a",
        "scope": "pricing.read other.scope",
        "realm_access": {"roles": ["admin"]},
        "resource_access": {"gateway-api": {"roles": ["writer"]}},
    }

    monkeypatch.setattr(plugin, "_get_signing_key", lambda token: FakeKey())
    monkeypatch.setattr("app.plugins.oauth.jwt.decode", lambda *args, **kwargs: payload)

    context = SimpleNamespace(
        scope={"headers": [(b"authorization", b"Bearer token")]} 
    )

    await plugin.before_request(context)

    assert context.user_id == "user-1"
    assert context.client_id == "client-a"
    assert "pricing.read" in context.scopes
    assert set(context.roles) == {"admin", "writer"}


@pytest.mark.asyncio
async def test_oauth_raises_when_required_scope_missing(monkeypatch):
    plugin = KeycloakOAuth2Plugin(
        issuer="https://idp.local/realms/x",
        audience="gateway-api",
        required_scopes=["pricing.read"],
    )

    class FakeKey:
        key = "public-key"

    payload = {"scope": "other.scope"}

    monkeypatch.setattr(plugin, "_get_signing_key", lambda token: FakeKey())
    monkeypatch.setattr("app.plugins.oauth.jwt.decode", lambda *args, **kwargs: payload)

    context = SimpleNamespace(
        scope={"headers": [(b"authorization", b"Bearer token")]} 
    )

    with pytest.raises(JWTInvalidScopeError):
        await plugin.before_request(context)
