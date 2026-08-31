"""Schemas for the /api/hosts endpoint."""

from datetime import datetime

from pydantic import BaseModel


class HostOut(BaseModel):
    id: str
    host_id: str
    hostname: str
    ip_address: str
    status: str
    last_seen: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class HostListResponse(BaseModel):
    hosts: list[HostOut]
    total: int
    online: int
    offline: int