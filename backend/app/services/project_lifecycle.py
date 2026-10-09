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
from app.services import (
    anomaly_detector,
    attack_detector,
    container_service,
    event_service,
    link_service,
    node_service,
    packet_service,
    route_installer,
)

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

    # M4 phase 07 — first event: project is starting.
    await event_service.emit_lifecycle(
        session, project.id, state="starting", detail={"nodes": len(project.nodes), "links": len(project.links)},
    )

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
            # Persist the chosen bridge name + Docker network id on
            # the link row so the capture / router proxy can find
            # them later without re-deriving.
            link.docker_bridge_name = bridge.short_name
            link.docker_network_id = bridge.network_id
            result.started_bridges.append(bridge.network_id)
            # M4 phase 07 — bridge event.
            await event_service.emit_bridge_created(
                session,
                project.id,
                link_id=link.id,
                bridge_name=bridge.short_name,
                subnet_cidr=bridge.subnet_cidr,
            )
        except Exception as exc:
            result.errors.append(f"bridge {link.id}: {exc}")
            log.exception("[lifecycle] bridge create failed for link %s", link.id)
            await event_service.emit_error(
                session,
                project.id,
                summary=f"Bridge create failed: {exc}",
                detail={"link_id": link.id, "phase": "bridge_create"},
            )
            await _set_error(session, project, result, "start")
            return result

    # M4 phase 04 — per-link packet capture. Each spawned node
    # starts a background tcpdump on the interface it's attached
    # to for that link (see node_service.spawn_node). All nodes on
    # the same link write to the same NDJSON file
    # (/var/lib/containernet/captures/<proj8>l<link4>.ndjson)
    # concurrently; the SSE stream tails that file.
    #
    # We don't spawn a sidecar capture container any more — a
    # Linux bridge's fast-forward path bypasses AF_PACKET, so
    # tcpdump on the bridge itself never sees host→host unicast.
    # The node's veth, in the node's own netns, sees every frame
    # that crosses the link.
    #
    # Mark the link as "capture running" optimistically. The
    # actual tcpdump processes are tracked by the node containers
    # themselves; if one fails, the NDJSON file just stops growing
    # and the SSE stream sees a stall (which is the right UX).
    for link in project.links:
        if not link.docker_network_id or not link.docker_bridge_name:
            continue
        if link.capture is not None:
            # Sentinel value: we don't have a single container id
            # for the capture (it's distributed across the nodes).
            # The frontend treats any non-null container_id as
            # "capturing"; the actual NDJSON file is the source of
            # truth for the SSE stream.
            link.capture.container_id = f"node-driven:{project.id[:8]}:{link.id[:4]}"
            link.capture.status = "running"
    # Build the MAC table now (after all containers are up) so the
    # packet streamer can tag packets with the right src_node_kind.
    packet_service.invalidate_project(project.id)

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
            # M4 phase 07 — node_started event.
            await event_service.emit_node_started(
                session,
                project.id,
                node_id=node.id,
                node_name=node.name,
                node_kind=node.kind.value if hasattr(node.kind, "value") else str(node.kind),
            )
        except Exception as exc:
            result.errors.append(f"node {node.name}: {exc}")
            log.exception("[lifecycle] node spawn failed for %s", node.name)
            await event_service.emit_error(
                session,
                project.id,
                summary=f"Node {node.name!r} spawn failed: {exc}",
                detail={"node_id": node.id, "phase": "node_spawn"},
            )
            await _set_error(session, project, result, "start")
            return result

    # Step 3: success.
    project.status = ProjectStatus.RUNNING
    await session.commit()
    result.status = "running"
    # M4 phase 07 — lifecycle: running.
    await event_service.emit_lifecycle(
        session, project.id, state="running", detail={"nodes": len(result.started_nodes)},
    )
    # M4 phase 03 — start polling routers for ARP anomalies.
    anomaly_detector.start_polling(project.id)
    # M4 phase 06 — start polling attackers for signal detection.
    attack_detector.start_polling(project.id)
    # M4 phase 09 — install inter-router static routes so multi-router
    # topologies can reach each other's LANs. We do this AFTER status
    # flips to RUNNING so a failed install doesn't roll the whole
    # project back; the user can fix individual routes via the panel.
    try:
        await route_installer.install_inter_router_routes(project)
    except Exception:
        log.exception(
            "[lifecycle] route installation crashed for project %s",
            project.id,
        )
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

    # M4 phase 07 — first event: project is stopping.
    await event_service.emit_lifecycle(
        session, project.id, state="stopping", detail={"nodes": len(project.nodes)},
    )

    # M4 phase 04 — per-link captures are driven by the node
    # containers (each node tcpdumps the interface it's attached
    # to for that link). Stopping the node containers below also
    # stops the per-node tcpdumps. We just clear the link's
    # capture state here.
    for link in project.links:
        if link.capture is not None:
            link.capture.container_id = None
            link.capture.status = "idle"

    # Nodes first.
    for node in project.nodes:
        if node.container_id:
            try:
                container_service.stop_container(node.container_id, timeout=3)
                container_service.remove_container(node.container_id, force=True)
            except Exception as exc:
                result.errors.append(f"stop node {node.name}: {exc}")
                log.warning("[lifecycle] stop node %s: %s", node.name, exc)
                # Don't crash on this — best-effort stop.
            node.container_id = None
            node.container_status = "stopped"
            result.started_nodes.append(node.id)
            # M4 phase 07 — node_stopped event (after the container is
            # actually gone; the order doesn't matter to the timeline).
            await event_service.emit_node_stopped(
                session,
                project.id,
                node_id=node.id,
                node_name=node.name,
                node_kind=node.kind.value if hasattr(node.kind, "value") else str(node.kind),
            )

    # Then bridges.
    for link in project.links:
        try:
            link_service.delete_bridge_for_link(
                project_id=project.id, link_id=link.id
            )
            link.docker_bridge_name = None
            link.docker_network_id = None
            result.started_bridges.append(link.id)
        except Exception as exc:
            result.errors.append(f"delete bridge {link.id}: {exc}")
            log.warning("[lifecycle] delete bridge %s: %s", link.id, exc)

    # Drop the cached MAC table + recent-packets ring buffer.
    packet_service.invalidate_project(project.id)
    packet_service.reset_recent(project.id)

    project.status = ProjectStatus.STOPPED
    await session.commit()
    result.status = "stopped"
    # M4 phase 07 — lifecycle: stopped.
    await event_service.emit_lifecycle(
        session, project.id, state="stopped", detail={"stopped_nodes": len(result.started_nodes)},
    )
    # M4 phase 03 — stop the anomaly poller; the routers are gone.
    anomaly_detector.stop_polling(project.id)
    # M4 phase 06 — stop the attack signal poller.
    attack_detector.stop_polling(project.id)
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
        cap = link.capture
        links.append({
            "id": link.id,
            "iface_a_id": link.iface_a_id,
            "iface_b_id": link.iface_b_id,
            "docker_bridge_name": link.docker_bridge_name,
            "docker_network_id": link.docker_network_id,
            "subnet_cidr": link.subnet_cidr,
            "bridge": (
                {
                    "network_id": bridge.network_id,
                    "name": bridge.name,
                    "short_name": bridge.short_name,
                    "subnet_cidr": bridge.subnet_cidr,
                }
                if bridge else None
            ),
            "capture": (
                {
                    "id": cap.id,
                    "container_id": cap.container_id,
                    "status": cap.status,
                    "last_packet_at": cap.last_packet_at.isoformat() if cap.last_packet_at else None,
                    "packet_count": cap.packet_count,
                }
                if cap else None
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
    from app.models import ProjectCapture, ProjectLink
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
            selectinload(Project.links).selectinload(ProjectLink.capture),
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
    # M4 phase 07 — emit a lifecycle event for the error transition so
    # the LogsView shows "Project error" in the timeline. The detailed
    # cause was already emitted by the caller (e.g. "Bridge create
    # failed: ...").
    try:
        await event_service.emit_lifecycle(
            session,
            project.id,
            state=f"error ({op})",
            detail={"errors": result.errors},
        )
    except Exception:
        log.exception("[lifecycle] emit error event failed")
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
