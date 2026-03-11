from types import SimpleNamespace

from .base import BasePlugin
from .errors import CORSOriginNotAllowedError


class CORSPlugin(BasePlugin):
    name = "cors"
    phase = "forward"

    def _normalize_csv_or_list(self, value, default):
        if value is None:
            return list(default)
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return list(default)

    def _headers_map(self, context):
        return {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in context.scope.get("headers", [])
        }

    def _allow_origin(self, origin, allowed_origins):
        if "*" in allowed_origins:
            return "*"
        if origin in allowed_origins:
            return origin
        return None

    def _compose_headers(self, config, origin):
        allowed_origins = self._normalize_csv_or_list(config.get("allowed_origins"), ["*"])
        allowed_methods = self._normalize_csv_or_list(
            config.get("allowed_methods"),
            ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )
        allowed_headers = self._normalize_csv_or_list(
            config.get("allowed_headers"),
            ["authorization", "content-type", "x-api-key", "x-tenant-id"],
        )
        expose_headers = self._normalize_csv_or_list(config.get("expose_headers"), [])

        allowed_origin = self._allow_origin(origin, allowed_origins)
        if not allowed_origin and config.get("block_disallowed_origin", False):
            raise CORSOriginNotAllowedError()

        if not allowed_origin:
            return []

        headers = [
            ("access-control-allow-origin", allowed_origin),
            ("access-control-allow-methods", ", ".join(allowed_methods)),
            ("access-control-allow-headers", ", ".join(allowed_headers)),
            ("vary", "Origin"),
        ]

        if expose_headers:
            headers.append(("access-control-expose-headers", ", ".join(expose_headers)))

        if bool(config.get("allow_credentials", False)):
            headers.append(("access-control-allow-credentials", "true"))

        max_age = int(config.get("max_age", 600))
        if max_age > 0:
            headers.append(("access-control-max-age", str(max_age)))

        return headers

    def _merge_headers(self, base_headers, headers_to_add):
        current = list(base_headers or [])
        names_to_replace = {name.lower() for name, _ in headers_to_add}
        filtered = [(k, v) for k, v in current if k.lower() not in names_to_replace]
        filtered.extend(headers_to_add)
        return filtered

    async def around_request(self, context, call_next, config):
        headers = self._headers_map(context)
        origin = headers.get("origin")

        if not origin:
            return await call_next()

        cors_headers = self._compose_headers(config, origin)
        method = context.scope.get("method", "GET").upper()
        is_preflight = (
            method == "OPTIONS"
            and "access-control-request-method" in headers
        )

        if is_preflight:
            return SimpleNamespace(status=204, headers=cors_headers, body=b"")

        response = await call_next()
        response.headers = self._merge_headers(getattr(response, "headers", []), cors_headers)
        return response