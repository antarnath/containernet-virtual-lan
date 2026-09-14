"""Communication orchestrator — Phase 06.

Project-Scoped Communication
----------------------------
A communication is always between two hosts of THE SAME project. The
service refuses to dispatch if source or destination doesn't belong to
the project, and persists the row with the ``project_id`` so the log
filter on the frontend naturally isolates one project from another.

WebSocket events carry the same ``project_id`` so the frontend can drop
events from projects the user isn't viewing (cross-project isolation).

Steps for ``trigger_communication(project_id, ...)``
    1. Validate the project exists.
    2. Look up source + destination as ProjectHost rows. Raise 400 if
       either is missing or doesn't belong to this project.
    3. Refuse to dispatch if either host has no container_id (project
       not started yet).
    4. Insert a Communication row with status=PENDING.
    5. Publish ``communication_start`` over WebSocket.
    6. POST the source host agent's ``/send`` endpoint (which then opens
       a fresh connection to the destination's ``/receive``).
    7. Time the round-trip; mark DELIVERED or FAILED; persist latency.
    8. Publish ``communication_complete`` over WebSocket.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from docker.errors import APIError, NotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docker_client import get_docker_client
from app.models import (
    CommStatus,
    Communication,
    Project,
    ProjectHost,
)
from app.schemas.communication import CommunicationCreateIn
from app.services import host_service
from app.ws import publish_to_project

AGENT_SEND_TIMEOUT = 5.0  # seconds

# The Docker bridge the backend is attached to. Spawned host containers are
# also attached here so they can DNS-resolve ``backend:8000`` for heartbeats
# AND so the backend can reach them on this network for the comm dispatch.
# Must match `BACKEND_NETWORK` in project_service.py (the compose-prefixed
# network name). Kept as a constant here so the orchestrator works without
# an import cycle.
BACKEND_NETWORK_NAME = "containernet_containernet_lan"


def _resolve_backend_lan_ip(container_id: str | None) -> str | None:
    """Return the IP a host container has on the backend's LAN bridge, or
    ``None`` if the container is missing / not attached. Used by the
    orchestrator so the backend's POST to ``/send`` reaches the agent
    without being blocked by per-project bridge isolation."""
    if not container_id:
        return None
    try:
        c = get_docker_client().containers.get(container_id)
        c.reload()
        nets = (c.attrs.get("NetworkSettings") or {}).get("Networks") or {}
        entry = nets.get(BACKEND_NETWORK_NAME)
        if entry and entry.get("IPAddress"):
            return entry["IPAddress"]
    except (NotFound, APIError):
        return None
    except Exception:
        return None
    return None


def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


def _serialize(comm: Communication) -> dict[str, Any]:
    """Communication row -> JSON-friendly dict (for WS events)."""
    return {
        "id": comm.id,
        "project_id": comm.project_id,
        "source_host_id": comm.source_host_id,
        "dest_host_id": comm.dest_host_id,
        "protocol": comm.protocol,
        "payload": comm.payload,
        "data_size": comm.data_size,
        "latency_ms": comm.latency_ms,
        "status": _status_str(comm.status),
        "timestamp": comm.timestamp.isoformat() if comm.timestamp else None,
    }


# ─── reads ──────────────────────────────────────────────────────────────────

async def list_project_communications(
    session: AsyncSession, project_id: str, limit: int = 100
) -> list[Communication]:
    """Return the most-recent communications for ONE project."""
    result = await session.execute(
        select(Communication)
        .where(Communication.project_id == project_id)
        .order_by(Communication.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def get_project_communication(
    session: AsyncSession, project_id: str, comm_id: str
) -> Communication | None:
    """Fetch one communication by (project_id, id)."""
    result = await session.execute(
        select(Communication).where(
            Communication.project_id == project_id,
            Communication.id == comm_id,
        )
    )
    return result.scalar_one_or_none()


async def list_all_communications(
    session: AsyncSession, limit: int = 100
) -> list[Communication]:
    """Legacy flat listing (no project scope). Kept during transition."""
    result = await session.execute(
        select(Communication)
        .order_by(Communication.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def list_recent_communications(
    session: AsyncSession, limit: int = 20
) -> list[Communication]:
    """Phase 09 — most-recent comms across every project. Used by the
    dashboard's "Recent Activity" feed."""
    return await list_all_communications(session, limit=limit)


# ─── trigger ────────────────────────────────────────────────────────────────

