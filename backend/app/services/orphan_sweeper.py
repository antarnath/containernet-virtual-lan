"""orphan_sweeper — the safety net for half-started projects.

M4 phase 07. Runs every 60s. Lists all containers with the
``containernet.host=true`` label, then for each one:
  * If the container's ``containernet.project`` label points to a
    project that still exists AND is in a running state, leave
    it alone.
  * Otherwise, stop + remove the container.

This handles the "backend crashed mid-start" case where containers
were spawned but the project row never made it to ``running`` (or
was deleted out from under us). Without the sweeper, those
orphans would accumulate and pin Docker resources.

The sweeper is conservative: it never touches a container whose
project is alive and running. If the project is in any other
state (``stopped``, ``error``, ``partial``), the container is
considered an orphan and removed.

Container labels used:
  * ``containernet.host=true`` — the marker this sweeper looks for.
    Every node container in node_service.spawn_node sets it.
  * ``containernet.project=<project-id>`` — the owning project.

Set on node containers in container_service.spawn_node.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.docker_client import get_docker_client
from app.models import Project, ProjectStatus

log = logging.getLogger(__name__)

# Sweep interval — the spec says 60s.
SWEEP_INTERVAL_SEC = 60.0
HOST_LABEL = "containernet.host"
PROJECT_LABEL = "containernet.project"

_task: asyncio.Task | None = None


def start_sweeper() -> None:
    """Spawn the periodic sweeper task. Idempotent."""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_sweeper_loop(), name="orphan-sweeper")
    log.info("[orphan-sweeper] started")


def stop_sweeper() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None


async def _sweeper_loop() -> None:
    """Main loop — every SWEEP_INTERVAL_SEC, sweep once."""
    # First sweep on startup is delayed by 30s so a fresh backend
    # has a chance to register its projects before we run.
    await asyncio.sleep(30.0)
    while True:
        try:
            await sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[orphan-sweeper] sweep_once failed")
        try:
            await asyncio.sleep(SWEEP_INTERVAL_SEC)
        except asyncio.CancelledError:
            raise


async def sweep_once() -> int:
    """Run a single sweep. Returns the number of containers removed."""
    client = get_docker_client()
    if client is None:
        return 0
    try:
        containers = client.containers.list(
            all=True,  # include stopped — we still want to inspect labels
            filters={"label": f"{HOST_LABEL}=true"},
        )
    except Exception:
        log.exception("[orphan-sweeper] docker list failed")
        return 0

    if not containers:
        return 0

    # Build a set of project ids that exist and are RUNNING — the
    # only state under which a container is *not* an orphan.
    alive_running: set[str] = set()
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Project.id, Project.status).where(
                Project.status == ProjectStatus.RUNNING
            )
            rows = (await session.execute(stmt)).all()
        alive_running = {row[0] for row in rows}
    except Exception:
        log.exception("[orphan-sweeper] could not load project list")

    removed = 0
    for c in containers:
        labels = c.labels or {}
        pid = labels.get(PROJECT_LABEL)
        # If the container has no project label at all, treat it as
        # an orphan (someone hand-spun a containernet host without
        # the lifecycle).
        is_orphan = (
            pid is None
            or pid not in alive_running
        )
        if not is_orphan:
            continue
        try:
            cname = c.name
            log.info(
                "[orphan-sweeper] removing orphan %s (project=%s status=%s)",
                cname, pid, (c.status if hasattr(c, "status") else "?"),
            )
            try:
                c.stop(timeout=3)
            except Exception:
                pass
            try:
                c.remove(force=True)
            except Exception:
                log.exception("[orphan-sweeper] remove failed for %s", cname)
                continue
            removed += 1
        except Exception:
            log.exception("[orphan-sweeper] handling %s raised", c.id)

    if removed:
        log.info("[orphan-sweeper] removed %d orphan container(s)", removed)
    return removed