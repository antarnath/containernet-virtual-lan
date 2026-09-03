"""Business logic for host tracking."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Host, HostStatus
from app.schemas.heartbeat import HeartbeatIn
from app.ws import publish


ONLINE_THRESHOLD = timedelta(seconds=15)


def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


async def upsert_heartbeat(session: AsyncSession, hb: HeartbeatIn) -> Host:
    """Mark a host as online. Auto-register if it is the first heartbeat."""
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

    # Emit event only on transition (skip the steady-state heartbeat spam).
    new_status = _status_str(host.status)
    if previous_status != new_status:
        publish(
            "host_status_change",
            {"host_id": host.host_id, "status": new_status},
        )

    return host


async def sweep_offline_hosts(session: AsyncSession) -> int:
    """Mark hosts as offline if they have not sent a heartbeat recently."""
    cutoff = datetime.now(timezone.utc) - ONLINE_THRESHOLD
    result = await session.execute(select(Host).where(Host.status == HostStatus.ONLINE))
    count = 0
    for host in result.scalars():
        if host.last_seen is None or host.last_seen < cutoff:
            host.status = HostStatus.OFFLINE
            count += 1
            publish(
                "host_status_change",
                {"host_id": host.host_id, "status": _status_str(host.status)},
            )
    if count:
        await session.commit()
    return count


async def list_hosts(session: AsyncSession) -> list[Host]:
    """Return all hosts ordered by creation time."""
    result = await session.execute(select(Host).order_by(Host.created_at))
    return list(result.scalars())


async def get_topology(session: AsyncSession) -> dict:
    """Build nodes + edges for the future topology view."""
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