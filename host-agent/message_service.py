"""Stub message service. Real implementation in Phase 05.

Right now this just reserves port :8080 so we can confirm it's open.
All routes return HTTP 501 'Not Implemented'.
"""

import asyncio

from aiohttp import web

from config import config


async def not_implemented(_request: web.Request) -> web.Response:
    return web.json_response(
        {"detail": "Message service implemented in Phase 05"},
        status=501,
    )


async def run_server() -> None:
    app = web.Application()
    app.router.add_post("/send", not_implemented)
    app.router.add_post("/receive", not_implemented)
    app.router.add_get("/messages", not_implemented)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.MESSAGE_PORT)
    await site.start()
    print(f"[{config.HOST_NAME}] message server listening on :{config.MESSAGE_PORT} (stub)")


if __name__ == "__main__":
    asyncio.run(run_server())