from types import SimpleNamespace

import pytest

from app.plugins.circuit_breaker import CIRCUIT_BREAKER_STATE, CircuitBreakerPlugin


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold_and_short_circuits(make_context):
    CIRCUIT_BREAKER_STATE.clear()
    plugin = CircuitBreakerPlugin()
    context = make_context(route={"prefix": "/cb", "target_base": "http://up"})

    async def call_fails():
        raise RuntimeError("upstream failure")

    with pytest.raises(RuntimeError):
        await plugin.around_request(
            context,
            call_fails,
            {"failure_threshold": 2, "recovery_timeout_seconds": 60},
        )

    with pytest.raises(RuntimeError):
        await plugin.around_request(
            context,
            call_fails,
            {"failure_threshold": 2, "recovery_timeout_seconds": 60},
        )

    response = await plugin.around_request(
        context,
        call_fails,
        {"failure_threshold": 2, "recovery_timeout_seconds": 60},
    )

    assert response.status == 503


@pytest.mark.asyncio
async def test_circuit_breaker_resets_on_success(make_context):
    CIRCUIT_BREAKER_STATE.clear()
    plugin = CircuitBreakerPlugin()
    context = make_context(route={"prefix": "/cb", "target_base": "http://up"})

    async def call_error_response():
        return SimpleNamespace(status=500)

    async def call_success_response():
        return SimpleNamespace(status=200)

    await plugin.around_request(
        context,
        call_error_response,
        {"failure_threshold": 5, "recovery_timeout_seconds": 60},
    )

    response = await plugin.around_request(
        context,
        call_success_response,
        {"failure_threshold": 5, "recovery_timeout_seconds": 60},
    )

    key = "http://up:/cb"
    assert response.status == 200
    assert CIRCUIT_BREAKER_STATE[key]["failures"] == 0
