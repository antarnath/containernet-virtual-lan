"""Schemas for the /api/communications endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class CommunicationCreate(BaseModel):
    """Body for POST /api/communications (what the frontend sends)."""

    source_host_id: str = Field(..., description="host_id of the sender, e.g. 'pc1'")
    destination_host_id: str = Field(..., description="host_id of the receiver, e.g. 'pc2'")
    protocol: str = Field(default="HTTP", description="HTTP / TCP / SQL / FILE")
    payload: str = Field(..., description="Message body")


class CommunicationOut(BaseModel):
    """One communication record returned to clients."""

    id: str
    source_host_id: str
    dest_host_id: str
    protocol: str
    payload: str
    data_size: int
    latency_ms: float | None
    status: str
    timestamp: datetime


class CommunicationListResponse(BaseModel):
    """Wrapped list for GET /api/communications."""

    communications: list[CommunicationOut]
    total: int