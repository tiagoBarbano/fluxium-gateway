import json
from types import SimpleNamespace

import pytest

from app.plugins.event_bridge import EventBridgePlugin


class FakeRedis:
    def __init__(self):
        self.publish_calls = []
        self.xadd_calls = []

    async def publish(self, channel, payload):
        self.publish_calls.append((channel, payload))

    async def xadd(self, stream, payload):
        self.xadd_calls.append((stream, payload))
        return b"1732115636178-0"


@pytest.mark.asyncio
async def test_event_bridge_publish_returns_202_without_forward(monkeypatch, make_context):
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.plugins.event_bridge.redis_client", fake_redis)

    plugin = EventBridgePlugin()
    context = make_context(route={"prefix": "/events"}, method="POST")
    context.scope["path"] = "/events"
    context.scope["query_string"] = b"source=admin"
    context.extra["request_body"] = b'{"id": 10}'

    call_count = {"n": 0}

    async def call_next():
        call_count["n"] += 1
        return SimpleNamespace(status=200)

    response = await plugin.around_request(
        context,
        call_next,
        {"mode": "pubsub", "channel": "orders.events"},
    )

    assert response.status == 202
    assert call_count["n"] == 0
    assert fake_redis.publish_calls[0][0] == "orders.events"


@pytest.mark.asyncio
async def test_event_bridge_forward_after_publish(monkeypatch, make_context):
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.plugins.event_bridge.redis_client", fake_redis)

    plugin = EventBridgePlugin()
    context = make_context(route={"prefix": "/events"}, method="POST")
    context.scope["path"] = "/events"
    context.extra["request_body"] = b'{"id": 10}'

    async def call_next():
        return SimpleNamespace(status=201, headers=[], body=b"ok")

    response = await plugin.around_request(
        context,
        call_next,
        {
            "mode": "stream",
            "stream": "orders.stream",
            "forward_after_publish": True,
        },
    )

    assert response.status == 201
    assert fake_redis.xadd_calls[0][0] == "orders.stream"

    payload = json.loads(fake_redis.xadd_calls[0][1]["event"])
    assert payload["route"] == "/events"