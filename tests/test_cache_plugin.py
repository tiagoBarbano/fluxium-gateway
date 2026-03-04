import base64
import json
from types import SimpleNamespace

import pytest

from app.plugins.cache import CachePlugin


class FakeRedis:
    def __init__(self, cached_value=None):
        self.cached_value = cached_value
        self.set_calls = []

    async def get(self, key):
        return self.cached_value

    async def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))


@pytest.mark.asyncio
async def test_cache_before_request_populates_cache_hit(monkeypatch):
    payload = {
        "status": 200,
        "headers": [["content-type", "application/json"]],
        "body": base64.b64encode(b"hello").decode(),
    }
    fake_redis = FakeRedis(cached_value=json.dumps(payload))
    monkeypatch.setattr("app.plugins.cache.redis_client", fake_redis)

    plugin = CachePlugin()
    context = SimpleNamespace(
        scope={"method": "GET", "path": "/x", "query_string": b""},
        tenant="tenant-a",
        route={"plugins": []},
        extra={},
    )

    await plugin.before_request(context)

    assert context.extra["cache_hit"]["status"] == 200
    assert context.extra["cache_hit"]["body"] == b"hello"


@pytest.mark.asyncio
async def test_cache_after_response_stores_payload(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.plugins.cache.redis_client", fake_redis)

    plugin = CachePlugin()
    context = SimpleNamespace(
        scope={"method": "GET", "path": "/x", "query_string": b""},
        tenant="tenant-a",
        route={
            "plugins": [
                {"type": "cache", "config": {"ttl_seconds": 60}},
            ]
        },
        extra={
            "response_data": {
                "status": 200,
                "headers": [("content-type", "application/json")],
                "body": b"{\"ok\": true}",
            }
        },
    )

    await plugin.after_response(context)

    assert len(fake_redis.set_calls) == 1
    _, raw_payload, ex = fake_redis.set_calls[0]
    parsed = json.loads(raw_payload)
    assert parsed["status"] == 200
    assert ex == 60
