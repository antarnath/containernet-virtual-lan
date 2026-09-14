"""Message persistence + WebSocket fan-out — Phase 08.

The host agent POSTs one ``Message`` row per send/receive. We persist it
and publish a ``message`` event to every subscriber of the same
``project_id`` so the frontend's per-host console can render the bubble
in real time.

Storage is Postgres for MVP. The volume per project is small (each
trigger writes two rows total: one OUT, one IN). If we ever need lower
latency for high message rates, swap the storage to Redis lists while
keeping this API surface stable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageDirection
from app.schemas.message import MessageIn
from app.ws import publish_to_project


def _dir_str(d) -> str:
    """Return the enum's string value, tolerating both enum and raw str."""
    if hasattr(d, "value"):
        return d.value
    return str(d)


async def record_message(
    session: AsyncSession, project_id: str, host_id: str, body: MessageIn
) -> Message:
    """Persist one message row + broadcast the WebSocket event.

    The host agent's reporter is fire-and-forget, so we don't propagate
    individual failures as 5xx — we log and return the row anyway. Real
    failures (DB unavailable) bubble up to FastAPI and surface as 500s.
    """
    row = Message(
        project_id=project_id,
        host_id=host_id,
        direction=MessageDirection(body.direction),
        peer_host_id=body.peer_host_id,
        comm_id=body.comm_id,
        payload=body.payload,
        protocol=body.protocol or "HTTP",
        timestamp=body.timestamp or datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    publish_to_project(
        str(project_id),
        "message",
        {
            "id": row.id,
            "project_id": str(project_id),
            "host_id": row.host_id,
            "direction": _dir_str(row.direction),
            "peer_host_id": row.peer_host_id,
            "comm_id": row.comm_id,
            "payload": row.payload,
            "protocol": row.protocol,
            "timestamp": row.timestamp.isoformat(),
        },
    )
    return row


async def list_project_host_messages(
    session: AsyncSession, project_id: str, host_id: str, limit: int = 100
) -> list[Message]:
    """History for ONE host inside ONE project — newest first."""
    result = await session.execute(
        select(Message)
        .where(Message.project_id == project_id, Message.host_id == host_id)
        .order_by(Message.timestamp.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def list_project_messages(
    session: AsyncSession, project_id: str, limit: int = 1000
) -> list[Message]:
    """History across EVERY host of ONE project — used by the legacy
    ``/api/communications`` style flow if we ever need it."""
    result = await session.execute(
        select(Message)
        .where(Message.project_id == project_id)
        .order_by(Message.timestamp.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def clear_project_messages(session: AsyncSession, project_id: str) -> int:
    """Wipe every message row for a project. Returns the number removed.

    Intentionally does NOT emit a WS event — the frontend already has the
    delete button, so the local UI updates optimistically.
    """
    result = await session.execute(
        delete(Message).where(Message.project_id == project_id)
    )
    removed = int(result.rowcount or 0)
    # The DELETE above goes through SQLAlchemy's session.execute(); without an
    # explicit commit the row stays in the DB until the session closes. The
    # API layer is built around ``get_session`` yielding fresh sessions per
    # request, so the safest pattern is to commit here.
    await session.commit()
    return removed


async def list_recent_messages(
    session: AsyncSession, limit: int = 100
) -> list[Message]:
    """Cross-project recent feed — used by the Phase 09 dashboard summary."""
    result = await session.execute(
        select(Message)
        .order_by(Message.timestamp.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(result.scalars())