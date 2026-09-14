"""Messages API — Phase 08.

Per-project, per-host endpoints:

  POST   /api/projects/{project_id}/hosts/{host_id}/messages   — agent ingests
  GET    /api/projects/{project_id}/hosts/{host_id}/messages   — history fetch
  GET    /api/projects/{project_id}/messages                   — every host of the project
  DELETE /api/projects/{project_id}/messages                   — wipe the project

The POST endpoint is what the host agent's ``message_reporter`` calls.
We validate that ``host_id`` belongs to ``project_id`` so a misconfigured
agent at least fails with a clear 404 instead of silently writing into
the wrong bucket.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.message import MessageIn, MessageListResponse, MessageOut
from app.services import host_service, message_service


router = APIRouter(prefix="/projects", tags=["messages (per host)"])


def _to_out(m) -> MessageOut:
    direction = m.direction.value if hasattr(m.direction, "value") else str(m.direction)
    return MessageOut(
        id=m.id,
        project_id=str(m.project_id),
        host_id=m.host_id,
        direction=direction,
        peer_host_id=m.peer_host_id,
        comm_id=m.comm_id,
        payload=m.payload,
        protocol=m.protocol,
        timestamp=m.timestamp,
    )


@router.post(
    "/{project_id}/hosts/{host_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest(
    project_id: str,
    host_id: str,
    body: MessageIn,
    session: AsyncSession = Depends(get_session),
):
    """Ingest a single message event from the host agent.

    Raises 404 if the host doesn't belong to the project — protects against
    misconfigured agents writing into the wrong scope.
    """
    host = await host_service.get_project_host(session, project_id, host_id)
    if host is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown host {host_id!r} in project {project_id}",
        )
    try:
        row = await message_service.record_message(session, project_id, host_id, body)
    except Exception as exc:
        # Persisting a message row should never break the agent's send/receive
        # flow, but on this side we're already inside an HTTP handler — there's
        # no caller to silently continue. Surface the error.
        raise HTTPException(status_code=500, detail=f"failed to record message: {exc}")
    return _to_out(row)


@router.get(
    "/{project_id}/hosts/{host_id}/messages",
    response_model=MessageListResponse,
)
async def history(
    project_id: str,
    host_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Return the most-recent ``limit`` messages for this host."""
    rows = await message_service.list_project_host_messages(
        session, project_id, host_id, limit=limit
    )
    out = [_to_out(r) for r in rows]
    return MessageListResponse(messages=out, total=len(out))


@router.get(
    "/{project_id}/messages",
    response_model=MessageListResponse,
)
async def list_project_messages(
    project_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    """Return every message in the project, newest first."""
    rows = await message_service.list_project_messages(session, project_id, limit=limit)
    out = [_to_out(r) for r in rows]
    return MessageListResponse(messages=out, total=len(out))


@router.delete("/{project_id}/messages")
async def clear(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Wipe every message for the project. Idempotent — returns 0 when empty."""
    removed = await message_service.clear_project_messages(session, project_id)
    return {"project_id": project_id, "removed": removed}