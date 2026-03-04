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
	"redis://localhost:6379",
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
        r = await routes_collection.find_one({"tenant_id": tenant_id, "entity_id": entity_id})
        if r:
            routes[r["prefix"]] = r
            _routes_cache.update(routes)
        return
    async for r in routes_collection.find():
        routes[r["prefix"]] = r
    _routes_cache = routes

def match_route(path):
    for prefix, route in _routes_cache.items():
        if _is_template_route(prefix):
            if _match_template_route(path, prefix):
                return route
            continue

        if path.startswith(prefix):
            return route
    return None


async def subscribe_config_updates():
    global _routes_cache
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL)

    async for message in pubsub.listen():

        if message["type"] != "message":
            continue

        event = orjson.loads(message["data"])

        if event["entity"] == "route":

            if event["event"] == "upsert":
                await load_routes(
                    event["entity_id"],
                    event["tenant_id"]
                )

            elif event["event"] == "delete":
                r = await routes_collection.find_one({"tenant_id": event["tenant_id"], "entity_id": event["entity_id"]})
                prefix = r["prefix"] if r else None
                if prefix:  
                    _routes_cache.pop(prefix, None)