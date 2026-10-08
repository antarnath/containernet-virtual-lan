"""Project lifecycle — start / stop / restart a project.

M4 phase 02. The lifecycle reads the project's full topology
(nodes + interfaces + links) and materializes it as Docker
containers + Linux bridges. Stop tears them all down. Restart
is stop + start.

The lifecycle is **idempotent and resumable**:
  * start can be called twice; the second call is a no-op if
    every container + bridge already exists.
  * start can be called after a partial start that crashed; it
    re-creates whatever's missing and reuses what's there.
  * stop is no-op-safe; it never throws on missing containers.
  * on start failure, we roll back any partial state so the
    project doesn't end up with half-spawned containers.

State machine (the ``projects.status`` column):
  draft    ──start──▶  starting ──ok──▶  running
                                 ──fail─▶  error
  running  ──stop──▶   stopping ──ok──▶  stopped
  stopped  ──start──▶  starting ──ok──▶  running
  partial  ──start──▶  starting (idempotent resume)
  error    ──start──▶  starting (retry from where we left off)

The status transitions are written to the DB after the work
succeeds, so the canvas UI can poll for them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    Project,
    ProjectInterface,
    ProjectLink,
    ProjectNode,
    ProjectStatus,
)
from app.services import container_service, link_service, node_service

log = logging.getLogger(__name__)


# ─── data shapes ───────────────────────────────────────────────────────

@dataclass
class LifecycleResult:
    project_id: str
    status: str
    started_nodes: list[str] = field(default_factory=list)
    started_bridges: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ─── start ─────────────────────────────────────────────────────────────

async def start_project(
    session: AsyncSession,
    project_id: str,
) -> LifecycleResult:
    """Start a project. Idempotent + resumable.

    Steps:
      1. Set project status to ``starting`` (visible in the UI).
      2. For every link, create the per-link bridge (no-op if exists).
      3. For every node, spawn the container + attach to its bridges.
      4. Set project status to ``running`` on success, ``error`` on
         failure (with rollback of the partial state).
    """
    project = await _load_project(session, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} not found")

    project.status = ProjectStatus.STARTING
    await session.commit()

    result = LifecycleResult(project_id=project_id, status="starting")

    backend_network = settings.BACKEND_NETWORK
    backend_url = settings.BACKEND_URL

    # Step 1: every bridge first (so node attachment always finds
    # the bridge it expects).
    for link in project.links:
        try:
            a, b = _iface_for_link(project, link)
            bridge = link_service.create_bridge_for_link(
                project_id=project.id,
                link_id=link.id,
                iface_a_ip=a.ip_address if a else None,
                iface_a_mask=a.subnet_mask if a else None,
                iface_b_ip=b.ip_address if b else None,
                iface_b_mask=b.subnet_mask if b else None,
            )
            # Persist the chosen bridge name on the link row so the
            # capture / router proxy can find it later.
            link.docker_bridge_name = bridge.short_name
            result.started_bridges.append(bridge.network_id)
        except Exception as exc:
            result.errors.append(f"bridge {link.id}: {exc}")
            log.exception("[lifecycle] bridge create failed for link %s", link.id)
            await _set_error(session, project, result, "start")
            return result

    # Step 2: spawn every node. Routers are spawned first so they're
    # up before any host that needs them as a default gateway.
    nodes = sorted(
        project.nodes,
        key=lambda n: (
            0 if n.kind == "router" else 1,
            0 if n.kind == "switch" else 1,
            2,
            n.created_at,
        ),
    )
    for node in nodes:
        try:
            spawned = node_service.spawn_node(
                project=project,
                node=node,
                links=project.links,
                interfaces=node.interfaces,
                backend_network=backend_network,
                backend_url=backend_url,
            )
            # Persist the container id on the node row.
            node.container_id = spawned.container_id
            node.container_status = "running"
            result.started_nodes.append(node.id)
        except Exception as exc:
            result.errors.append(f"node {node.name}: {exc}")
            log.exception("[lifecycle] node spawn failed for %s", node.name)
            await _set_error(session, project, result, "start")
            return result

    # Step 3: success.
    project.status = ProjectStatus.RUNNING
    await session.commit()
    result.status = "running"
    return result


# ─── stop ──────────────────────────────────────────────────────────────

async def stop_project(
    session: AsyncSession,
    project_id: str,
) -> LifecycleResult:
    """Stop a project. Idempotent + best-effort.

    Tears down in reverse order: nodes first, then bridges.
    """
    project = await _load_project(session, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} not found")

    project.status = ProjectStatus.STOPPED
    await session.commit()

    result = LifecycleResult(project_id=project_id, status="stopping")

    # Nodes first.
    for node in project.nodes:
        if node.container_id:
            try:
                container_service.stop_container(node.container_id, timeout=3)
                container_service.remove_container(node.container_id, force=True)
            except Exception as exc:
                result.errors.append(f"stop node {node.name}: {exc}")
                log.warning("[lifecycle] stop node %s: %s", node.name, exc)
            node.container_id = None
            node.container_status = "stopped"
            result.started_nodes.append(node.id)

    # Then bridges.
    for link in project.links:
        try:
            link_service.delete_bridge_for_link(
                project_id=project.id, link_id=link.id
            )
            link.docker_bridge_name = None
            result.started_bridges.append(link.id)
        except Exception as exc:
            result.errors.append(f"delete bridge {link.id}: {exc}")
            log.warning("[lifecycle] delete bridge %s: %s", link.id, exc)

    project.status = ProjectStatus.STOPPED
    await session.commit()
    result.status = "stopped"
    return result


# ─── restart ───────────────────────────────────────────────────────────

async def restart_project(
    session: AsyncSession, project_id: str
) -> LifecycleResult:
    """Restart a project = stop + start."""
    stop_result = await stop_project(session, project_id)
    if stop_result.errors:
        # Continue anyway — start is idempotent and will reuse
        # whatever's left.
        log.warning(
            "[lifecycle] restart: stop had %d errors; proceeding to start",
            len(stop_result.errors),
        )
    return await start_project(session, project_id)


# ─── queries (used by the canvas UI's state endpoint) ─────────────────

async def project_state(
    session: AsyncSession, project_id: str
) -> dict:
    """Snapshot of the project's live state for the canvas.

    Returns a JSON-friendly dict with:
      * project.status
      * per-node container info (id, name, status, image)
      * per-link bridge info (network_id, name, short_name, subnet)
    """
    project = await _load_project(session, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} not found")

    nodes = []
    for node in project.nodes:
        info = node_service.find_node_container(node.id) if node.container_id else None
        nodes.append({
            "id": node.id,
            "name": node.name,
            "kind": node.kind.value if hasattr(node.kind, "value") else node.kind,
            "container_id": node.container_id,
            "container_status": node.container_status,
            "container": info,
        })

    links = []
    for link in project.links:
        bridge = link_service.find_bridge_by_link_id(project.id, link.id) if link.docker_bridge_name else None
        links.append({
            "id": link.id,
            "iface_a_id": link.iface_a_id,
            "iface_b_id": link.iface_b_id,
            "docker_bridge_name": link.docker_bridge_name,
            "bridge": (
                {
                    "network_id": bridge.network_id,
                    "name": bridge.name,
                    "short_name": bridge.short_name,
                    "subnet_cidr": bridge.subnet_cidr,
                }
                if bridge else None
            ),
        })

    return {
        "project_id": project.id,
        "status": project.status.value if hasattr(project.status, "value") else project.status,
        "nodes": nodes,
        "links": links,
    }


# ─── helpers ───────────────────────────────────────────────────────────

async def _load_project(
    session: AsyncSession, project_id: str
) -> Project | None:
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
            selectinload(Project.links),
        )
    )
    result = await session.execute(stmt)
    return result.scalars().first()


def _iface_for_link(
    project: Project, link: ProjectLink
) -> tuple[ProjectInterface | None, ProjectInterface | None]:
    """Return (iface_a, iface_b) for a link, looking up by id."""
    iface_by_id: dict[str, ProjectInterface] = {}
    for n in project.nodes:
        for i in n.interfaces:
            iface_by_id[i.id] = i
    return iface_by_id.get(link.iface_a_id), iface_by_id.get(link.iface_b_id)


async def _set_error(
    session: AsyncSession,
    project: Project,
    result: LifecycleResult,
    op: str,
) -> None:
    project.status = ProjectStatus.ERROR
    await session.commit()
    result.status = "error"
    # Best-effort rollback: stop whatever we started so a retry
    # starts from a clean slate.
    try:
        for node in project.nodes:
            if node.container_id:
                try:
                    container_service.stop_container(node.container_id, timeout=2)
                    container_service.remove_container(node.container_id, force=True)
                except Exception:
                    pass
                node.container_id = None
                node.container_status = "error"
        for link in project.links:
            try:
                link_service.delete_bridge_for_link(
                    project_id=project.id, link_id=link.id
                )
            except Exception:
                pass
            link.docker_bridge_name = None
        await session.commit()
    except Exception:
        log.exception("[lifecycle] rollback after %s error failed", op)
