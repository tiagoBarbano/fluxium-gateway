import json

from .base import BasePlugin
from .errors import TransformationInvalidJsonError


class TransformationPlugin(BasePlugin):
    name = "transformation"
    phase = "forward"

    def _json_transform_enabled(self, config):
        return any(
            [
                config.get("json_rename"),
                config.get("json_defaults"),
                config.get("json_remove"),
            ]
        )

    def _load_json_body(self, context):
        body_bytes = context.extra.get("request_body", b"")
        if not body_bytes:
            return {}

        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransformationInvalidJsonError() from exc

        if not isinstance(parsed, dict):
            raise TransformationInvalidJsonError("Transformation expects JSON object body")

        return parsed

    async def around_request(self, context, call_next, config):
        upstream_headers = context.extra.setdefault("upstream_headers", {})

        for header_name, header_value in (config.get("set_headers") or {}).items():
            upstream_headers[str(header_name).lower()] = str(header_value)

        for header_name in config.get("remove_headers", []):
            upstream_headers.pop(str(header_name).lower(), None)

        if self._json_transform_enabled(config):
            body_json = self._load_json_body(context)

            for old_name, new_name in (config.get("json_rename") or {}).items():
                if old_name in body_json:
                    body_json[new_name] = body_json.pop(old_name)

            for field_name, default_value in (config.get("json_defaults") or {}).items():
                body_json.setdefault(field_name, default_value)

            for field_name in config.get("json_remove", []):
                body_json.pop(field_name, None)

            context.extra["request_body"] = json.dumps(body_json).encode("utf-8")
            upstream_headers.setdefault("content-type", "application/json")

        return await call_next()