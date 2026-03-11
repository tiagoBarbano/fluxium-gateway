import pytest

from app.plugins.errors import IPRestrictionForbiddenError
from app.plugins.ip_restriction import IPRestrictionPlugin


@pytest.mark.asyncio
async def test_ip_restriction_allows_client_ip_in_allowlist(make_context):
    plugin = IPRestrictionPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {
                    "type": "ip_restriction",
                    "config": {"allowlist": ["10.0.0.0/8"]},
                }
            ],
        }
    )
    context.scope["client"] = ("10.1.2.3", 12345)

    await plugin.before_request(context)


@pytest.mark.asyncio
async def test_ip_restriction_denies_client_ip_in_denylist(make_context):
    plugin = IPRestrictionPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {
                    "type": "ip_restriction",
                    "config": {"denylist": ["10.1.2.3"]},
                }
            ],
        }
    )
    context.scope["client"] = ("10.1.2.3", 12345)

    with pytest.raises(IPRestrictionForbiddenError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_ip_restriction_uses_x_forwarded_for_when_configured(make_context):
    plugin = IPRestrictionPlugin()
    context = make_context(
        route={
            "prefix": "/test",
            "plugins": [
                {
                    "type": "ip_restriction",
                    "config": {
                        "source": "x-forwarded-for",
                        "allowlist": ["192.168.1.0/24"],
                    },
                }
            ],
        },
        headers=[(b"x-forwarded-for", b"192.168.1.45, 10.0.0.1")],
    )

    await plugin.before_request(context)
