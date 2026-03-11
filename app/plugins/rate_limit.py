from .base import BasePlugin
from .errors import RateLimitExceededError
from app.rate_limit import check_rate_limit


class RateLimitPlugin(BasePlugin):
    name = "rate_limit"
    order = 2

    def _plugin_config(self, context):
        for plugin in context.route.get("plugins", []):
            if isinstance(plugin, dict) and plugin.get("type") == self.name:
                return plugin.get("config", {})
        return {}

    @staticmethod
    def _resolve_limit_config(base_config, consumer_id, consumer_tags):
        effective = {
            "limit": int(base_config.get("limit", 5)),
            "window_seconds": int(base_config.get("window_seconds", 60)),
        }

        consumer_limits = base_config.get("consumer_limits") or {}
        if consumer_id and isinstance(consumer_limits.get(consumer_id), dict):
            override = consumer_limits[consumer_id]
            if "limit" in override:
                effective["limit"] = int(override["limit"])
            if "window_seconds" in override:
                effective["window_seconds"] = int(override["window_seconds"])

        consumer_tag_limits = base_config.get("consumer_tag_limits") or {}
        for tag in consumer_tags:
            override = consumer_tag_limits.get(tag)
            if not isinstance(override, dict):
                continue
            if "limit" in override:
                effective["limit"] = int(override["limit"])
            if "window_seconds" in override:
                effective["window_seconds"] = int(override["window_seconds"])

        return effective

    async def before_request(self, context):
        config = self._plugin_config(context)

        by_consumer = bool(config.get("by_consumer", False))
        consumer_id = context.extra.get("consumer_id")
        consumer_tags = context.extra.get("consumer_tags") or []

        scope_value = context.tenant
        if by_consumer and consumer_id:
            scope_value = f"{context.tenant}:{consumer_id}"

        effective_config = self._resolve_limit_config(config, consumer_id, consumer_tags)
        allowed = await check_rate_limit(scope_value, effective_config, context.route["prefix"])
        if not allowed:
            if by_consumer and consumer_id:
                raise RateLimitExceededError(f"Consumer quota exceeded: {consumer_id}")
            raise RateLimitExceededError()