import json
import os
from types import SimpleNamespace
from urllib.parse import parse_qs

import redis.asyncio as redis
from redis.exceptions import RedisError

from .base import BasePlugin
from .errors import EventBridgePublishError


redis_url = os.getenv("REDIS_URL", "redis://:redis1234@localhost:6379/0")
redis_client = redis.from_url(redis_url)


class EventBridgePlugin(BasePlugin):
    name = "event_bridge"
    phase = "forward"

    def _scope_headers(self, context):
        raw_headers = context.scope.get("headers", [])
        return {k.decode().lower(): v.decode() for k, v in raw_headers}

    def _scope_query(self, context):
        query_string = context.scope.get("query_string", b"")
        parsed = parse_qs(query_string.decode("latin-1"), keep_blank_values=True)
        return {k: values[-1] for k, values in parsed.items()}

    def _body_as_json_or_text(self, context):
        body_bytes = context.extra.get("request_body", b"")
        if not body_bytes:
            return None

        try:
            body_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return body_bytes.decode("latin-1")

        try:
            return json.loads(body_text)
        except json.JSONDecodeError:
            return body_text

    async def around_request(self, context, call_next, config):
        include_headers = bool(config.get("include_headers", False))
        payload = {
            "tenant": context.tenant,
            "route": context.route.get("prefix"),
            "method": context.scope.get("method", "GET"),
            "path": context.scope.get("path", ""),
            "query": self._scope_query(context),
            "body": self._body_as_json_or_text(context),
            "metadata": config.get("event", {}),
        }
        if include_headers:
            payload["headers"] = self._scope_headers(context)

        payload_json = json.dumps(payload)
        mode = str(config.get("mode", "pubsub")).lower()

        try:
            if mode == "stream":
                stream_key = config.get("stream", "gateway.events")
                message_id = await redis_client.xadd(stream_key, {"event": payload_json})
                destination = stream_key
            else:
                channel = config.get("channel", "gateway.events")
                await redis_client.publish(channel, payload_json)
                destination = channel
                message_id = None
        except RedisError as exc:
            raise EventBridgePublishError() from exc

        context.extra["event_bridge"] = {
            "mode": mode,
            "destination": destination,
            "message_id": message_id,
        }

        if bool(config.get("forward_after_publish", False)):
            return await call_next()

        response_status = int(config.get("response_status", 202))
        body = {
            "code": "EVENT_PUBLISHED",
            "description": "Event published successfully",
            "destination": destination,
        }
        if message_id is not None:
            body["message_id"] = message_id.decode("utf-8")

        return SimpleNamespace(
            status=response_status,
            headers=[("content-type", "application/json")],
            body=json.dumps(body).encode("utf-8"),
        )