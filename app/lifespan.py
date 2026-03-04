import asyncio

from app.config_store import load_routes, subscribe_config_updates
from app.handler_http import SessionManager


async def startup() -> None:
    """Startup middleware for initializing resources."""
    await load_routes()
    asyncio.create_task(subscribe_config_updates())


async def shutdown() -> None:
    """Shutdown middleware for cleaning up resources."""
    await SessionManager.close_session()


async def lifespan(scope, receive, send) -> None:
    while True:
        """Lifespan middleware for startup and shutdown events."""
        msg = await receive()
        if msg["type"] == "lifespan.startup":
            asyncio.create_task(startup())
            await send({"type": "lifespan.startup.complete"})
        elif msg["type"] == "lifespan.shutdown":
            await shutdown()
            await send({"type": "lifespan.shutdown.complete"})
            return