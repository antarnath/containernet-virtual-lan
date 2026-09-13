"""Schemas for the /api/health heartbeat endpoint.

Phase 03 added ``project_id``: a host spawned for a project now sends its
project's UUID in every heartbeat, so the backend can route the heartbeat
into the right ``project_hosts`` row instead of the legacy global ``hosts``
table.

Legacy behaviour is preserved: if a heartbeat comes in without a
``project_id`` (the old static ``pc1/pc2/pc3`` still do), we fall back to
the global ``hosts`` table so Phase 03 doesn't break the existing setup
during the transition.
"""

from datetime import datetime

from pydantic import BaseModel


class HeartbeatIn(BaseModel):
    host_id: str
    host_name: str
    host_ip: str
    project_id: str | None = None   # NEW in Phase 03 — None for legacy hosts
    ts: datetime | None = None


class HeartbeatOut(BaseModel):
    status: str
    host_id: str
    message: str