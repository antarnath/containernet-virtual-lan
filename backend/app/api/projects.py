"""REST endpoints for /api/projects (M4 5-primitive model).

Endpoints (see phases/milestone-4/phase_m4-01 §1.3 for the full list)
-----------------------------------------------------------------------
  POST   /api/projects                            create a project
  GET    /api/projects                            list projects (summary)
  GET    /api/projects/{id}                       fetch one + full canvas
  PATCH  /api/projects/{id}                       update name + viewport
  DELETE /api/projects/{id}                       delete (cascades)
  POST   /api/projects/{id}/nodes                 add a node
  GET    /api/projects/{id}/nodes/{node_id}       fetch one node
  PATCH  /api/projects/{id}/nodes/{node_id}       update name/pos/attack_mode
  DELETE /api/projects/{id}/nodes/{node_id}       delete (cascades)
  POST   /api/projects/{id}/nodes/{nid}/interfaces     add a port
  PATCH  /api/projects/{id}/interfaces/{iid}     update IP/name/mask
  DELETE /api/projects/{id}/interfaces/{iid}     delete (rejects if wired)
  POST   /api/projects/{id}/links                 wire two interfaces
  DELETE /api/projects/{id}/links/{lid}          unwire

  POST   /api/projects/{id}/start                phase 02 — 501
  POST   /api/projects/{id}/stop                 phase 02 — 501
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.models import AnomalyEvent, AttackSignal, NodeKind, ProjectNode
from app.services import (
    anomaly_detector,
    attack_detector,
    attack_proxy,
    communication_service,
    packet_service,
    project_lifecycle,
    project_service,
    realtime,
    route_resolver,
    router_proxy,
)

log = logging.getLogger(__name__)
from app.schemas.project import (
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectInterfaceCreateIn,
    ProjectInterfaceOut,
    ProjectInterfaceUpdateIn,
    ProjectLinkCreateIn,
    ProjectLinkOut,
    ProjectListResponse,
    ProjectNodeCreateIn,
    ProjectNodeOut,
    ProjectNodeUpdateIn,
    ProjectOut,
    ProjectUpdateIn,
)
from app.services import project_lifecycle, project_service
from app.services.project_service import (
    InterfaceIsWiredError,
    LinkEndpointsError,
    NodeHasLinksError,
    ProjectNotFoundError,
)


router = APIRouter(prefix="/projects", tags=["projects"])


# ─── helpers ──────────────────────────────────────────────────────────────

def _status_value(p) -> str:
    return p.status.value if hasattr(p.status, "value") else p.status


def _project_out(p) -> ProjectOut:
    # list_projects attaches _node_count / _link_count as transient
    # attributes. get_project and the create path don't, so we
    # fall back to len() in those cases.
    nc = getattr(p, "_node_count", None)
    lc = getattr(p, "_link_count", None)
    if nc is None:
        nc = len(p.nodes) if p.nodes else 0
    if lc is None:
        lc = len(p.links) if p.links else 0
    return ProjectOut(
        id=p.id,
        name=p.name,
        status=_status_value(p),
        viewport_x=p.viewport_x,
        viewport_y=p.viewport_y,
        viewport_zoom=p.viewport_zoom,
        node_count=nc,
        link_count=lc,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _iface_out(i) -> ProjectInterfaceOut:
    # The column has a TypeDecorator that should turn IPv4Address -> str,
    # but belt-and-braces: Pydantic demands a plain str, and some
    # asyncpg / SQLAlchemy edge cases hand us an IPv4Address object
    # directly. Force-stringify here so the response is always JSON-clean.
    ip = i.ip_address
    if ip is not None and not isinstance(ip, str):
        ip = str(ip)
    return ProjectInterfaceOut(
        id=i.id,
        node_id=i.node_id,
        name=i.name,
        ip_address=ip,
        subnet_mask=i.subnet_mask,
        mac_address=i.mac_address,
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


def _node_out(n) -> ProjectNodeOut:
    return ProjectNodeOut(
        id=n.id,
        project_id=n.project_id,
        name=n.name,
        kind=n.kind.value if hasattr(n.kind, "value") else n.kind,
        canvas_x=n.canvas_x,
        canvas_y=n.canvas_y,
        attack_mode=n.attack_mode,
        container_id=n.container_id,
        container_status=n.container_status,
        created_at=n.created_at,
        updated_at=n.updated_at,
        interfaces=[_iface_out(i) for i in (n.interfaces or [])],
    )


def _link_out(l) -> ProjectLinkOut:
    from app.schemas.project import ProjectCaptureOut
    cap = l.capture
    # The TypeDecorator should return str, but force-coerce here too in
    # case asyncpg / SQLAlchemy delivers an IPv4Network object instead.
    cidr = l.subnet_cidr
    if cidr is not None and not isinstance(cidr, str):
        cidr = str(cidr)
    return ProjectLinkOut(
        id=l.id,
        project_id=l.project_id,
        iface_a_id=l.iface_a_id,
        iface_b_id=l.iface_b_id,
        subnet_cidr=cidr,
        subnet_color_index=l.subnet_color_index,
        docker_bridge_name=l.docker_bridge_name,
        created_at=l.created_at,
        capture=ProjectCaptureOut(
            id=cap.id,
            link_id=cap.link_id,
            container_id=cap.container_id,
            status=cap.status,
            last_packet_at=cap.last_packet_at,
            packet_count=cap.packet_count,
        ) if cap else None,
    )


# ─── Project endpoints ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ProjectDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Create a new (empty) project. The canvas starts blank."""
    try:
        project = await project_service.create_project(session, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    project = await project_service.get_project(session, project.id)
    assert project is not None
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        nodes=[_node_out(n) for n in project.nodes],
        links=[_link_out(l) for l in project.links],
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(session: AsyncSession = Depends(get_session)):
    """Summary list, newest first. Includes node + link counts."""
    projects = await project_service.list_projects(session)
    return ProjectListResponse(
        projects=[_project_out(p) for p in projects],
        total=len(projects),
    )


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Full canvas: project + every node (with its interfaces) + every
    link (with its capture). This is what the React Flow canvas hydrates
    from on mount.
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        nodes=[_node_out(n) for n in project.nodes],
        links=[_link_out(l) for l in project.links],
    )


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    body: ProjectUpdateIn,
    session: AsyncSession = Depends(get_session),
):
    """Update name and/or viewport state. The canvas auto-saves viewport
    on every pan/zoom; users can rename the project here."""
    project = await project_service.update_project(session, project_id, body)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_out(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project. Cascades to all nodes, interfaces, links, captures."""
    deleted = await project_service.delete_project(session, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Node endpoints ───────────────────────────────────────────────────────

@router.post(
    "/{project_id}/nodes",
    response_model=ProjectNodeOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_node(
    project_id: str,
    body: ProjectNodeCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Drop a node on the canvas. Kind is required; name is auto-suggested."""
    try:
        node = await project_service.add_node(session, project_id, body)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Re-fetch with interfaces loaded
    node = await project_service.get_node(session, project_id, node.id)
    assert node is not None
    return _node_out(node)


@router.get("/{project_id}/nodes/{node_id}", response_model=ProjectNodeOut)
async def get_node(
    project_id: str,
    node_id: str,
    session: AsyncSession = Depends(get_session),
):
    node = await project_service.get_node(session, project_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return _node_out(node)


@router.patch(
    "/{project_id}/nodes/{node_id}",
    response_model=ProjectNodeOut,
)
async def update_node(
    project_id: str,
    node_id: str,
    body: ProjectNodeUpdateIn,
    session: AsyncSession = Depends(get_session),
):
    """Update a node's name, canvas position, or attack_mode. The canvas
    auto-saves position on every drag-end."""
    try:
        node = await project_service.update_node(
            session, project_id, node_id, body
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    node = await project_service.get_node(session, project_id, node_id)
    assert node is not None
    return _node_out(node)


@router.delete(
    "/{project_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_node(
    project_id: str,
    node_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a node. Returns 409 if any of its interfaces are wired."""
    try:
        deleted = await project_service.delete_node(
            session, project_id, node_id
        )
    except NodeHasLinksError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "link_ids": exc.link_ids,
            },
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="node not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Interface endpoints ─────────────────────────────────────────────────

@router.post(
    "/{project_id}/nodes/{node_id}/interfaces",
    response_model=ProjectInterfaceOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_interface(
    project_id: str,
    node_id: str,
    body: ProjectInterfaceCreateIn,
    session: AsyncSession = Depends(get_session),
):
    try:
        iface = await project_service.add_interface(
            session, project_id, node_id, body
        )
    except project_service.NodeNotFoundError:
        raise HTTPException(status_code=404, detail="node not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _iface_out(iface)


@router.patch(
    "/{project_id}/interfaces/{iface_id}",
    response_model=ProjectInterfaceOut,
)
async def update_interface(
    project_id: str,
    iface_id: str,
    body: ProjectInterfaceUpdateIn,
    session: AsyncSession = Depends(get_session),
):
    iface = await project_service.update_interface(
        session, project_id, iface_id, body
    )
    if iface is None:
        raise HTTPException(status_code=404, detail="interface not found")
    return _iface_out(iface)


@router.delete(
    "/{project_id}/interfaces/{iface_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_interface(
    project_id: str,
    iface_id: str,
    session: AsyncSession = Depends(get_session),
):
    try:
        deleted = await project_service.delete_interface(
            session, project_id, iface_id
        )
    except InterfaceIsWiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "link_ids": exc.link_ids,
            },
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="interface not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Link endpoints ───────────────────────────────────────────────────────

@router.post(
    "/{project_id}/links",
    response_model=ProjectLinkOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_link(
    project_id: str,
    body: ProjectLinkCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Wire two interfaces. The 1:1 capture row is created in the same
    transaction (status='idle', packet_count=0).
    """
    try:
        link = await project_service.add_link(session, project_id, body)
    except LinkEndpointsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Re-fetch with capture loaded
    from app.models import ProjectLink
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    stmt = (
        select(ProjectLink)
        .where(ProjectLink.id == link.id)
        .options(selectinload(ProjectLink.capture))
    )
    result = await session.execute(stmt)
    link = result.scalars().first()
    assert link is not None
    return _link_out(link)


@router.delete(
    "/{project_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_link(
    project_id: str,
    link_id: str,
    session: AsyncSession = Depends(get_session),
):
    deleted = await project_service.delete_link(
        session, project_id, link_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="link not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Lifecycle (phase 02) ─────────────────────────────────────────────

@router.post("/{project_id}/start")
async def start_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Materialize the project's nodes + wires as Docker containers
    and per-wire Linux bridges.

    Idempotent: a second call while the project is already running
    is a no-op. A call after a partial start resumes from wherever
    the previous run crashed.
    """
    try:
        result = await project_lifecycle.start_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.exception("[api] start_project failed for %s", project_id)
        raise HTTPException(status_code=500, detail=f"start failed: {exc}")
    if result.status == "error":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "start failed",
                "errors": result.errors,
                "started_nodes": result.started_nodes,
                "started_bridges": result.started_bridges,
            },
        )
    # Return the project detail so the UI can update its state.
    return await _detail_for(session, project_id)


@router.post("/{project_id}/stop")
async def stop_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Tear down the project's containers + bridges. Idempotent."""
    try:
        result = await project_lifecycle.stop_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.exception("[api] stop_project failed for %s", project_id)
        raise HTTPException(status_code=500, detail=f"stop failed: {exc}")
    return await _detail_for(session, project_id)


@router.post("/{project_id}/restart")
async def restart_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Stop + start. Used after editing the topology of a running project."""
    try:
        result = await project_lifecycle.restart_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.exception("[api] restart_project failed for %s", project_id)
        raise HTTPException(status_code=500, detail=f"restart failed: {exc}")
    if result.status == "error":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "restart failed",
                "errors": result.errors,
            },
        )
    return await _detail_for(session, project_id)


@router.get("/{project_id}/state")
async def get_project_state(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Per-project live state: node container statuses + per-link bridge
    info. Used by the canvas UI to colour status pills and surface
    start/stop errors."""
    try:
        return await project_lifecycle.project_state(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ─── Phase 04 — per-link packet stream (SSE) ─────────────────────────

@router.get("/{project_id}/links/{link_id}/packets/stream")
async def stream_link_packets(
    project_id: str,
    link_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Server-Sent Events stream of packet events for one wire.

    Each frame is ``data: <json>\\n\\n`` where <json> is a
    PacketEvent. Frames are flushed immediately so the browser's
    EventSource sees packets in real time. A comment line
    ``: keep-alive\\n\\n`` is sent every 15s to keep the connection
    open through intermediate proxies.

    The client closes the connection when the user navigates away;
    the streaming generator stops on its own when the file stops
    growing for too long (the capture container has been stopped).
    """
    # Validate the project + link exist (404 otherwise).
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    link_exists = any(l.id == link_id for l in project.links)
    if not link_exists:
        raise HTTPException(status_code=404, detail="link not found")

    stop_event = threading.Event()

    def event_stream():
        # Heartbeat thread: every 15s, push a comment so the
        # connection isn't closed by intermediaries.
        def heartbeat():
            while not stop_event.is_set():
                stop_event.wait(15.0)
                if stop_event.is_set():
                    return
                # The generator below handles its own writes; we
                # can't interleave with it from a different thread
                # without a queue, so we keep the heartbeat inline
                # below. This stub stays for clarity.
        # Inline heartbeat: we yield the comment every 15 packets
        # or every ~15s by tracking wall time.
        last_hb = datetime.now(timezone.utc)
        try:
            yield ": connected\n\n"
            for pkt in packet_service.sync_iter_packets(
                project_id, link_id, stop_event
            ):
                # Also broadcast over the project's WebSocket so the
                # canvas dot animation can pick it up.
                # NOTE: broadcast is async; fire-and-forget here.
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(
                            realtime.broadcast_project_event(
                                project_id,
                                {"type": "packet", **pkt},
                            )
                        )
                except Exception:
                    # No loop / already closed — best effort.
                    pass
                yield f"data: {json.dumps(pkt, separators=(',', ':'))}\n\n"
                now = datetime.now(timezone.utc)
                if (now - last_hb).total_seconds() >= 15.0:
                    yield ": keep-alive\n\n"
                    last_hb = now
        finally:
            stop_event.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )


@router.get("/{project_id}/packets/recent")
async def recent_packets(
    project_id: str,
    link_id: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Return the most recent N packets for a project (or one link).

    Used by the canvas to draw dot animations on the wires — a
    lightweight REST poll that complements the per-link SSE stream.
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    limit = max(1, min(limit, 200))
    return {
        "project_id": project_id,
        "link_id": link_id,
        "packets": packet_service.get_recent_packets(
            project_id, link_id, limit=limit
        ),
    }


# ─── Phase 03 — per-node live state + anomalies ──────────────────────

@router.get("/{project_id}/nodes/{node_id}/state")
async def get_node_state(
    project_id: str,
    node_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Live state for a single node.

    For a router, returns the cached or freshly-fetched routes /
    neigh / ifaces from the router agent (router_proxy). Also
    returns the list of open anomalies for the node.

    For a host / server / attacker, returns the container status
    (and any open anomalies). Phase 05 will add CPU / memory.

    For a switch, returns the container status (no live data in v1).
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    node = await project_service.get_node(session, project_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")

    kind = node.kind.value if hasattr(node.kind, "value") else node.kind

    # Anomalies (open + recent resolved) for this node.
    stmt = (
        select(AnomalyEvent)
        .where(AnomalyEvent.project_id == project_id)
        .where(AnomalyEvent.node_id == node_id)
        .order_by(AnomalyEvent.created_at.desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).scalars().all()
    anomalies = [
        {
            "id": r.id,
            "kind": r.kind,
            "severity": r.severity,
            "summary": r.summary,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
        for r in rows
    ]

    out: dict = {
        "node_id": node.id,
        "name": node.name,
        "kind": kind,
        "container_id": node.container_id,
        "container_status": node.container_status,
        "anomalies": anomalies,
    }

    if kind == NodeKind.ROUTER.value and node.container_id:
        state = await router_proxy.get_router_state(node.id, node.container_id)
        out["router"] = state.to_dict()
    else:
        out["router"] = None

    return out


@router.get("/{project_id}/anomalies")
async def list_anomalies(
    project_id: str,
    include_resolved: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """List anomalies for a project. By default, only open (un-resolved)."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    stmt = select(AnomalyEvent).where(AnomalyEvent.project_id == project_id)
    if not include_resolved:
        stmt = stmt.where(AnomalyEvent.resolved_at.is_(None))
    stmt = stmt.order_by(AnomalyEvent.created_at.desc()).limit(200)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "project_id": project_id,
        "anomalies": [
            {
                "id": r.id,
                "node_id": r.node_id,
                "kind": r.kind,
                "severity": r.severity,
                "summary": r.summary,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            }
            for r in rows
        ],
    }


@router.post("/{project_id}/anomalies/{anomaly_id}/dismiss")
async def dismiss_anomaly(
    project_id: str,
    anomaly_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Mark an anomaly as resolved. The underlying state change
    remains in the DB (for the logs view in phase 07) but the
    banner / canvas highlight disappears."""
    ev = (await session.execute(
        select(AnomalyEvent).where(
            AnomalyEvent.id == anomaly_id,
            AnomalyEvent.project_id == project_id,
        )
    )).scalars().first()
    if ev is None:
        raise HTTPException(status_code=404, detail="anomaly not found")
    if ev.resolved_at is None:
        ev.resolved_at = datetime.now(timezone.utc)
        await session.commit()
    return {"id": ev.id, "resolved_at": ev.resolved_at.isoformat()}


# ─── Phase 05 — Trigger & message console ───────────────────────────

@router.get("/{project_id}/route")
async def resolve_route(
    project_id: str,
    src: str,
    dst: str,
    session: AsyncSession = Depends(get_session),
):
    """Resolve the route from ``src`` (node id) to ``dst`` (IP).

    Returns ``{"hops": [Hop, ...]}`` on success. Returns 422
    with ``{"detail": {"error": "..."}}`` if the destination is
    unreachable, or 200 with ``{"error": "routing_loop",
    "visited": [...]}`` if a loop is detected.
    """
    try:
        hops = await route_resolver.resolve_route(
            session, project_id, src, dst
        )
    except route_resolver.RouteLoop as exc:
        return {
            "project_id": project_id,
            "src_node_id": src,
            "dst_ip": dst,
            "hops": [],
            "error": "routing_loop",
            "visited": exc.visited,
        }
    except route_resolver.RouteError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": str(exc.message), "src": src, "dst": dst},
        )
    return {
        "project_id": project_id,
        "src_node_id": src,
        "dst_ip": dst,
        "hops": [h.to_dict() for h in hops],
    }


@router.post("/{project_id}/communications")
async def send_communication(
    project_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """Send a message from one host to a destination IP.

    Body: ``{"src_node_id", "dst_ip", "protocol", "payload",
    "dst_node_id"?}``. Response: ``SendResult`` with
    ``comm_id, status, hops_crossed, delivered_at, error?``.
    """
    src_node_id = body.get("src_node_id")
    dst_ip = body.get("dst_ip")
    protocol = body.get("protocol", "HTTP")
    payload = body.get("payload", "")
    dst_node_id = body.get("dst_node_id")
    if not src_node_id or not dst_ip:
        raise HTTPException(
            status_code=400,
            detail="src_node_id and dst_ip are required",
        )
    try:
        result = await communication_service.send_message(
            session=session,
            project_id=project_id,
            src_node_id=src_node_id,
            dst_ip=dst_ip,
            protocol=protocol,
            payload=payload,
            dst_node_id=dst_node_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result.to_dict()


@router.get("/{project_id}/messages")
async def list_messages(
    project_id: str,
    node_id: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """Return the message history for a project (optionally
    filtered to a single node). Newest first."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    limit = max(1, min(limit, 500))
    rows = await communication_service.list_messages(
        session, project_id, node_id=node_id, limit=limit
    )
    return {"project_id": project_id, "node_id": node_id, "messages": rows}


# ─── Phase 07 — Logs view ────────────────────────────────────────────


@router.get("/{project_id}/events")
async def list_events(
    project_id: str,
    kind: list[str] | None = Query(default=None, description="Filter by event kind (repeatable)"),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """List project events (newest first) for the LogsView.

    The optional ``kind`` filter is multi-valued (?kind=anomaly&kind=attack_signal)
    so the filter chips can compose. ``cursor`` is the opaque id of the
    last event the client already has; the response returns strictly
    older events. Default page size 100, capped at 500.
    """
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    from app.models import ProjectEvent
    stmt = select(ProjectEvent).where(ProjectEvent.project_id == project_id)
    if kind:
        stmt = stmt.where(ProjectEvent.kind.in_(kind))
    if cursor:
        # Page by (created_at, id) so two events with the same
        # millisecond still have a stable order.
        anchor = (
            await session.execute(
                select(ProjectEvent).where(ProjectEvent.id == cursor)
            )
        ).scalars().first()
        if anchor is not None:
            stmt = stmt.where(
                (ProjectEvent.ts < anchor.ts)
                | ((ProjectEvent.ts == anchor.ts) & (ProjectEvent.id < anchor.id))
            )
    stmt = stmt.order_by(ProjectEvent.ts.desc(), ProjectEvent.id.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    return {
        "project_id": project_id,
        "events": [r.to_dict() for r in rows],
        "next_cursor": rows[-1].id if rows else None,
    }


@router.get("/{project_id}/events/stream")
async def stream_events(project_id: str):
    """Server-Sent Events of new project events.

    The first message is a ``hello`` marker so the client knows it's
    connected. Subsequent messages are JSON-serialised event payloads,
    one per ``type: "event"`` WS broadcast. The stream is
    unidirectional; the client is expected to also poll
    ``GET /events`` for backfill on mount / reconnect.
    """
    # Verify the project exists so 404 is surfaced cleanly.
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
    subscriber_id: str | None = None

    async def _event_iter():
        nonlocal subscriber_id
        from app.services import realtime
        subscriber_id = await realtime.subscribe(project_id, queue)
        # Push the hello marker so the client knows it's connected.
        await queue.put({"type": "hello", "project_id": project_id})
        try:
            # Initial comment so EventSource opens the connection.
            yield ": stream open\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Keep-alive comment.
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            if subscriber_id is not None:
                realtime.unsubscribe(project_id, subscriber_id)

    return StreamingResponse(
        _event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Phase 06 — Attacks view ─────────────────────────────────────────


@router.get("/{project_id}/attacks")
async def list_attacks(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List every attacker-kind node in the project, with its live
    engine state (fetched from :9092/state). Newest project order
    — the canvas adds new nodes; we don't sort here."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    out: list[dict] = []
    for n in project.nodes:
        kind_val = n.kind.value if hasattr(n.kind, "value") else n.kind
        if kind_val != NodeKind.ATTACKER.value:
            continue
        # Lazy import to avoid the docker-client cost on the hot path.
        state = await attack_proxy.attacker_state(n, session)
        out.append({
            "node_id": n.id,
            "name": n.name,
            "container_id": n.container_id,
            "container_status": n.container_status,
            "attack_mode": n.attack_mode,
            "state": state,
        })
    return {"project_id": project_id, "attacks": out}


@router.get("/{project_id}/attacks/{attacker_node_id}/signals")
async def list_attack_signals(
    project_id: str,
    attacker_node_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Newest-first signal log for one attacker. Capped at 200 rows
    for sanity; the frontend keeps a 50-row in-memory ring anyway."""
    limit = max(1, min(limit, 200))
    stmt = (
        select(AttackSignal)
        .where(
            AttackSignal.project_id == project_id,
            AttackSignal.attacker_node_id == attacker_node_id,
        )
        .order_by(AttackSignal.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "project_id": project_id,
        "attacker_node_id": attacker_node_id,
        "signals": [r.to_dict() for r in rows],
    }


@router.post("/{project_id}/attacks/{attacker_node_id}/start")
async def start_attack(
    project_id: str,
    attacker_node_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """Start the attacker's engine in the given mode against the
    given target IP. Body: {"mode": "<mode>", "target_ip": "<ip>"}.

    Validates that the attacker node is kind=attacker and has a
    running container. The proxy forwards to :9092/attack.
    """
    mode = body.get("mode")
    target_ip = body.get("target_ip")
    target_node_id = body.get("target_node_id")
    if not mode or not isinstance(mode, str):
        raise HTTPException(status_code=400, detail="mode required")
    # If target_node_id is given (preferred), resolve to its primary
    # interface IP. The user might pass target_ip directly for
    # advanced use (e.g. broadcasting to 10.255.255.255).
    if not target_ip and target_node_id:
        from sqlalchemy.orm import selectinload as _si
        stmt = (
            select(ProjectNode)
            .where(ProjectNode.id == target_node_id)
            .where(ProjectNode.project_id == project_id)
            .options(_si(ProjectNode.interfaces))
        )
        target_node = (await session.execute(stmt)).scalars().first()
        if target_node is None:
            raise HTTPException(
                status_code=404,
                detail=f"target_node_id {target_node_id} not found in project",
            )
        if not target_node.interfaces:
            raise HTTPException(
                status_code=422,
                detail="target node has no interfaces",
            )
        target_ip = target_node.interfaces[0].ip_address
    if not target_ip or not isinstance(target_ip, str):
        raise HTTPException(
            status_code=400,
            detail="target_ip or target_node_id required",
        )
    attacker = await _get_attacker_node(session, project_id, attacker_node_id)
    if attacker is None:
        raise HTTPException(
            status_code=404, detail="attacker not found in project"
        )
    if not attacker.container_id:
        raise HTTPException(
            status_code=409,
            detail="attacker container is not running — start the project first",
        )
    result = await attack_proxy.start_attack(attacker, mode, target_ip)
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"attacker rejected start: {result.get('error')}",
        )
    return result


@router.post("/{project_id}/attacks/{attacker_node_id}/stop")
async def stop_attack(
    project_id: str,
    attacker_node_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Stop the attacker's engine. No body."""
    attacker = await _get_attacker_node(session, project_id, attacker_node_id)
    if attacker is None:
        raise HTTPException(
            status_code=404, detail="attacker not found in project"
        )
    result = await attack_proxy.stop_attack(attacker)
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"attacker rejected stop: {result.get('error')}",
        )
    return result


async def _get_attacker_node(
    session: AsyncSession, project_id: str, attacker_node_id: str
):
    """Fetch the attacker node by id within the project, ensuring
    it's kind=attacker. Returns None if not found or wrong kind."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(ProjectNode)
        .where(
            ProjectNode.id == attacker_node_id,
            ProjectNode.project_id == project_id,
        )
        .options(selectinload(ProjectNode.interfaces))
    )
    node = (await session.execute(stmt)).scalars().first()
    if node is None:
        return None
    kind_val = node.kind.value if hasattr(node.kind, "value") else node.kind
    if kind_val != NodeKind.ATTACKER.value:
        return None
    return node


# ─── helpers ──────────────────────────────────────────────────────────

async def _detail_for(session: AsyncSession, project_id: str):
    """Build a ProjectDetailOut for a project. Used by start/stop/restart
    to return the up-to-date state in the same shape as GET /projects/{id}."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        nodes=[_node_out(n) for n in project.nodes],
        links=[_link_out(l) for l in project.links],
    )
