"""FastAPI application entrypoint."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api import websocket as ws_router
from app.core import get_session, init_db
from app.services import host_service


async def offline_sweeper() -> None:
    """Periodically mark hosts offline if no heartbeat in 15+ seconds."""
    while True:
        try:
            async for session in get_session():
                marked = await host_service.sweep_offline_hosts(session)
                if marked:
                    print(f"[sweeper] marked {marked} host(s) offline")
        except Exception as exc:
            print(f"[sweeper] error: {exc}")
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    sweeper_task = asyncio.create_task(offline_sweeper())
    print("[main] database initialized, sweeper started")
    yield
    # Shutdown
    sweeper_task.cancel()


app = FastAPI(title="ContainerNet API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}