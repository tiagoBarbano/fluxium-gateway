from types import SimpleNamespace

import pytest

from app.plugins.errors import RateLimitExceededError
from app.plugins.rate_limit import RateLimitPlugin


@pytest.mark.asyncio
async def test_rate_limit_allows_request(monkeypatch):
    plugin = RateLimitPlugin()
    context = SimpleNamespace(
        tenant="tenant-a",
        route={
            "prefix": "/api",
            "plugins": [
                {
                    "type": "rate_limit",
                    "config": {"limit": 5, "window_seconds": 60},
                }
            ],
        },
    )

    async def fake_check_rate_limit(tenant, config, prefix):
        assert tenant == "tenant-a"
        assert config == {"limit": 5, "window_seconds": 60}
        assert prefix == "/api"
        return True

    monkeypatch.setattr("app.plugins.rate_limit.check_rate_limit", fake_check_rate_limit)

    await plugin.before_request(context)


@pytest.mark.asyncio
async def test_rate_limit_blocks_request(monkeypatch):
    plugin = RateLimitPlugin()
    context = SimpleNamespace(
        tenant="tenant-a",
        route={
            "prefix": "/api",
            "plugins": [
                {
                    "type": "rate_limit",
                    "config": {"limit": 5, "window_seconds": 60},
                }
            ],
        },
    )

    async def fake_check_rate_limit(tenant, config, prefix):
        return False

    monkeypatch.setattr("app.plugins.rate_limit.check_rate_limit", fake_check_rate_limit)

    with pytest.raises(RateLimitExceededError):
        await plugin.before_request(context)
