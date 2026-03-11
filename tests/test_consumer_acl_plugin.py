from types import SimpleNamespace

import pytest

from app.plugins.consumer_acl import ConsumerACLPlugin
from app.plugins.errors import ConsumerACLForbiddenError, ConsumerNotResolvedError


@pytest.mark.asyncio
async def test_consumer_acl_denies_when_consumer_missing():
    plugin = ConsumerACLPlugin()
    context = SimpleNamespace(
        extra={},
        route={
            "plugins": [
                {
                    "type": "consumer_acl",
                    "config": {"allow_anonymous": False},
                }
            ]
        },
    )

    with pytest.raises(ConsumerNotResolvedError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_consumer_acl_allows_by_tag():
    plugin = ConsumerACLPlugin()
    context = SimpleNamespace(
        extra={
            "consumer_id": "consumer-1",
            "consumer_tags": ["vip"],
            "consumer_actor_type": "application",
        },
        route={
            "plugins": [
                {
                    "type": "consumer_acl",
                    "config": {
                        "allow_tags": ["vip"],
                        "required_actor_types": ["application"],
                    },
                }
            ]
        },
    )

    await plugin.before_request(context)
    assert context.extra["consumer_acl_passed"] is True


@pytest.mark.asyncio
async def test_consumer_acl_denies_by_consumer_id():
    plugin = ConsumerACLPlugin()
    context = SimpleNamespace(
        extra={
            "consumer_id": "consumer-1",
            "consumer_tags": ["vip"],
            "consumer_actor_type": "application",
        },
        route={
            "plugins": [
                {
                    "type": "consumer_acl",
                    "config": {
                        "deny_consumer_ids": ["consumer-1"],
                    },
                }
            ]
        },
    )

    with pytest.raises(ConsumerACLForbiddenError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_consumer_acl_denies_when_no_permission_found(monkeypatch):
    plugin = ConsumerACLPlugin()
    context = SimpleNamespace(
        tenant="tenant-a",
        scope={"method": "GET"},
        extra={
            "consumer_id": "consumer-1",
            "consumer_tags": ["vip"],
            "consumer_actor_type": "application",
        },
        route={
            "_id": "route-1",
            "api_id": "api-1",
            "tenant_id": "tenant-a",
            "plugins": [
                {
                    "type": "consumer_acl",
                    "config": {
                        "enforce_permissions": True,
                    },
                }
            ],
        },
    )

    class FakeCursor:
        def __aiter__(self):
            self._iter = iter([])
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCollection:
        def find(self, query):
            return FakeCursor()

    monkeypatch.setattr(ConsumerACLPlugin, "_permissions_collection", FakeCollection())

    with pytest.raises(ConsumerACLForbiddenError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_consumer_acl_allows_when_permission_matches(monkeypatch):
    plugin = ConsumerACLPlugin()
    context = SimpleNamespace(
        tenant="tenant-a",
        scope={"method": "POST"},
        extra={
            "consumer_id": "consumer-1",
            "consumer_tags": ["vip"],
            "consumer_actor_type": "application",
        },
        route={
            "_id": "route-1",
            "api_id": "api-1",
            "tenant_id": "tenant-a",
            "plugins": [
                {
                    "type": "consumer_acl",
                    "config": {
                        "enforce_permissions": True,
                    },
                }
            ],
        },
    )

    class FakeCursor:
        def __init__(self, items):
            self._items = items

        def __aiter__(self):
            self._iter = iter(self._items)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCollection:
        def find(self, query):
            return FakeCursor(
                [
                    {
                        "tenant_id": "tenant-a",
                        "consumer_id": "consumer-1",
                        "route_id": "route-1",
                        "api_id": "api-1",
                        "methods": ["POST"],
                    }
                ]
            )

    monkeypatch.setattr(ConsumerACLPlugin, "_permissions_collection", FakeCollection())

    await plugin.before_request(context)
    assert context.extra["consumer_acl_passed"] is True
