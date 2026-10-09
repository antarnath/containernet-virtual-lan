"""FastAPI application entrypoint.

M4 — the application is intentionally minimal in phase 01. The lifespan:
  * initializes the database (creates the 5 new tables, drops the
    M2 ``project_hosts`` and ``project_edges`` tables via _PATCHES)
  * pings the Docker daemon (the host agent's containers will need
    this in phase 02)
  * shuts down cleanly

The orphan sweeper + lifecycle tasks ship in phase 02.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core import init_db
from app.core import docker_client, settings
from app.services import anomaly_detector, attack_detector, orphan_sweeper


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — create the 5 new tables; _PATCHES drops the M2 ones.
    await init_db()
    print("[main] database initialized (M4 5-primitive model)")

    if docker_client.ping():
        print(f"[main] Docker daemon reachable at {settings.DOCKER_HOST}")
    else:
        print(f"[main] WARNING: Docker daemon unreachable at {settings.DOCKER_HOST}")
    if settings.ADMIN_TOKEN:
        print("[main] admin endpoints ENABLED (X-Admin-Token required)")
    else:
        print("[main] admin endpoints DISABLED (ADMIN_TOKEN unset)")

    # M4 phase 07 — orphan sweeper for half-started projects.
    orphan_sweeper.start_sweeper()

    yield

    # Shutdown — cancel periodic tasks.
    orphan_sweeper.stop_sweeper()
    anomaly_detector.stop_all()
    attack_detector.stop_all()


app = FastAPI(title="ContainerNet API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
