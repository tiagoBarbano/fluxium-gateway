import pytest

from app.plugins.api_key import APIKeyAuthPlugin
from app.plugins.errors import APIKeyInvalidError, APIKeyMissingError


@pytest.mark.asyncio
async def test_api_key_auth_accepts_header_key(make_context):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {
                    "type": "api_key",
                    "order": 1,
                    "config": {"keys": ["valid-key"]},
                }
            ],
        },
        headers=[(b"x-api-key", b"valid-key")],
    )

    await plugin.before_request(context)

    assert context.extra["api_key_authenticated"] is True


@pytest.mark.asyncio
async def test_api_key_auth_accepts_query_key(make_context):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {
                    "type": "api_key",
                    "order": 1,
                    "config": {"keys": ["valid-key"]},
                }
            ],
        },
    )
    context.scope["query_string"] = b"api_key=valid-key"

    await plugin.before_request(context)

    assert context.extra["api_key_authenticated"] is True


@pytest.mark.asyncio
async def test_api_key_auth_raises_when_missing(make_context):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [{"type": "api_key", "order": 1, "config": {"keys": ["k1"]}}],
        }
    )

    with pytest.raises(APIKeyMissingError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_api_key_auth_raises_when_invalid(make_context):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [{"type": "api_key", "order": 1, "config": {"keys": ["k1"]}}],
        },
        headers=[(b"x-api-key", b"k2")],
    )

    with pytest.raises(APIKeyInvalidError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_api_key_resolves_consumer_from_collection(make_context, monkeypatch):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "tenant_id": "tenant-a",
            "plugins": [
                {
                    "type": "api_key",
                    "order": 1,
                    "config": {"keys": ["k1"], "resolve_consumer": True},
                }
            ],
        },
        headers=[(b"x-api-key", b"k1")],
    )

    class FakeCollection:
        async def find_one(self, query):
            assert query["tenant_id"] == "tenant-a"
            assert query["api_keys"] == "k1"
            return {
                "_id": "consumer-1",
                "name": "Consumer One",
                "actor_type": "application",
                "status": "active",
                "tags": ["vip"],
                "plan_override": "gold",
            }

    monkeypatch.setattr(APIKeyAuthPlugin, "_consumers_collection", FakeCollection())

    await plugin.before_request(context)

    assert context.extra["consumer_id"] == "consumer-1"
    assert context.extra["consumer_name"] == "Consumer One"
    assert context.extra["consumer_tags"] == ["vip"]
    assert context.extra["consumer_plan_override"] == "gold"


@pytest.mark.asyncio
async def test_api_key_raises_when_consumer_not_found_and_enforced(make_context, monkeypatch):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "tenant_id": "tenant-a",
            "plugins": [
                {
                    "type": "api_key",
                    "order": 1,
                    "config": {
                        "keys": ["k1"],
                        "resolve_consumer": True,
                        "enforce_consumer_resolution": True,
                    },
                }
            ],
        },
        headers=[(b"x-api-key", b"k1")],
    )

    class FakeCollection:
        async def find_one(self, query):
            return None

    monkeypatch.setattr(APIKeyAuthPlugin, "_consumers_collection", FakeCollection())

    with pytest.raises(APIKeyInvalidError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_api_key_auth_accepts_client_credentials_when_enabled(make_context, monkeypatch):
    plugin = APIKeyAuthPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "tenant_id": "tenant-a",
            "plugins": [
                {
                    "type": "api_key",
                    "order": 1,
                    "config": {
                        "allow_client_credentials": True,
                        "resolve_consumer": True,
                        "enforce_consumer_resolution": True,
                    },
                }
            ],
        },
        headers=[(b"x-client-id", b"client-a"), (b"x-secret-id", b"secret-a")],
    )

    class FakeCollection:
        async def find_one(self, query):
            assert query["client_id"] == "client-a"
            assert query["secret_id"] == "secret-a"
            return {
                "_id": "consumer-1",
                "name": "Consumer One",
                "client_id": "client-a",
                "actor_type": "application",
                "status": "active",
                "tags": ["vip"],
            }

    monkeypatch.setattr(APIKeyAuthPlugin, "_consumers_collection", FakeCollection())

    await plugin.before_request(context)

    assert context.extra["api_key_authenticated"] is True
    assert context.extra["consumer_id"] == "consumer-1"
    assert context.extra["consumer_client_id"] == "client-a"
