import asyncio

from app.logging_fast import log_json

from .base import BasePlugin


class RetryPlugin(BasePlugin):
    name = "retry"
    phase = "forward"

    async def around_request(self, context, call_next, config):
        attempts = max(1, int(config.get("attempts", 3)))
        backoff_ms = config.get("backoff_ms", config.get("delay_ms", 100))
        delay_ms = max(0, int(backoff_ms))

        retry_on = config.get("retry_on", config.get("retry_on_status", [502, 503, 504]))
        retry_on_status = {int(status) for status in retry_on}

        for attempt in range(1, attempts + 1):
            try:
                response = await call_next()
            except Exception as error:
                should_retry = attempt < attempts
                log_json(
                    "ERROR",
                    "upstream_request_exception",
                    route=context.route["prefix"],
                    attempt=attempt,
                    max_attempts=attempts,
                    error=str(error),
                )

                if should_retry:
                    if delay_ms:
                        await asyncio.sleep(delay_ms / 1000)
                    continue
                raise

            should_retry = (
                attempt < attempts
                and response.status in retry_on_status
            )

            if should_retry:
                log_json(
                    "WARN",
                    "upstream_retry",
                    route=context.route["prefix"],
                    status=response.status,
                    attempt=attempt,
                    max_attempts=attempts,
                )
                if delay_ms:
                    await asyncio.sleep(delay_ms / 1000)
                continue

            return response
