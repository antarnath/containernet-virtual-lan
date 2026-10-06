"""Packets API — M2-07 §4.

Exposes the per-project packet log to the dashboard:

  GET /api/projects/{project_id}/packets?since=<id>&limit=<n>
      REST replay of packet events with id > since.

  GET /api/projects/{project_id}/packets/stream
      Server-Sent Events stream of packet events. One `data:` line per
      packet, with `:hb` comments every 15 seconds to keep proxies alive.

Errors:
  404 — no such project
  409 — no capture container (project never started)
  503 — capture container is restarting / unhealthy
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.services import packet_service
from app.services.project_service import get_project


router = APIRouter(prefix="/projects", tags=["packets"])


async def _require_project(project_id: str, session: AsyncSession) -> None:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")


def _ensure_capture(project_id: str) -> str:
    container_id = packet_service.get_capture_container_id(project_id)
    if container_id is None:
        raise HTTPException(
            status_code=409,
            detail="no capture container — start the project first",
        )
    return container_id


@router.get("/{project_id}/packets")
async def get_packets(
    project_id: str,
    since: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Replay packet events with id > since."""
    await _require_project(project_id, session)
    _ensure_capture(project_id)
    try:
        events = packet_service.get_packets(project_id, since=since, limit=limit)
    except FileNotFoundError:
        # Capture hasn't written anything yet.
        return {"events": [], "since": since, "limit": limit}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"events": events, "since": since, "limit": limit}


def _sse_format(event: dict | None, comment: str | None = None) -> bytes:
    """Format a packet event (or comment) as an SSE frame."""
    if comment is not None:
        return f":{comment}\n\n".encode("utf-8")
    if event is None:
        return b":hb\n\n"
    return b"data: " + json.dumps(event).encode("utf-8") + b"\n\n"


async def _event_stream(
    project_id: str,
    since: int,
) -> AsyncIterator[bytes]:
    """Async generator that wraps packet_service.iter_packets into SSE."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def producer() -> None:
        """Sync producer thread: polls the capture container and pushes."""
        for kind, payload in packet_service.iter_packets(project_id, since=since):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))
            except Exception:
                # Queue full or loop closed — drop and let consumer catch up.
                pass
            if kind == "reset":
                return

    # Run the sync producer in a thread so it doesn't block the event loop.
    fut: asyncio.Future = asyncio.ensure_future(
        asyncio.to_thread(producer)
    )

    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Idle tick — emit a heartbeat every 15 s.
                yield _sse_format(None, comment="hb")
                continue
            if kind == ":hb":
                yield _sse_format(None, comment="hb")
            elif kind == "reset":
                yield b"event: reset\ndata: {}\n\n"
                break
            elif kind == "event" and payload is not None:
                yield _sse_format(payload)
    finally:
        if not fut.done():
            fut.cancel()


@router.get("/{project_id}/packets/stream")
async def stream_packets(
    project_id: str,
    since: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Live SSE stream of packet events."""
    await _require_project(project_id, session)
    _ensure_capture(project_id)

    async def gen() -> AsyncIterator[bytes]:
        async for chunk in _event_stream(project_id, since):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )
