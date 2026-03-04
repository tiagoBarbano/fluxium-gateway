from types import SimpleNamespace

import pytest

from app.plugins.retry import RetryPlugin


@pytest.mark.asyncio
async def test_retry_retries_on_status_then_succeeds(make_context):
    plugin = RetryPlugin()
    context = make_context(route={"prefix": "/test"})

    calls = {"n": 0}

    async def call_next():
        calls["n"] += 1
        if calls["n"] < 3:
            return SimpleNamespace(status=503)
        return SimpleNamespace(status=200)

    response = await plugin.around_request(
        context,
        call_next,
        {"attempts": 3, "retry_on": [503], "backoff_ms": 0},
    )

    assert response.status == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_retries_on_exception_then_raises(make_context):
    plugin = RetryPlugin()
    context = make_context(route={"prefix": "/test"})

    calls = {"n": 0}

    async def call_next():
        calls["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await plugin.around_request(
            context,
            call_next,
            {"attempts": 2, "backoff_ms": 0},
        )

    assert calls["n"] == 2
