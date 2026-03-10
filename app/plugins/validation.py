import json
from urllib.parse import parse_qs

from .base import BasePlugin
from .errors import ValidationFailedError, ValidationInvalidJsonError


class ValidationPlugin(BasePlugin):
    name = "validation"
    phase = "forward"

    def _get_json_body(self, context, config):
        request_body = context.extra.get("request_body", b"")
        if not request_body:
            return {}

        try:
            parsed = json.loads(request_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationInvalidJsonError() from exc

        if not isinstance(parsed, dict):
            raise ValidationFailedError("Request body JSON must be an object")

        return parsed

    def _scope_headers(self, context):
        raw_headers = context.scope.get("headers", [])
        return {k.decode().lower(): v.decode() for k, v in raw_headers}

    def _scope_query_params(self, context):
        query_string = context.scope.get("query_string", b"")
        parsed = parse_qs(query_string.decode("latin-1"), keep_blank_values=True)
        return {k: values[-1] for k, values in parsed.items()}

    async def around_request(self, context, call_next, config):
        allowed_methods = [m.upper() for m in config.get("allowed_methods", [])]
        request_method = context.scope.get("method", "GET").upper()
        if allowed_methods and request_method not in allowed_methods:
            raise ValidationFailedError(
                f"Method {request_method} is not allowed; expected one of {allowed_methods}"
            )

        body_json = self._get_json_body(context, config)

        required_fields = config.get("required_fields", [])
        for field in required_fields:
            if field not in body_json:
                raise ValidationFailedError(f"Missing required field: {field}")

        headers = self._scope_headers(context)
        for rule in config.get("header_rules", []):
            name = str(rule.get("name", "")).lower()
            if not name:
                continue

            required = bool(rule.get("required", False))
            expected = rule.get("equals")
            actual = headers.get(name)

            if required and actual is None:
                raise ValidationFailedError(f"Missing required header: {name}")
            if expected is not None and actual != str(expected):
                raise ValidationFailedError(
                    f"Header {name} has invalid value; expected {expected}"
                )

        query_params = self._scope_query_params(context)
        for rule in config.get("query_rules", []):
            name = str(rule.get("name", ""))
            if not name:
                continue

            required = bool(rule.get("required", False))
            expected = rule.get("equals")
            actual = query_params.get(name)

            if required and actual is None:
                raise ValidationFailedError(f"Missing required query param: {name}")
            if expected is not None and actual != str(expected):
                raise ValidationFailedError(
                    f"Query param {name} has invalid value; expected {expected}"
                )

        return await call_next()