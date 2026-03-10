import pytest

from app.plugins.errors import ValidationFailedError
from app.plugins.validation import ValidationPlugin


@pytest.mark.asyncio
async def test_validation_plugin_allows_valid_request(make_context):
    plugin = ValidationPlugin()
    context = make_context(
        route={"prefix": "/orders"},
        headers=[(b"x-source", b"portal")],
        method="POST",
    )
    context.scope["query_string"] = b"version=v1"
    context.extra["request_body"] = b'{"order_id": "123"}'

    async def call_next():
        return "ok"

    result = await plugin.around_request(
        context,
        call_next,
        {
            "allowed_methods": ["POST"],
            "required_fields": ["order_id"],
            "header_rules": [{"name": "x-source", "required": True, "equals": "portal"}],
            "query_rules": [{"name": "version", "required": True, "equals": "v1"}],
        },
    )

    assert result == "ok"


@pytest.mark.asyncio
async def test_validation_plugin_rejects_missing_required_field(make_context):
    plugin = ValidationPlugin()
    context = make_context(method="POST")
    context.extra["request_body"] = b'{"customer_id": "123"}'

    async def call_next():
        return "ok"

    with pytest.raises(ValidationFailedError, match="Missing required field: order_id"):
        await plugin.around_request(
            context,
            call_next,
            {"required_fields": ["order_id"]},
        )