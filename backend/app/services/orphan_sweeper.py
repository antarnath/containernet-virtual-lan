"""orphan_sweeper — the safety net for half-started projects.

M4 phase 07. Runs every 60s. Two passes per tick:

1. Container pass — list all containers with the
   ``containernet.host=true`` label, then for each one:
     * If the container's ``containernet.project`` label points to a
       project that still exists AND is in a running state, leave
       it alone.
     * Otherwise, stop + remove the container.

2. Network pass — list all Docker networks whose name starts with
   ``cn`` (our per-wire bridge prefix), decode the project id from
   the name (``cn<12hex>ppl<4hex>``), and remove any whose project
   is not RUNNING. This handles the "backend crashed mid-start"
   case where bridges were created in Docker but the project never
   made it to ``running`` — the next Start would otherwise hit
   ``Pool overlaps`` and 500. See the M4-09 fix in commit 6f2c5d6.

This handles the "backend crashed mid-start" case where containers
+ bridges were spawned but the project row never made it to
``running`` (or was deleted out from under us). Without the
sweeper, those orphans would accumulate and pin Docker resources.

The sweeper is conservative: it never touches a container or
bridge whose project is alive and running. If the project is in
any other state (``stopped``, ``error``, ``partial``), both are
considered orphans and removed.

Container labels used:
  * ``containernet.host=true`` — the marker this sweeper looks for.
    Every node container in node_service.spawn_node sets it.
  * ``containernet.project=<project-id>`` — the owning project.

Bridge naming convention (set in link_service.create_bridge_for_link):
  * ``cn<project.id[:12]>ppl<link.id[:4]>`` — the 12-char project
    prefix is used to reverse-lookup the owning project.
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
# Bridge names look like "cn<8hex>p<4hex>l<4hex>". The "cn" is the
# ContainerNet prefix; the rest of the layout is defined in
# link_service.bridge_name (see that function for the rationale).
# The 8-char project prefix is what we need to reverse-lookup the
# owning project.
_BRIDGE_PREFIX = "cn"
_BRIDGE_PROJECT_LEN = 8  # hex chars from project.id at the start of the name
_BRIDGE_TOTAL_LEN = 20   # full length per link_service.bridge_name

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


def _project_id_from_bridge_name(name: str) -> str | None:
    """Reverse-lookup the project id from a per-wire bridge name.

    The bridge name is ``cn<8hex>p<4hex>l<4hex>`` (see
    link_service.bridge_name). The 8-hex prefix is the truncated
    project id (UUIDs are 32 hex chars; we only encode 8 of them
    to keep bridge names short).

    This function is best-effort: if the name doesn't match the
    pattern, returns None and the caller leaves the bridge alone.
    """
    if not name or not name.startswith(_BRIDGE_PREFIX):
        return None
    rest = name[len(_BRIDGE_PREFIX):]
    if len(rest) < _BRIDGE_PROJECT_LEN:
        return None
    short_pid = rest[:_BRIDGE_PROJECT_LEN]
    try:
        int(short_pid, 16)
    except ValueError:
        return None
    return short_pid


async def _load_alive_running() -> set[str]:
    """Return the set of full project ids that are currently RUNNING."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Project.id, Project.status).where(
                Project.status == ProjectStatus.RUNNING
            )
            rows = (await session.execute(stmt)).all()
        return {row[0] for row in rows}
    except Exception:
        log.exception("[orphan-sweeper] could not load project list")
        return set()


def _matches_orphan(
    short_pid: str,
    alive_full_ids: set[str],
    _all_full_ids_unused: set[str],
) -> bool:
    """True if the bridge's project is NOT currently RUNNING.

    A bridge is an orphan if either:
      * its project is in the DB but in a non-RUNNING state
        (error / stopped / partial / starting); or
      * its project is no longer in the DB at all (the project
        row was deleted but the bridge was leaked).

    The ``_all_full_ids_unused`` parameter is kept for API
    compatibility with earlier versions — only the RUNNING set
    is consulted.
    """
    prefix = short_pid.lower()
    for full_id in alive_full_ids:
        if full_id.lower().startswith(prefix):
            return False
    return True


async def sweep_once() -> int:
    """Run a single sweep. Returns the number of orphans removed
    (containers + bridges combined)."""
    client = get_docker_client()
    if client is None:
        return 0

    # First pass — list containers with our marker label.
    try:
        containers = client.containers.list(
            all=True,  # include stopped — we still want to inspect labels
            filters={"label": f"{HOST_LABEL}=true"},
        )
    except Exception:
        log.exception("[orphan-sweeper] docker list failed")
        containers = []

    # Second pass — list all per-wire bridges we ever created.
    # The Docker SDK's `names=` argument is exact-match only, so we
    # use the `name` filter (which is a substring match in the
    # Docker engine API) to grab every "cn" prefixed network, then
    # filter to the ones matching our exact project prefix.
    try:
        all_nets = client.networks.list(filters={"name": _BRIDGE_PREFIX})
    except Exception:
        log.exception("[orphan-sweeper] docker network list failed")
        all_nets = []
    bridges = [
        n for n in all_nets
        if _project_id_from_bridge_name(n.name) is not None
    ]

    if not containers and not bridges:
        return 0

    alive_running = await _load_alive_running()

    removed = 0

    # ─── container pass ────────────────────────────────────────
    for c in containers:
        labels = c.labels or {}
        pid = labels.get(PROJECT_LABEL)
        is_orphan = pid is None or pid not in alive_running
        if not is_orphan:
            continue
        try:
            cname = c.name
            log.info(
                "[orphan-sweeper] removing orphan container %s (project=%s status=%s)",
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

    # ─── bridge pass ───────────────────────────────────────────
    for net in bridges:
        try:
            nname = net.name
            short_pid = _project_id_from_bridge_name(nname)
            if short_pid is None:
                # Not one of our bridges (could be cni-* etc). Skip.
                continue
            if not _matches_orphan(short_pid, alive_running, set()):
                continue
            # Disconnect any still-attached containers, then remove.
            try:
                for cid in list(net.attrs.get("Containers", {}).keys()):
                    try:
                        net.disconnect(cid, force=True)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                net.remove()
            except Exception:
                log.exception("[orphan-sweeper] bridge remove failed for %s", nname)
                continue
            log.info(
                "[orphan-sweeper] removed orphan bridge %s (project prefix=%s)",
                nname, short_pid,
            )
            removed += 1
        except Exception:
            log.exception("[orphan-sweeper] handling bridge %s raised", getattr(net, "name", "?"))

    if removed:
        log.info("[orphan-sweeper] removed %d orphan(s)", removed)
    return removed