async def trigger_communication(
    session: AsyncSession, project_id: str, data: CommunicationCreateIn
) -> Communication:
    """Dispatch a host-to-host message inside the given project.

    Raises ``ValueError`` with a clear message on any validation failure
    (unknown project, unknown source/destination, host not running).
    The API layer translates ValueError -> HTTP 400.
    """

    # 1. Project must exist
    proj_res = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    if proj_res.scalar_one_or_none() is None:
        raise ValueError(f"unknown project: {project_id}")

    # 2. Resolve source and destination — scoped to THIS project.
    src = await host_service.get_project_host(
        session, project_id, data.source_host_id
    )
    if src is None:
        raise ValueError(
            f"unknown source host {data.source_host_id!r} in project {project_id}"
        )

    dst = await host_service.get_project_host(
        session, project_id, data.destination_host_id
    )
    if dst is None:
        raise ValueError(
            f"unknown destination host {data.destination_host_id!r} in project {project_id}"
        )

    # 3. Both hosts must have a running container.
    if not src.container_id or not dst.container_id:
        raise ValueError(
            "one or both hosts are not running (project not started?)"
        )

    # 4. Create the row in PENDING state.
    comm = Communication(
        project_id=project_id,
        source_host_id=data.source_host_id,
        dest_host_id=data.destination_host_id,
        protocol=data.protocol,
        payload=data.payload,
        data_size=len(data.payload.encode("utf-8")),
        status=CommStatus.PENDING,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(comm)
    await session.commit()
    await session.refresh(comm)

    # 5. Emit "start" event scoped to the project — the frontend hook only
    # receives this if its socket is subscribed to the same project_id.
    publish_to_project(
        str(comm.project_id),
        "communication_start",
        {
            "id": comm.id,
            "source_host_id": comm.source_host_id,
            "dest_host_id": comm.dest_host_id,
            "protocol": comm.protocol,
            "payload": comm.payload,
        },
    )

    # 6. Dispatch to the source host agent's /send endpoint. The agent
    #    then opens a NEW connection to the destination's /receive.
    #
    #    The source host's `src.ip_address` is its project-bridge IP (e.g.
    #    10.80.0.11) which is ONLY reachable from inside the project bridge.
    #    The backend isn't on that bridge, so it resolves the agent's
    #    containernet_lan IP via a quick Docker inspect on the container.
    #    Falls back to `src.ip_address` (which will time out) if the
    #    container no longer exists, so callers always get a deterministic
    #    error rather than a crash.
    src_agent_ip = _resolve_backend_lan_ip(src.container_id) or src.ip_address
    dispatch_url = f"http://{src_agent_ip}:8080/send"
    dispatch_body = {
        "comm_id": comm.id,
        "project_id": str(project_id),
        "target_host_id": dst.host_id,
        "target_ip": dst.ip_address,
        "payload": data.payload,
        "protocol": data.protocol,
    }

    start = datetime.now(timezone.utc)
    status = CommStatus.FAILED
    error_msg: str | None = None
    try:
        async with httpx.AsyncClient(timeout=AGENT_SEND_TIMEOUT) as client:
            resp = await client.post(dispatch_url, json=dispatch_body)
            try:
                body = resp.json()
            except Exception:
                body = {}
            agent_status = body.get("status") if isinstance(body, dict) else None
            if 200 <= resp.status_code < 300 and agent_status == "sent":
                status = CommStatus.DELIVERED
            else:
                error_msg = (
                    body.get("error")
                    if isinstance(body, dict) and body.get("error")
                    else f"agent returned HTTP {resp.status_code}"
                )
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0

    # 7. Update row with final status + latency.
    comm.status = status
    comm.latency_ms = round(elapsed_ms, 2)
    await session.commit()
    await session.refresh(comm)

    if error_msg:
        print(
            f"[orchestrator] {project_id} {data.source_host_id} -> "
            f"{data.destination_host_id} FAILED after {comm.latency_ms}ms: {error_msg}"
        )
    else:
        print(
            f"[orchestrator] {project_id} {data.source_host_id} -> "
            f"{data.destination_host_id} delivered in {comm.latency_ms}ms"
        )

    # 8. Emit "complete" event scoped to the project — only subscribers
    # of this project_id receive the final latency / status update.
    publish_to_project(str(comm.project_id), "communication_complete", _serialize(comm))

    return comm
