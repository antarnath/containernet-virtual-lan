"""Communications API — Phase 06.

Per-project endpoints (preferred):
  POST /api/projects/{project_id}/communications
  GET  /api/projects/{project_id}/communications
  GET  /api/projects/{project_id}/communications/{comm_id}

Legacy global endpoints (deprecated, kept for transition):
  POST /api/communications
  GET  /api/communications
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.communication import (
    CommunicationCreateIn,
    CommunicationListResponse,
    CommunicationOut,
)
from app.services import communication_service


# Two routers — one per prefix.
project_router = APIRouter(prefix="/projects", tags=["communications (per project)"])
legacy_router = APIRouter(prefix="/communications", tags=["communications (legacy)"])


def _to_out(c) -> CommunicationOut:
    return CommunicationOut(
        id=c.id,
        project_id=c.project_id,
        source_host_id=c.source_host_id,
        dest_host_id=c.dest_host_id,
        protocol=c.protocol,
        payload=c.payload,
        data_size=c.data_size,
        latency_ms=c.latency_ms,
        status=c.status.value if hasattr(c.status, "value") else c.status,
        timestamp=c.timestamp,
    )


# ─── Per-project (Phase 06) ─────────────────────────────────────────────────

@project_router.post(
    "/{project_id}/communications",
    response_model=CommunicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_project_communication(
    project_id: str,
    body: CommunicationCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Dispatch a host-to-host message inside the given project."""
    try:
        comm = await communication_service.trigger_communication(
            session, project_id, body
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_out(comm)


@project_router.get(
    "/{project_id}/communications",
    response_model=CommunicationListResponse,
)
async def list_project_communications(
    project_id: str,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """Return the most-recent communications for the given project."""
    comms = await communication_service.list_project_communications(
        session, project_id, limit=limit
    )
    out = [_to_out(c) for c in comms]
    return CommunicationListResponse(communications=out, total=len(out))


@project_router.get(
    "/{project_id}/communications/{comm_id}",
    response_model=CommunicationOut,
)
async def get_project_communication(
    project_id: str,
    comm_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Fetch one communication by (project_id, id)."""
    comm = await communication_service.get_project_communication(
        session, project_id, comm_id
    )
    if comm is None:
        raise HTTPException(status_code=404, detail="communication not found")
    return _to_out(comm)


# ─── Legacy global (deprecated, kept during transition) ────────────────────

@legacy_router.post("", response_model=CommunicationOut, deprecated=True)
async def trigger_legacy_comm(
    data: CommunicationCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Legacy endpoint — operates on the legacy global `hosts` table only.

    .. deprecated::
        Use ``POST /api/projects/{project_id}/communications`` instead. This
        endpoint will be removed once all clients have migrated.
    """
    # Reuse the Phase-01 service path if you need the old behaviour.
    # For now, return 410 Gone so callers are forced to migrate.
    raise HTTPException(
        status_code=410,
        detail=(
            "legacy /api/communications removed — use "
            "POST /api/projects/{project_id}/communications"
        ),
    )


@legacy_router.get("", response_model=CommunicationListResponse, deprecated=True)
async def list_legacy_comms(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """Legacy listing — still works (flat across all projects).

    .. deprecated::
        Use ``GET /api/projects/{project_id}/communications`` instead.
    """
    comms = await communication_service.list_all_communications(
        session, limit=limit
    )
    out = [_to_out(c) for c in comms]
    return CommunicationListResponse(communications=out, total=len(out))
