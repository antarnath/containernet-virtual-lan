"""FastAPI application entrypoint."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api import websocket as ws_router
from app.core import docker_client, get_session, init_db, settings
from app.models import ProjectStatus
from app.services import container_service, host_service, orphan_service, project_service


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


async def _graceful_shutdown() -> None:
    """Phase 09 — stop every spawned host container before the process
    exits, then mark the projects as ``stopped`` in the DB so the next
    start is a clean restart rather than an orphan-state recovery.

    This runs when Docker sends SIGTERM (``docker compose down`` /
    ``restart``). Bridge networks are intentionally left in place — they're
    cheap to keep and avoid the cost of recreating them on the next start.
    """
    try:
        async for session in get_session():
            projects = await project_service.list_projects(session)
            stopped = 0
            for project in projects:
                pid = str(project.id)
                if project.status.value == "running":
                    try:
                        removed = container_service.stop_project_hosts(
                            pid, timeout=5
                        )
                        if removed:
                            print(
                                f"[shutdown] stopped {removed} container(s) "
                                f"for project {pid}"
                            )
                            stopped += removed
                        project.status = ProjectStatus.STOPPED
                    except Exception as exc:
                        print(
                            f"[shutdown] failed to stop {pid}: {exc}"
                        )
            if stopped:
                await session.commit()
                print(f"[shutdown] {stopped} container(s) stopped total")
            else:
                print("[shutdown] no running projects to stop")
    except Exception as exc:
        print(f"[shutdown] graceful shutdown failed: {exc}")


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
    # Shutdown — Phase 09: stop every spawned container before exiting.
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass
    await _graceful_shutdown()


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