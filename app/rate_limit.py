import os
import time
import redis.asyncio as redis
from opentelemetry.instrumentation.redis import RedisInstrumentor

RedisInstrumentor().instrument()


redis_url = os.getenv(
	"REDIS_URL",
	"redis://:redis1234@localhost:6379/0",
)

redis_client = redis.from_url(redis_url)

async def check_rate_limit(tenant, config, prefix):
    limit = config.get("limit")
    window = config.get("window_seconds")

    now = int(time.time())
    bucket = now // window

    key = f"rl:{tenant}:{prefix}:{bucket}"

    count = await redis_client.incr(key)

    if count == 1:
        await redis_client.expire(key, window)

    return count <= limit