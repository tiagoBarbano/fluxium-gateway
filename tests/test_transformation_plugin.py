import json

import pytest

from app.plugins.transformation import TransformationPlugin


@pytest.mark.asyncio
async def test_transformation_plugin_updates_headers_and_body(make_context):
    plugin = TransformationPlugin()
    context = make_context(method="POST")
    context.extra["request_body"] = b'{"old_name": "ana", "secret": "x"}'
    context.extra["upstream_headers"] = {"authorization": "Bearer token"}

    async def call_next():
        return "ok"

    result = await plugin.around_request(
        context,
        call_next,
        {
            "set_headers": {"x-origin": "gateway"},
            "remove_headers": ["authorization"],
            "json_rename": {"old_name": "name"},
            "json_defaults": {"source": "gateway"},
            "json_remove": ["secret"],
        },
    )

    transformed = json.loads(context.extra["request_body"].decode("utf-8"))
    assert result == "ok"
    assert transformed == {"name": "ana", "source": "gateway"}
    assert "authorization" not in context.extra["upstream_headers"]
    assert context.extra["upstream_headers"]["x-origin"] == "gateway"
    assert context.extra["upstream_headers"]["content-type"] == "application/json"