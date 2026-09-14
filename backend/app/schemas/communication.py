"""Schemas for the per-project communications endpoints.

Phase 06 — every comm now lives inside a project. The URL carries the
project_id (``/api/projects/{project_id}/communications``); request and
response bodies include it so the frontend can route the event back to
the right per-project store even before the URL is read.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# Allowed protocol values — kept loose so future additions don't need a
# schema change. Matches the values rendered by ProtocolSelector.
ProtocolLiteral = Literal["HTTP", "TCP", "SQL", "FILE"]


class CommunicationCreateIn(BaseModel):
    """Body for POST /api/projects/{project_id}/communications.

    The frontend doesn't need to send ``project_id`` in the body — it's
    already in the URL — but we accept it if the caller wants to be
    explicit. The orchestrator always uses the URL value as the
    authoritative project.
    """

    source_host_id: str = Field(..., description="host_id of the sender, e.g. 'host-1'")
    destination_host_id: str = Field(..., description="host_id of the receiver, e.g. 'host-2'")
    protocol: str = Field(default="HTTP", description="HTTP / TCP / SQL / FILE")
    payload: str = Field(..., description="Message body")
    project_id: str | None = Field(
        default=None,
        description="Optional — overridden by the URL path.",
    )


class CommunicationOut(BaseModel):
    """One communication record returned to clients."""

    id: str
    project_id: str | None = None
    source_host_id: str
    dest_host_id: str
    protocol: str
    payload: str
    data_size: int
    latency_ms: float | None
    status: str
    timestamp: datetime


class CommunicationListResponse(BaseModel):
    """Wrapped list for GET …/communications."""

    communications: list[CommunicationOut]
    total: int
