import os

from .base import BasePlugin
from .errors import RequestSizeExceededError


class RequestSizePlugin(BasePlugin):
    name = "request_size"
    phase = "forward"

    def _plugin_config(self, config):
        default_max = int(os.getenv("GATEWAY_MAX_REQUEST_BYTES", "1048576"))
        max_bytes = int(config.get("max_bytes", default_max))
        return max(1, max_bytes)

    async def around_request(self, context, call_next, config):
        max_bytes = self._plugin_config(config)
        body = context.extra.get("request_body", b"") or b""
        size = len(body)

        if size > max_bytes:
            raise RequestSizeExceededError(
                f"Request payload {size} bytes exceeds max allowed {max_bytes} bytes"
            )

        context.extra["request_size_bytes"] = size
        return await call_next()
