import pytest

from app.plugins.cors import CORSPlugin
from app.plugins.errors import CORSOriginNotAllowedError


@pytest.mark.asyncio
async def test_cors_preflight_returns_204(make_context):
    plugin = CORSPlugin()
    context = make_context(
        method="OPTIONS",
        headers=[
            (b"origin", b"https://app.example.com"),
            (b"access-control-request-method", b"GET"),
        ],
    )

    response = await plugin.around_request(
        context,
        call_next=None,
        config={"allowed_origins": ["https://app.example.com"]},
    )

    assert response.status == 204
    headers = dict(response.headers)
    assert headers["access-control-allow-origin"] == "https://app.example.com"


@pytest.mark.asyncio
async def test_cors_adds_headers_to_upstream_response(make_context, make_response):
    plugin = CORSPlugin()
    context = make_context(
        method="GET",
        headers=[(b"origin", b"https://app.example.com")],
    )

    async def call_next():
        return make_response(status=200, headers=[("content-type", "application/json")])

    response = await plugin.around_request(
        context,
        call_next=call_next,
        config={"allowed_origins": ["https://app.example.com"]},
    )

    headers = dict(response.headers)
    assert response.status == 200
    assert headers["access-control-allow-origin"] == "https://app.example.com"
    assert headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_cors_blocks_origin_when_strict(make_context, make_response):
    plugin = CORSPlugin()
    context = make_context(
        method="GET",
        headers=[(b"origin", b"https://other.example.com")],
    )

    async def call_next():
        return make_response(status=200)

    with pytest.raises(CORSOriginNotAllowedError):
        await plugin.around_request(
            context,
            call_next=call_next,
            config={
                "allowed_origins": ["https://app.example.com"],
                "block_disallowed_origin": True,
            },
        )
