"""Schemas for the per-host message endpoints (Phase 08)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MessageDirectionLiteral = Literal["in", "out"]


class MessageIn(BaseModel):
    """Body for POST /api/projects/{project_id}/hosts/{host_id}/messages.

    Sent by the host agent's ``message_reporter`` after every send/receive.
    ``project_id`` and ``host_id`` come from the URL — we don't accept them
    in the body so the path is the single source of truth.
    """

    direction: MessageDirectionLiteral = Field(
        ..., description="'in' if this host received, 'out' if it sent"
    )
    peer_host_id: str | None = Field(
        default=None, description="Other endpoint of the message"
    )
    comm_id: str | None = Field(
        default=None,
        description="Cross-ref into the orchestrator's Communication row (if known)",
    )
    payload: str = Field(..., description="Raw message body")
    protocol: str = Field(default="HTTP", description="HTTP / TCP / SQL / FILE")
    timestamp: datetime | None = Field(
        default=None,
        description="ISO 8601 from the agent; backend fills in now() if missing",
    )


class MessageOut(BaseModel):
    """One message row returned to clients."""

    id: int
    project_id: str
    host_id: str
    direction: str
    peer_host_id: str | None
    comm_id: str | None
    payload: str
    protocol: str
    timestamp: datetime


class MessageListResponse(BaseModel):
    """Wrapped list for GET …/hosts/{host_id}/messages."""

    messages: list[MessageOut]
    total: int