import time

from app.handler_http import SessionManager
from app.logging_fast import log_json

from .base import BasePlugin


TOKEN_CACHE = {}


class ForwardAuthPlugin(BasePlugin):
    name = "forward_auth"
    phase = "forward"

    def _should_refresh_retry(self, context, config):
        if bool(config.get("refresh_retry_all_methods", False)):
            return True

        default_methods = ["GET", "HEAD", "OPTIONS"]
        retry_methods = config.get("refresh_retry_methods", default_methods)
        allowed_methods = {method.upper() for method in retry_methods}
        request_method = context.scope.get("method", "GET").upper()
        return request_method in allowed_methods

    def _request_headers(self, context):
        raw_headers = context.scope.get("headers", [])
        return {k.decode().lower(): v.decode() for k, v in raw_headers}

    def _token_cache_key(self, config):
        token_url = config.get("token_url", "")
        client_id = config.get("client_id", "")
        scope = config.get("scope", "")
        audience = config.get("audience", "")
        return f"{token_url}|{client_id}|{scope}|{audience}"

    async def _fetch_oauth_token(self, context, config, force_refresh=False):
        token_url = config.get("token_url")
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        grant_type = config.get("grant_type", "client_credentials")
        timeout = max(1, int(config.get("timeout_seconds", 5)))
        skew_seconds = max(0, int(config.get("cache_skew_seconds", 30)))

        if not token_url or not client_id or not client_secret:
            raise RuntimeError("forward_auth oauth2_client_credentials requires token_url, client_id and client_secret")

        cache_key = self._token_cache_key(config)
        if force_refresh:
            TOKEN_CACHE.pop(cache_key, None)

        cached = TOKEN_CACHE.get(cache_key)
        now = time.time()
        if cached and cached.get("expires_at", 0) > now:
            return cached["access_token"]

        session = await SessionManager.get_session()

        payload = {
            "grant_type": grant_type,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if config.get("scope"):
            payload["scope"] = config.get("scope")
        if config.get("audience"):
            payload["audience"] = config.get("audience")

        async with session.post(token_url, data=payload, timeout=timeout) as response:
            body = await response.json(content_type=None)

            if response.status >= 400:
                raise RuntimeError(
                    f"forward_auth token endpoint error status={response.status} body={body}"
                )

            access_token = body.get("access_token")
            expires_in = int(body.get("expires_in", 300))

            if not access_token:
                raise RuntimeError("forward_auth token endpoint response missing access_token")

            TOKEN_CACHE[cache_key] = {
                "access_token": access_token,
                "expires_at": now + max(1, expires_in - skew_seconds),
            }

            return access_token

    async def around_request(self, context, call_next, config):
        mode = config.get("mode", "propagate")
        target_header = config.get("target_header", "authorization").lower()

        upstream_headers = context.extra.setdefault("upstream_headers", {})

        if mode == "oauth2_client_credentials":
            refresh_on_401 = bool(config.get("refresh_on_401", True))
            can_retry_request = self._should_refresh_retry(context, config)
            token = await self._fetch_oauth_token(context, config)
            scheme = config.get("scheme", "Bearer")
            upstream_headers[target_header] = f"{scheme} {token}" if scheme else token

            response = await call_next()

            if refresh_on_401 and can_retry_request and response.status == 401:
                log_json(
                    "WARN",
                    "forward_auth_token_refresh_on_401",
                    route=context.route.get("prefix"),
                )
                token = await self._fetch_oauth_token(context, config, force_refresh=True)
                upstream_headers[target_header] = f"{scheme} {token}" if scheme else token
                return await call_next()

            if refresh_on_401 and not can_retry_request and response.status == 401:
                log_json(
                    "INFO",
                    "forward_auth_skip_refresh_on_401_non_idempotent",
                    route=context.route.get("prefix"),
                    method=context.scope.get("method", "GET"),
                )

            return response

        if mode == "static":
            token = config.get("token")
            scheme = config.get("scheme", "Bearer")
            if token:
                upstream_headers[target_header] = f"{scheme} {token}" if scheme else token
            else:
                log_json(
                    "WARN",
                    "forward_auth_missing_token",
                    route=context.route.get("prefix"),
                )
            return await call_next()

        source_header = config.get("source_header", "authorization").lower()
        request_headers = self._request_headers(context)
        source_value = request_headers.get(source_header)

        if source_value:
            upstream_headers[target_header] = source_value
        else:
            log_json(
                "WARN",
                "forward_auth_source_missing",
                route=context.route.get("prefix"),
                source_header=source_header,
            )

        return await call_next()
