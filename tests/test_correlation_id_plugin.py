import pytest

from app.plugins.correlation_id import CorrelationIdPlugin


@pytest.mark.asyncio
async def test_correlation_id_propagates_existing_header(make_context, make_response):
    plugin = CorrelationIdPlugin()
    context = make_context(headers=[(b"x-request-id", b"abc-123")])

    async def call_next():
        return make_response(status=200, headers=[("content-type", "application/json")])

    response = await plugin.around_request(context, call_next, {})

    assert context.extra["request_id"] == "abc-123"
    assert context.extra["upstream_headers"]["x-request-id"] == "abc-123"
    assert dict(response.headers)["x-request-id"] == "abc-123"


@pytest.mark.asyncio
async def test_correlation_id_generates_when_missing(make_context, make_response):
    plugin = CorrelationIdPlugin()
    context = make_context(headers=[])

    async def call_next():
        return make_response(status=200, headers=[])

    response = await plugin.around_request(context, call_next, {})

    request_id = context.extra["request_id"]
    assert isinstance(request_id, str)
    assert len(request_id) > 0
    assert dict(response.headers)["x-request-id"] == request_id
