"""FastAPI application entrypoint."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api import websocket as ws_router
from app.core import docker_client, get_session, init_db, settings
from app.services import host_service, orphan_service


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

    # Phase 03 — orphan cleanup
    try:
        async for session in get_session():
            stats = await orphan_service.sweep_orphans(session)
            if stats["removed_containers"] or stats["removed_networks"]:
                print(
                    f"[main] orphan sweep removed "
                    f"{stats['removed_containers']} container(s) and "
                    f"{stats['removed_networks']} network(s)"
                )
            else:
                print(f"[main] orphan sweep: nothing to clean ({stats['live_projects']} live projects)")
    except Exception as exc:
        print(f"[main] orphan sweep failed: {exc}")

    # Phase 01 — log Docker reachability + admin-token status.
    if docker_client.ping():
        print(f"[main] Docker daemon reachable at {settings.DOCKER_HOST}")
    else:
        print(f"[main] WARNING: Docker daemon unreachable at {settings.DOCKER_HOST}")
    if settings.ADMIN_TOKEN:
        print("[main] admin endpoints ENABLED (X-Admin-Token required)")
    else:
        print("[main] admin endpoints DISABLED (ADMIN_TOKEN unset)")

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