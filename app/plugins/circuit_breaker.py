import json
import time
from types import SimpleNamespace

from app.logging_fast import log_json

from .base import BasePlugin


CIRCUIT_BREAKER_STATE = {}


class CircuitBreakerPlugin(BasePlugin):
    name = "circuit_breaker"
    phase = "forward"

    def _state(self, context):
        key = f"{context.route.get('target_base', '')}:{context.route.get('prefix', '')}"
        state = CIRCUIT_BREAKER_STATE.setdefault(
            key,
            {"failures": 0, "opened_until": 0.0},
        )
        return key, state

    async def around_request(self, context, call_next, config):
        threshold = max(1, int(config.get("failure_threshold", 5)))
        recovery_timeout_seconds = max(1, int(config.get("recovery_timeout_seconds", 30)))

        key, state = self._state(context)
        now = time.monotonic()

        if state["opened_until"] > now:
            log_json(
                "ERROR",
                "circuit_breaker_open",
                route=context.route["prefix"],
            )
            return SimpleNamespace(
                status=503,
                headers=[("content-type", "application/json")],
                body=json.dumps(
                    {
                        "code": "CIRCUIT_BREAKER_OPEN",
                        "description": "Upstream temporarily unavailable",
                    }
                ).encode(),
            )

        if state["opened_until"]:
            state["opened_until"] = 0.0

        try:
            response = await call_next()
        except Exception:
            state["failures"] += 1
            if state["failures"] >= threshold:
                state["opened_until"] = time.monotonic() + recovery_timeout_seconds
                state["failures"] = 0
            raise

        if response.status >= 500:
            state["failures"] += 1
            if state["failures"] >= threshold:
                state["opened_until"] = time.monotonic() + recovery_timeout_seconds
                state["failures"] = 0
        else:
            state["failures"] = 0
            state["opened_until"] = 0.0

        CIRCUIT_BREAKER_STATE[key] = state
        return response
