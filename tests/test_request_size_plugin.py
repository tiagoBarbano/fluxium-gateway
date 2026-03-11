import pytest

from app.plugins.errors import RequestSizeExceededError
from app.plugins.request_size import RequestSizePlugin


@pytest.mark.asyncio
async def test_request_size_allows_payload_within_limit(make_context, make_response):
    plugin = RequestSizePlugin()
    context = make_context()
    context.extra["request_body"] = b"hello"

    async def call_next():
        return make_response(status=200)

    response = await plugin.around_request(
        context,
        call_next,
        {"max_bytes": 10},
    )

    assert response.status == 200
    assert context.extra["request_size_bytes"] == 5


@pytest.mark.asyncio
async def test_request_size_blocks_payload_above_limit(make_context, make_response):
    plugin = RequestSizePlugin()
    context = make_context()
    context.extra["request_body"] = b"0123456789"

    async def call_next():
        return make_response(status=200)

    with pytest.raises(RequestSizeExceededError):
        await plugin.around_request(
            context,
            call_next,
            {"max_bytes": 5},
        )
