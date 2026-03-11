import json

from app.logging_fast import log_json

from .base import BasePlugin


class RequestLoggingPlugin(BasePlugin):
    name = "logging"
    phase = "forward"

    def _sensitive_tokens(self, config):
        raw = config.get(
            "sensitive_fields",
            [
                "password",
                "passwd",
                "pwd",
                "token",
                "secret",
                "authorization",
                "api_key",
                "cpf",
                "cnpj",
                "email",
            ],
        )

        if isinstance(raw, str):
            return tuple(part.strip().lower() for part in raw.split(",") if part.strip())

        if isinstance(raw, list):
            return tuple(str(part).strip().lower() for part in raw if str(part).strip())

        return ()

    def _is_sensitive_key(self, key, config):
        key_lower = str(key).lower()
        return any(token in key_lower for token in self._sensitive_tokens(config))

    def _mask_sensitive(self, payload, config):
        if isinstance(payload, dict):
            masked = {}
            for key, value in payload.items():
                if self._is_sensitive_key(key, config):
                    masked[key] = config.get("mask_value", "***")
                else:
                    masked[key] = self._mask_sensitive(value, config)
            return masked

        if isinstance(payload, list):
            return [self._mask_sensitive(item, config) for item in payload]

        if isinstance(payload, tuple):
            return tuple(self._mask_sensitive(item, config) for item in payload)

        return payload

    def _decode_body(self, body):
        if body is None:
            return ""

        if isinstance(body, (bytes, bytearray)):
            return bytes(body).decode("utf-8", errors="replace")

        return str(body)

    def _body_for_log(self, body, config):
        text = self._decode_body(body)

        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = text

        if config.get("mask_sensitive_enabled", True):
            payload = self._mask_sensitive(payload, config)

        rendered = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)

        max_chars = int(config.get("max_body_chars", 4000))
        if max_chars > 0 and len(rendered) > max_chars:
            rendered = rendered[:max_chars] + "... (truncated)"

        return rendered

    async def around_request(self, context, call_next, config):
        route = context.route.get("prefix")
        tenant = context.tenant
        scope = context.scope
        method = scope.get("method")

        if config.get("log_request", True):
            log_json(
                "INFO",
                "gateway_request_input",
                plugin=self.name,
                route=route,
                method=method,
                tenant=tenant,
                request_body=self._body_for_log(context.extra.get("request_body", b""), config),
            )

        response = await call_next()

        if config.get("log_response", True):
            log_json(
                "INFO",
                "gateway_response_output",
                plugin=self.name,
                route=route,
                method=method,
                tenant=tenant,
                status=getattr(response, "status", None),
                response_body=self._body_for_log(getattr(response, "body", b""), config),
            )

        return response
