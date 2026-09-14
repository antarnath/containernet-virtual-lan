"""Business logic for host tracking.

Phase 03 split
--------------
* If a heartbeat carries a ``project_id`` (from a spawned project host),
  we upsert into ``project_hosts`` keyed by ``(project_id, host_id)``.
* If no ``project_id`` is present (legacy static ``pc1/pc2/pc3``), we
  fall back to the legacy global ``hosts`` table.

Both paths publish a ``host_status_change`` WebSocket event so existing
frontend code keeps working unchanged.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Host,
    HostStatus,
    ProjectHost,
    ProjectHostStatus,
)
from app.schemas.heartbeat import HeartbeatIn
from app.ws import publish


ONLINE_THRESHOLD = timedelta(seconds=15)


def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


# ─── project-scoped heartbeat (Phase 03) ────────────────────────────────────

async def _upsert_project_heartbeat(
    session: AsyncSession, hb: HeartbeatIn
) -> ProjectHost | None:
    """Upsert a heartbeat into project_hosts. Returns the row (or None if
    the project_id is unknown to us — e.g. a host racing ahead of project
    creation)."""
    result = await session.execute(
        select(ProjectHost).where(
            ProjectHost.project_id == hb.project_id,
            ProjectHost.host_id == hb.host_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    previous_status = _status_str(row.status)
    row.status = ProjectHostStatus.ONLINE
    row.last_seen = datetime.now(timezone.utc)
    if hb.host_name:
        row.hostname = hb.host_name
    if hb.host_ip:
        row.ip_address = hb.host_ip

    await session.commit()
    await session.refresh(row)

    new_status = _status_str(row.status)
    if previous_status != new_status:
        publish("host_status_change", {
            "project_id": hb.project_id,
            "host_id": row.host_id,
            "status": new_status,
        })
    return row


# ─── legacy global heartbeat (Phase 02 backwards-compat) ───────────────────

async def _upsert_global_heartbeat(
    session: AsyncSession, hb: HeartbeatIn
) -> Host:
    """Legacy path: project_id is None. Hits the global ``hosts`` table."""
    result = await session.execute(select(Host).where(Host.host_id == hb.host_id))
    host = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    previous_status: str | None = None

    if host is None:
        host = Host(
            host_id=hb.host_id,
            hostname=hb.host_name,
            ip_address=hb.host_ip,
            status=HostStatus.ONLINE,
            last_seen=now,
        )
        session.add(host)
    else:
        previous_status = _status_str(host.status)
        host.hostname = hb.host_name
        host.ip_address = hb.host_ip
        host.status = HostStatus.ONLINE
        host.last_seen = now

    await session.commit()
    await session.refresh(host)

    new_status = _status_str(host.status)
    if previous_status != new_status:
        publish("host_status_change", {"host_id": host.host_id, "status": new_status})
    return host


# ─── entry point ────────────────────────────────────────────────────────────

async def upsert_heartbeat(session: AsyncSession, hb: HeartbeatIn) -> dict:
    """Mark a host as online. Routes by project_id if present.

    Returns a dict ``{kind, host_id, status, message}`` so the API layer
    can echo back a useful response regardless of which path was taken.
    """
    if hb.project_id:
        row = await _upsert_project_heartbeat(session, hb)
        if row is not None:
            return {
                "kind": "project",
                "host_id": row.host_id,
                "status": _status_str(row.status),
                "message": f"{row.hostname} marked {_status_str(row.status)} (project)",
            }
        # Project unknown — fall through to global path so a misconfigured
        # host at least shows up somewhere rather than being silently dropped.
    host = await _upsert_global_heartbeat(session, hb)
    return {
        "kind": "global",
        "host_id": host.host_id,
        "status": _status_str(host.status),
        "message": f"{host.hostname} marked {_status_str(host.status)} (global)",
    }


# ─── sweepers ───────────────────────────────────────────────────────────────

async def sweep_offline_hosts(session: AsyncSession) -> int:
    """Mark hosts offline if no heartbeat in 15+ seconds. Sweeps BOTH the
    legacy global table and the project-scoped table."""
    cutoff = datetime.now(timezone.utc) - ONLINE_THRESHOLD
    count = 0

    # Global hosts
    result = await session.execute(select(Host).where(Host.status == HostStatus.ONLINE))
    for host in result.scalars():
        if host.last_seen is None or host.last_seen < cutoff:
            host.status = HostStatus.OFFLINE
            count += 1
            publish("host_status_change", {"host_id": host.host_id, "status": "offline"})

    # Project hosts
    result = await session.execute(
        select(ProjectHost).where(ProjectHost.status == ProjectHostStatus.ONLINE)
    )
    for row in result.scalars():
        if row.last_seen is None or row.last_seen < cutoff:
            row.status = ProjectHostStatus.OFFLINE
            count += 1
            publish("host_status_change", {
                "project_id": row.project_id,
                "host_id": row.host_id,
                "status": "offline",
            })

    if count:
        await session.commit()
    return count


# ─── reads ──────────────────────────────────────────────────────────────────

async def list_hosts(session: AsyncSession) -> list[Host]:
    """Return legacy global hosts ordered by creation time."""
    result = await session.execute(select(Host).order_by(Host.created_at))
    return list(result.scalars())


async def list_project_hosts(session: AsyncSession, project_id: str) -> list[ProjectHost]:
    """Return hosts for a project, ordered by host_id."""
    result = await session.execute(
        select(ProjectHost)
        .where(ProjectHost.project_id == project_id)
        .order_by(ProjectHost.host_id)
    )
    return list(result.scalars())


async def get_project_host(
    session: AsyncSession, project_id: str, host_id: str
) -> ProjectHost | None:
    """Fetch a single ProjectHost by (project_id, host_id). None if not found."""
    result = await session.execute(
        select(ProjectHost).where(
            ProjectHost.project_id == project_id,
            ProjectHost.host_id == host_id,
        )
    )
    return result.scalar_one_or_none()


async def list_all_projects_hosts(session: AsyncSession) -> list[ProjectHost]:
    """Flat list of every ProjectHost across every project. Used by the legacy
    dashboard during the transition. Returns the rows ordered by
    (project_id, host_id) for stable pagination."""
    result = await session.execute(
        select(ProjectHost).order_by(ProjectHost.project_id, ProjectHost.host_id)
    )
    return list(result.scalars())


async def get_topology(session: AsyncSession) -> dict:
    """Legacy: build the static 3-node topology from global hosts."""
    hosts = await list_hosts(session)
    nodes = [
        {
            "id": h.host_id,
            "label": h.hostname,
            "ip": h.ip_address,
            "status": _status_str(h.status),
        }
        for h in hosts
    ]
    edges = []
    for i, src in enumerate(nodes):
        for dst in nodes[i + 1 :]:
            edges.append({"source": src["id"], "target": dst["id"]})
    return {"nodes": nodes, "edges": edges}
