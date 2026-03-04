import time
import json
from types import SimpleNamespace

from app.handler_http import SessionManager
from app.lifespan import lifespan
from app.context import RequestContext
from app.config_store import match_route
from app.plugins.engine import PluginEngine
from app.plugins.cache import CachePlugin
from app.plugins.jwt_auth import JWTAuthPlugin
from app.plugins.oauth import KeycloakOAuth2Plugin
from app.plugins.rate_limit import RateLimitPlugin
from app.plugins.retry import RetryPlugin
from app.plugins.circuit_breaker import CircuitBreakerPlugin
from app.plugins.errors import PluginError
from app.logging_fast import log_json
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY, prometheus_metrics
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.util.http import parse_excluded_urls

from opentelemetry.semconv.attributes.http_attributes import HTTP_ROUTE

import app.telemetry  # noqa: F401 - Importa para habilitar o OpenTelemetry

session = SessionManager.init()

plugins = PluginEngine(
    {
        "cache": CachePlugin(),
        "jwt_auth": JWTAuthPlugin(),
        "rate_limit": RateLimitPlugin(),
        "retry": RetryPlugin(),
        "circuit_breaker": CircuitBreakerPlugin(),
        "oauth2": KeycloakOAuth2Plugin(
            issuer="https://keycloak.meudominio.com/realms/myrealm",
            audience="gateway-api",
            required_scopes=["pricing.read"],
        ),
    }
)

async def body_iterator(receive):
    while True:
        message = await receive()
        body = message.get("body", b"")
        if body:
            yield body
        if not message.get("more_body"):
            break


async def read_full_body(receive):
    chunks = []
    async for chunk in body_iterator(receive):
        chunks.append(chunk)
    return b"".join(chunks)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        return await lifespan(scope, receive, send)

    if scope["type"] != "http":
        return

    start = time.perf_counter()
    path = scope["path"]

    if path == "/metrics":
        body = prometheus_metrics()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": body})
        return

    route = match_route(path)
    if not route:
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "code": "ROUTE_NOT_FOUND",
                        "description": "Route not found",
                    }
                ).encode(),
            }
        )
        return

    input_headers = {k.decode(): v.decode() for k, v in scope["headers"]}
    tenant = input_headers.get("x-tenant-id", "unknown")
    context = RequestContext(scope, route, tenant)

    try:
        await plugins.run_before(context)
    except PluginError as e:
        log_json(
            "ERROR",
            "plugin_before_request_error",
            route=route["prefix"],
            code=e.error_code,
            description=e.description,
        )
        await send(
            {
                "type": "http.response.start",
                "status": e.status_code,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(e.to_dict()).encode(),
            }
        )
        return
    except Exception as e:
        log_json(
            "ERROR",
            "plugin_before_request_error",
            route=route["prefix"],
            code=e.error_code,
            description=e.description,
        )        
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "code": "PLUGIN_EXECUTION_ERROR",
                        "description": "Unexpected error during plugin execution",
                    }
                ).encode(),
            }
        )
        return

    cached_response = context.extra.get("cache_hit")
    if cached_response:
        await send(
            {
                "type": "http.response.start",
                "status": cached_response["status"],
                "headers": cached_response["headers"],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": cached_response["body"],
            }
        )

        latency = time.perf_counter() - start
        REQUEST_COUNT.labels(
            method=scope["method"],
            route=route["prefix"],
            status=str(cached_response["status"]),
            tenant=tenant,
        ).inc()
        REQUEST_LATENCY.labels(route=route["prefix"], tenant=tenant).observe(latency)

        log_json(
            "INFO",
            "proxy_request",
            route=route["prefix"],
            latency_ms=latency * 1000,
            tenant=tenant,
            cache_hit=True,
        )
        return

    request_body = await read_full_body(receive)

    try:
        resp = await plugins.run_forward(
            context,
            lambda: foward_call(scope, path, route, context, request_body),
        )
    except Exception as error:
        log_json(
            "ERROR",
            "upstream_request_exception",
            route=route["prefix"],
            error=str(error),
        )
        resp = SimpleNamespace(
            status=502,
            headers=[("content-type", "application/json")],
            body=json.dumps(
                {
                    "code": "UPSTREAM_REQUEST_ERROR",
                    "description": "Error while calling upstream",
                }
            ).encode(),
        )

    await send(
        {
            "type": "http.response.start",
            "status": resp.status,
            "headers": [(k.encode(), v.encode()) for k, v in resp.headers],
        }
    )
    await send({"type": "http.response.body", "body": resp.body, "more_body": False})

    context.extra["response_data"] = {
        "status": resp.status,
        "headers": resp.headers,
        "body": resp.body,
    }

    try:
        await plugins.run_after(context)
    except PluginError as e:
        log_json(
            "ERROR",
            "plugin_after_response_error",
            route=route["prefix"],
            code=e.error_code,
            description=e.description,
        )

    latency = time.perf_counter() - start

    REQUEST_COUNT.labels(
        method=scope["method"],
        route=route["prefix"],
        status=str(resp.status),
        tenant=tenant,
    ).inc()
    REQUEST_LATENCY.labels(route=route["prefix"], tenant=tenant).observe(latency)

    log_json(
        "INFO",
        "proxy_request",
        route=route["prefix"],
        latency_ms=latency * 1000,
        tenant=tenant,
    )

async def foward_call(scope, path, route, context, request_body):
    upstream_url = route["target_base"] + path

    session = await SessionManager.get_session()
    async with session.request(
        method=scope["method"],
        url=upstream_url,
        headers={},
        data=request_body,
        allow_redirects=False,
    ) as resp:
        response_body = await resp.read()
        response_headers = list(resp.headers.items())

        if resp.status >= 400:
            log_json(
                "ERROR", "upstream_error", route=route["prefix"], status=resp.status
            )

        if resp.status == 200:
            context.response = resp

        return SimpleNamespace(
            status=resp.status,
            headers=response_headers,
            body=response_body,
        )


def get_route_details(method, path):
    x = match_route(path)
    return x["prefix"] if x else path, method.upper()


def _get_default_span_details(scope):
    route, method = get_route_details(method=scope["method"], path=scope["path"])
    attributes = {HTTP_ROUTE: route}
    span_name = f"{method} {route}"

    return span_name, attributes


app = OpenTelemetryMiddleware(
    app,
    excluded_urls=parse_excluded_urls("/metrics,/openapi.json,/docs"),
    # exclude_spans=["send", "receive"],
    default_span_details=_get_default_span_details,
)
