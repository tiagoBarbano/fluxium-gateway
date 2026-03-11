from uuid import uuid4

from .base import BasePlugin


class CorrelationIdPlugin(BasePlugin):
    name = "correlation_id"
    phase = "forward"

    def _headers_map(self, context):
        return {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in context.scope.get("headers", [])
        }

    def _merge_headers(self, base_headers, headers_to_add):
        current = list(base_headers or [])
        names_to_replace = {name.lower() for name, _ in headers_to_add}
        filtered = [(k, v) for k, v in current if k.lower() not in names_to_replace]
        filtered.extend(headers_to_add)
        return filtered

    async def around_request(self, context, call_next, config):
        incoming_header = str(config.get("incoming_header", "x-request-id")).lower()
        upstream_header = str(config.get("upstream_header", incoming_header)).lower()
        response_header = str(config.get("response_header", incoming_header)).lower()

        headers = self._headers_map(context)
        request_id = headers.get(incoming_header) or uuid4().hex

        context.extra["request_id"] = request_id
        upstream_headers = context.extra.setdefault("upstream_headers", {})
        upstream_headers[upstream_header] = request_id

        response = await call_next()
        response.headers = self._merge_headers(
            getattr(response, "headers", []),
            [(response_header, request_id)],
        )
        return response
