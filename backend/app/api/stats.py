"""Platform-wide summary stats — Phase 09.

The dashboard's "Overview" page polls this endpoint every 5 seconds. It
returns aggregates across every project + the most recent communications
so the activity feed is always fresh.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.services import (
    communication_service,
    host_service,
    project_service,
)


router = APIRouter(prefix="/stats", tags=["stats"])


def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


def _serialize_comm(c) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "source_host_id": c.source_host_id,
        "dest_host_id": c.dest_host_id,
        "protocol": c.protocol,
        "payload": c.payload,
        "status": _status_str(c.status),
        "latency_ms": c.latency_ms,
        "timestamp": c.timestamp.isoformat() if c.timestamp else None,
    }


@router.get("/summary")
async def summary(
    limit_recent: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """Aggregate platform stats + the most-recent N communications."""
    projects = await project_service.list_projects(session)

    total_hosts = 0
    online_hosts = 0
    offline_hosts = 0
    running_projects = 0
    stopped_projects = 0
    other_projects = 0
    for p in projects:
        status = _status_str(p.status)
        if status == "running":
            running_projects += 1
        elif status == "stopped":
            stopped_projects += 1
        else:
            other_projects += 1
        hosts = await host_service.list_project_hosts(session, p.id)
        total_hosts += len(hosts)
        for h in hosts:
            hs = _status_str(h.status)
            if hs == "online":
                online_hosts += 1
            elif hs == "offline":
                offline_hosts += 1

    recent = await communication_service.list_recent_communications(
        session, limit=limit_recent
    )

    return {
        "projects": {
            "total": len(projects),
            "running": running_projects,
            "stopped": stopped_projects,
            "other": other_projects,
        },
        "hosts": {
            "total": total_hosts,
            "online": online_hosts,
            "offline": offline_hosts,
        },
        "recent_communications": [_serialize_comm(c) for c in recent],
    }