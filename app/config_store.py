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

_routes_cache = {}


def _is_template_route(prefix: str) -> bool:
    return "{" in prefix and "}" in prefix


def _match_template_route(path: str, template: str) -> bool:
    parts = re.split(r"(\{[^{}]+\})", template)
    pattern = "".join(
        r"[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in parts
    )
    return re.fullmatch(pattern, path) is not None

async def load_routes(entity_id=None, tenant_id=None):
    global _routes_cache
    routes = {}

    if entity_id and tenant_id:
        r = await routes_collection.find_one({"tenant_id": tenant_id, "_id": entity_id})
        if r:
            print(f"Updating route in cache: {r['prefix']}")
            print(r)
            methods = r.get("methods") or ["GET"]
            for method in methods:
                key = f"{method.upper()}:{r['prefix']}"
                routes[key] = r
            _routes_cache.update(routes)
        return
    async for r in routes_collection.find():
        print(f"Loading route into cache: {r['prefix']}")
        print(r)
        methods = r.get("methods") or ["GET"]
        for method in methods:
            key = f"{method.upper()}:{r['prefix']}"
            routes[key] = r
    _routes_cache = routes

def match_route(key):
    method, path = key.split(":", 1)
    method = method.upper()
    for prefix, route in _routes_cache.items():
        value_method, value_prefix = prefix.split(":", 1)
        if value_method.upper() != method:
            continue
        if _is_template_route(value_prefix):
            if _match_template_route(path, value_prefix):
                return route
            continue

        if path.startswith(value_prefix):
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
                    for method in methods:
                        key = f"{method.upper()}:{prefix}"
                        print(f"Removing route from cache: {key}")
                        _routes_cache.pop(key, None)