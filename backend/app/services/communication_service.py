"""Communication service — M4 phase 05.

Sends a message from one host to another (or to a free-form IP)
by POSTing to the source host's host-agent ``/send`` endpoint.
The agent then opens a NEW HTTP connection to the destination
host's ``/receive`` and we get back the result.

The service is the *only* place the backend initiates a
message. The frontend never talks to a host-agent directly
— the backend sits in the middle for two reasons:
  1. It can enrich the request with project_id, src_node_id,
     and the resolved route (so the agent can verify it).
  2. It captures the result + timing and surfaces it as a
     ``Communication`` row + a websocket event so the canvas
     + message console can highlight the crossing in real
     time.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Communication,
    NodeKind,
    Project,
    ProjectNode,
)
from app.services import realtime, route_resolver

log = logging.getLogger(__name__)


# ─── result shape ────────────────────────────────────────────────────

@dataclass
class SendResult:
    comm_id: str
    status: str  # "delivered" | "failed" | "unreachable"
    delivered_at: str | None
    hops_crossed: list[str]  # link_ids, in order
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "comm_id": self.comm_id,
            "status": self.status,
            "delivered_at": self.delivered_at,
            "hops_crossed": self.hops_crossed,
            "error": self.error,
        }


# ─── public entry point ─────────────────────────────────────────────

async def send_message(
    session: AsyncSession,
    project_id: str,
    src_node_id: str,
    dst_ip: str,
    protocol: str,
    payload: str,
    *,
    dst_node_id: str | None = None,
) -> SendResult:
    """Send ``payload`` from ``src_node_id`` to ``dst_ip``.

    1. Validates that ``src_node_id`` is a host in the project.
    2. Resolves the route (so we can include the hop list in
       the response + broadcast).
    3. POSTs to the source host's ``/send`` agent endpoint.
    4. Records a ``Communication`` row in the DB.
    5. Broadcasts a ``message`` event on the project WS.
    """
    project = await _load_project(session, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} not found")

    src_node = _node_by_id(project, src_node_id)
    if src_node is None:
        raise ValueError(f"source node {src_node_id!r} not in project")
    if _kind(src_node) not in (NodeKind.HOST, NodeKind.SERVER, NodeKind.ATTACKER):
        raise ValueError(
            f"source node {src_node.name!r} is kind={_kind(src_node).value}; "
            f"only host / server / attacker can send messages"
        )

    # Pick dst_node_id from the project if it's an interface on
    # a known host. Otherwise leave None (the agent will fall back
    # to plain IP).
    if dst_node_id is None:
        for n in project.nodes:
            for i in n.interfaces:
                if i.ip_address == dst_ip:
                    dst_node_id = n.id
                    break
            if dst_node_id:
                break

    # Resolve the route. The frontend asked for it via /route but
    # we re-resolve here so the response + the websocket event
    # both include the canonical hop list (and so the server is
    # the source of truth even if the client was stale).
    try:
        hops = await route_resolver.resolve_route(
            session, project_id, src_node_id, dst_ip
        )
        hop_link_ids = [h.link_id for h in hops if h.link_id]
    except route_resolver.RouteError as exc:
        return SendResult(
            comm_id=str(uuid.uuid4()),
            status="unreachable",
            delivered_at=None,
            hops_crossed=[],
            error=str(exc),
        )

    comm_id = str(uuid.uuid4())
    # Use the IP the source node has on the backend-facing network
    # (containernet_lan), not the topology IP. The host agent listens
    # on every interface, but the backend container can only reach
    # the node via the shared backend network. Looking at the
    # container's actual IP gives us that. Fall back to the first
    # topology IP for callers that don't have docker access (tests).
    src_iface_ip = _backend_lan_ip(src_node) or _primary_iface_ip(src_node)
    if not src_iface_ip:
        return SendResult(
            comm_id=comm_id,
            status="failed",
            delivered_at=None,
            hops_crossed=hop_link_ids,
            error=f"source node {src_node.name!r} has no IP",
        )

    # POST to the source host's /send endpoint. The agent
    # (running on its :8080 inside the container) does the
    # actual delivery to dst_ip:8080/receive.
    body = {
        "comm_id": comm_id,
        "project_id": project_id,
        "target_ip": dst_ip,
        "target_host_id": dst_node_id or "",
        "payload": payload,
        "protocol": protocol,
    }
    url = f"http://{src_iface_ip}:8080/send"

    delivered_at_iso: str | None = None
    error: str | None = None
    status = "failed"
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as http:
            async with http.post(url, json=body) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    status = "delivered"
                    delivered_at_iso = (
                        _now_iso()
                    )
                else:
                    status = "failed"
                    error = f"host agent returned {resp.status}: {text[:200]}"
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"

    # Persist a row so the message console can show history.
    try:
        comm = Communication(
            id=comm_id,
            project_id=project_id,
            src_node_id=src_node_id,
            dst_node_id=dst_node_id,
            dst_ip=dst_ip,
            protocol=protocol,
            payload=payload,
            status=status,
            hops_count=len(hop_link_ids),
            delivered_at=_parse_iso(delivered_at_iso) if delivered_at_iso else None,
        )
        session.add(comm)
        await session.commit()
    except Exception as exc:
        log.warning("[comm] could not persist Communication row: %s", exc)

    # Broadcast over the project WS so the wire view can highlight
    # the hops + the message console can show the bubble.
    try:
        await realtime.broadcast_project_event(
            project_id,
            {
                "type": "message",
                "comm_id": comm_id,
                "src_node_id": src_node_id,
                "src_node_name": src_node.name,
                "dst_node_id": dst_node_id,
                "dst_ip": dst_ip,
                "protocol": protocol,
                "payload": payload,
                "status": status,
                "hops_crossed": hop_link_ids,
                "delivered_at": delivered_at_iso,
            },
        )
    except Exception as exc:
        log.debug("[comm] broadcast failed (non-fatal): %s", exc)

    # M4 phase 07 — write to the unified project_events log so the
    # LogsView shows this message in the same timeline.
    try:
        from app.services import event_service
        await event_service.emit_message_sent(
            session,
            project_id,
            src_node_id=src_node_id,
            src_node_name=src_node.name,
            dst_node_id=dst_node_id or "",
            dst_node_name=dst_node.name if dst_node else dst_ip,
            protocol=protocol,
            detail_extra={
                "comm_id": comm_id,
                "status": status,
                "dst_ip": dst_ip,
                "hops_count": len(hop_link_ids),
                "payload_size": len(payload or "") if isinstance(payload, str) else None,
            },
        )
    except Exception:
        log.exception("[comm] failed to emit project_event for message %s", comm_id)

    return SendResult(
        comm_id=comm_id,
        status=status,
        delivered_at=delivered_at_iso,
        hops_crossed=hop_link_ids,
        error=error,
    )


# ─── queries ────────────────────────────────────────────────────────

async def list_messages(
    session: AsyncSession,
    project_id: str,
    node_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return the message history for a project, optionally
    filtered to messages that touch ``node_id`` (either as src
    or dst). Newest first."""
    from sqlalchemy import desc, select

    from app.models import Communication

    stmt = (
        select(Communication)
        .where(Communication.project_id == project_id)
        .order_by(desc(Communication.created_at))
        .limit(limit)
    )
    if node_id is not None:
        stmt = stmt.where(
            (Communication.src_node_id == node_id)
            | (Communication.dst_node_id == node_id)
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [_comm_to_dict(r) for r in rows]


# ─── helpers ────────────────────────────────────────────────────────

def _comm_to_dict(c: Communication) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "src_node_id": c.src_node_id,
        "dst_node_id": c.dst_node_id,
        "dst_ip": c.dst_ip,
        "protocol": c.protocol,
        "payload": c.payload,
        "status": c.status,
        "hops_count": c.hops_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "delivered_at": c.delivered_at.isoformat() if c.delivered_at else None,
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str):
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _kind(node: ProjectNode):
    if isinstance(node.kind, NodeKind):
        return node.kind
    return NodeKind(node.kind)


