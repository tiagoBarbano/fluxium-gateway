import base64
import hashlib
import json
import os

import redis.asyncio as redis
from redis.exceptions import RedisError

from .base import BasePlugin
from .errors import CacheBackendUnavailableError

redis_url = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379",
)

redis_client = redis.from_url(redis_url)

default_ttl_seconds = int(os.getenv("CACHE_TTL_SECONDS", "30"))
max_cache_body_bytes = int(os.getenv("CACHE_MAX_BODY_BYTES", "1048576"))


def _cache_key(context) -> str:
    method = context.scope.get("method", "GET")
    path = context.scope.get("path", "")
    query_string = context.scope.get("query_string", b"").decode()
    tenant = context.tenant or "anonymous"
    raw = f"{tenant}:{method}:{path}?{query_string}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return f"cache:{key_hash}"


class CachePlugin(BasePlugin):
    name = "cache"
    order = 10

    def _plugin_config(self, context):
        plugin_config = context.route.get("plugins", [])

        for plugin in plugin_config:
            if isinstance(plugin, dict) and plugin.get("type") == self.name:
                return plugin.get("config", {})

        return context.route.get("cache", {})

    async def before_request(self, context):
        if context.scope.get("method") != "GET":
            return

        key = _cache_key(context)
        try:
            cached = await redis_client.get(key)
        except RedisError as exc:
            raise CacheBackendUnavailableError() from exc

        if not cached:
            return

        payload = json.loads(cached)
        context.extra["cache_key"] = key
        context.extra["cache_hit"] = {
            "status": int(payload["status"]),
            "headers": [
                (k.encode(), v.encode())
                for k, v in payload.get("headers", [])
            ],
            "body": base64.b64decode(payload.get("body", "")),
        }

    async def after_response(self, context):
        if context.scope.get("method") != "GET":
            return

        if context.extra.get("cache_hit"):
            return

        cache_cfg = self._plugin_config(context)

        response_data = context.extra.get("response_data")
        if not response_data:
            return

        if int(response_data.get("status", 500)) != 200:
            return

        body = response_data.get("body", b"")
        if len(body) > max_cache_body_bytes:
            return

        ttl_seconds = int(cache_cfg.get("ttl_seconds", default_ttl_seconds))
        if ttl_seconds <= 0:
            return

        payload = {
            "status": int(response_data["status"]),
            "headers": response_data.get("headers", []),
            "body": base64.b64encode(body).decode(),
        }

        key = context.extra.get("cache_key") or _cache_key(context)
        try:
            await redis_client.set(key, json.dumps(payload), ex=ttl_seconds)
        except RedisError as exc:
            raise CacheBackendUnavailableError() from exc
