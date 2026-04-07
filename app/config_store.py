import os
import re
import orjson
import redis.asyncio as redis

from pymongo import AsyncMongoClient
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

PymongoInstrumentor().instrument()

CHANNEL = "config_updates"
redis_url = os.getenv(
	"REDIS_URL",
	"redis://:redis1234@localhost:6379/0",
)

redis_client = redis.from_url(redis_url)

mongo_url = os.getenv(
	"MONGO_URL",
    "mongodb://localhost:27017/?directConnection=true",
)

client = AsyncMongoClient(mongo_url)
db = client.gateway
routes_collection = db.routes
plugins_collection = db.plugins

_routes_cache = {}


def _route_tenant(route: dict) -> str:
    return str(route.get("tenant_id") or route.get("tenant") or "").strip("/")


def _compose_cache_path(tenant: str, prefix: str) -> str:
    normalized_prefix = "/" + str(prefix or "").lstrip("/")
    normalized_tenant = str(tenant or "").strip("/")
    if not normalized_tenant:
        return normalized_prefix
    return f"/{normalized_tenant}{normalized_prefix}"


def _is_template_route(prefix: str) -> bool:
    return "{" in prefix and "}" in prefix


def _template_part_to_regex(part: str) -> str:
    # Supports `{param}` and `{param:custom_regex}` placeholders.
    inner = part[1:-1]
    if ":" in inner:
        _, custom_regex = inner.split(":", 1)
        custom_regex = custom_regex.strip()
        if custom_regex:
            return f"(?:{custom_regex})"
    return r"[^/]+"


def _split_template(template: str) -> list[tuple[bool, str]]:
    parts = []
    cursor = 0

    while cursor < len(template):
        start = template.find("{", cursor)
        if start == -1:
            parts.append((False, template[cursor:]))
            break

        if start > cursor:
            parts.append((False, template[cursor:start]))

        depth = 1
        end = start + 1
        while end < len(template) and depth > 0:
            if template[end] == "{":
                depth += 1
            elif template[end] == "}":
                depth -= 1
            end += 1

        if depth == 0:
            parts.append((True, template[start:end]))
            cursor = end
            continue

        # Unbalanced placeholder: treat the remainder as a literal string.
        parts.append((False, template[start:]))
        break

    return parts


def _match_template_route(path: str, template: str) -> bool:
    parts = _split_template(template)
    try:
        pattern = "".join(
            _template_part_to_regex(part) if is_placeholder else re.escape(part)
            for is_placeholder, part in parts
        )
        return re.fullmatch(pattern, path) is not None
    except re.error:
        return False

async def load_routes(entity_id=None, tenant_id=None):
    global _routes_cache
    routes = {}

    if entity_id and tenant_id:
        r = await routes_collection.find_one({"tenant_id": tenant_id, "_id": entity_id})
        if r:
            print(f"Updating route in cache: {r['prefix']}")
            print(r)
            methods = r.get("methods") or ["GET"]
            route_tenant = _route_tenant(r)
            for method in methods:
                key = f"{method.upper()}:{_compose_cache_path(route_tenant, r['prefix'])}"
                routes[key] = r
            _routes_cache.update(routes)
        return
    async for r in routes_collection.find():
        print(f"Loading route into cache: {r['prefix']}")
        print(r)
        methods = r.get("methods") or ["GET"]
        route_tenant = _route_tenant(r)
        for method in methods:
            key = f"{method.upper()}:{_compose_cache_path(route_tenant, r['prefix'])}"
            routes[key] = r
    _routes_cache = routes

def match_route(key):
    method, path = key.split(":", 1)
    method = method.upper()
    template_candidates = []

    for prefix, route in _routes_cache.items():
        value_method, value_prefix = prefix.split(":", 1)
        if value_method.upper() != method:
            continue

        if _is_template_route(value_prefix):
            template_candidates.append((value_prefix, route))
            continue

        if path.startswith(value_prefix):
            return route

    for value_prefix, route in template_candidates:
        if _match_template_route(path, value_prefix):
            return route

    return None


def get_available_routes():
    """Retorna um snapshot serializavel das rotas atualmente em cache."""
    deduplicated_routes = {}
    for route in _routes_cache.values():
        methods = tuple(sorted((route.get("methods") or ["GET"])))
        dedup_key = (route.get("prefix"), route.get("target_base"), methods)
        deduplicated_routes[dedup_key] = route

    routes = []
    for route in deduplicated_routes.values():
        routes.append(
            {
                "prefix": route.get("prefix"),
                "target_base": route.get("target_base"),
                "strip_prefix": route.get("strip_prefix", False),
                "methods": route.get("methods", ["GET"]),
                "plugins": route.get("plugins", []),
            }
        )

    return sorted(routes, key=lambda item: item["prefix"] or "")


async def save_plugin(plugin_doc):
    """Insert or update a plugin document in the `plugins` collection.

    Expected minimal fields in `plugin_doc`:
      - name: human name / unique identifier
      - type: plugin type (used by engine mapping)
      - code: string with python source
      - enabled: bool
    """
    if not plugin_doc.get("name") or not plugin_doc.get("type") or not plugin_doc.get("code"):
        raise ValueError("plugin must contain name, type and code")

    existing = await plugins_collection.find_one({"type": plugin_doc.get("type")})
    if existing:
        await plugins_collection.update_one({"_id": existing["_id"]}, {"$set": plugin_doc})
        return existing["_id"]

    res = await plugins_collection.insert_one(plugin_doc)
    return res.inserted_id


async def list_plugins():
    """Return all plugin documents as a list."""
    items = []
    async for p in plugins_collection.find():
        # convert ObjectId to string for JSON serialisation if present
        if p.get("_id"):
            try:
                p["_id"] = str(p["_id"])
            except Exception:
                pass
        items.append(p)
    return items


async def subscribe_config_updates():
    global _routes_cache
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL)

    async for message in pubsub.listen():

        if message["type"] != "message":
            continue

        print(f"Received config update: {message['data']}")
        event = orjson.loads(message["data"])

        if event["entity"] == "route":

            if event["event"] == "upsert":
                await load_routes(
                    event["entity_id"],
                    event["tenant_id"]
                )

            elif event["event"] == "delete":
                r = await routes_collection.find_one({"tenant_id": event["tenant_id"], "_id": event["entity_id"]})
                prefix = r["prefix"] if r else None
                methods = r.get("methods") if r else None
                if prefix and methods:
                    route_tenant = _route_tenant(r)
                    for method in methods:
                        key = f"{method.upper()}:{_compose_cache_path(route_tenant, prefix)}"
                        print(f"Removing route from cache: {key}")
                        _routes_cache.pop(key, None)