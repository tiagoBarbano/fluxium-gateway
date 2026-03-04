import pytest

from app.plugins.engine import PluginEngine


class BeforeAfterPlugin:
    phase = "before_after"
    name = "before_after"

    def __init__(self, sink):
        self.sink = sink

    async def before_request(self, context):
        self.sink.append("before")

    async def after_response(self, context):
        self.sink.append("after")


class ForwardPlugin:
    phase = "forward"
    name = "forward"

    def __init__(self, sink):
        self.sink = sink

    async def around_request(self, context, call_next, config):
        self.sink.append(f"forward_before_{config.get('id')}")
        response = await call_next()
        self.sink.append(f"forward_after_{config.get('id')}")
        return response


@pytest.mark.asyncio
async def test_run_before_and_after_only_before_after_phase(make_context, make_response):
    sink = []
    engine = PluginEngine(
        {
            "p1": BeforeAfterPlugin(sink),
            "f1": ForwardPlugin(sink),
        }
    )
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {"type": "p1", "order": 1},
                {"type": "f1", "order": 2, "config": {"id": 1}},
            ],
        }
    )

    await engine.run_before(context)
    await engine.run_after(context)

    assert sink == ["before", "after"]


@pytest.mark.asyncio
async def test_run_forward_wraps_upstream_in_order(make_context, make_response):
    sink = []
    engine = PluginEngine(
        {
            "f1": ForwardPlugin(sink),
            "f2": ForwardPlugin(sink),
        }
    )
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {"type": "f1", "order": 1, "config": {"id": 1}},
                {"type": "f2", "order": 2, "config": {"id": 2}},
            ],
        }
    )

    async def call_upstream():
        sink.append("upstream")
        return make_response(status=200)

    response = await engine.run_forward(context, call_upstream)

    assert response.status == 200
    assert sink == [
        "forward_before_1",
        "forward_before_2",
        "upstream",
        "forward_after_2",
        "forward_after_1",
    ]