def _node_by_id(project: Project, node_id: str) -> ProjectNode | None:
    for n in project.nodes:
        if n.id == node_id:
            return n
    return None


def _primary_iface_ip(node: ProjectNode) -> str | None:
    """Return the first non-empty iface IP. Used as the source
    of the agent's HTTP request (the agent listens on every
    interface, so any works)."""
    for i in node.interfaces:
        if i.ip_address:
            return i.ip_address
    return None


def _backend_lan_ip(node: ProjectNode) -> str | None:
    """Return the source node's IP on the BACKEND network (the
    bridge the backend container is on).

    The host agent listens on every interface, but the backend can
    only reach the host via the shared backend network (e.g.
    ``containernet_containernet_lan``). The IP the host has on its
    user-drawn link bridge is NOT routable from the backend.

    Returns ``None`` if the node has no container or no IP on the
    backend network; caller falls back to the topology IP.
    """
    container_id = getattr(node, "container_id", None)
    if not container_id:
        return None
    try:
        from app.core.config import settings
        from app.core.docker_client import get_docker_client

        client = get_docker_client()
        c = client.containers.get(container_id)
        nets = c.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
        # Preferred: the explicit backend network.
        pref = nets.get(settings.BACKEND_NETWORK) or {}
        if pref.get("IPAddress"):
            return pref["IPAddress"]
        # Fall back: any attached network with an IP. The first one
        # is usually the default docker bridge, which the backend
        # can also reach (it's the standard inter-container bridge).
        for _name, info in nets.items():
            if info.get("IPAddress"):
                return info["IPAddress"]
    except Exception:
        return None
    return None


async def _load_project(
    session: AsyncSession, project_id: str
) -> Project | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Project, ProjectNode

    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
        )
    )
    return (await session.execute(stmt)).scalars().first()
