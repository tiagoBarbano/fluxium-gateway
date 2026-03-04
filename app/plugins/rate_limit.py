from .base import BasePlugin
from .errors import RateLimitExceededError
from app.rate_limit import check_rate_limit

class RateLimitPlugin(BasePlugin):
    name = "rate_limit"
    order = 2

    async def before_request(self, context):
        plugin_config = context.route.get("plugins", [])

        for plugin in plugin_config:
            if plugin["type"] == self.name:
                config = plugin.get("config", {})

        allowed = await check_rate_limit(context.tenant, config, context.route["prefix"])
        if not allowed:
            raise RateLimitExceededError()