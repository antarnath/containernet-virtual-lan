"""Schemas for the /api/health heartbeat endpoint."""

from datetime import datetime

from pydantic import BaseModel


class HeartbeatIn(BaseModel):
    host_id: str
    host_name: str
    host_ip: str
    ts: datetime | None = None


class HeartbeatOut(BaseModel):
    status: str
    host_id: str
    message: str