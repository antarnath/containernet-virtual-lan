"""Pydantic schemas for the /api/projects endpoints.

The split between "In" (request body) and "Out" (response body) lets the
API evolve in both directions independently. ``In`` schemas are strict;
``Out`` schemas include server-generated fields (id, status, created_at).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


TopologyLiteral = Literal["mesh", "star", "ring", "bus", "tree"]


# ─── requests ───────────────────────────────────────────────────────────────

class ProjectCreateIn(BaseModel):
    """Body for POST /api/projects."""
    name: str = Field(..., min_length=1, max_length=100)
    topology_type: TopologyLiteral
    host_count: int = Field(..., ge=1, le=32)
    subnet: str = Field(..., description="IPv4 CIDR, e.g. '10.20.0.0/24'")

    @field_validator("subnet")
    @classmethod
    def _looks_like_cidr(cls, v: str) -> str:
        # Just sanity-check the format here; deeper validation (overlap with
        # reserved ranges, host-count fit) happens in the topology generator.
        if "/" not in v:
            raise ValueError("subnet must be CIDR notation, e.g. '10.20.0.0/24'")
        return v


class NodePositionIn(BaseModel):
    """Body for PATCH /api/projects/{id}/nodes/{host_id}."""
    position_x: float
    position_y: float


# ─── responses ──────────────────────────────────────────────────────────────

class ProjectHostOut(BaseModel):
    id: str
    host_id: str
    hostname: str
    ip_address: str
    container_id: str | None
    position_x: float
    position_y: float
    status: str
    last_seen: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectHostListResponse(BaseModel):
    """Response shape for ``GET /api/projects/{project_id}/hosts``."""
    hosts: list[ProjectHostOut]
    total: int
    online: int
    offline: int


class ProjectEdgeOut(BaseModel):
    id: str
    source_host_id: str
    dest_host_id: str

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: str
    name: str
    topology_type: str
    host_count: int
    subnet: str
    gateway: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectDetailOut(ProjectOut):
    """ProjectOut plus the full topology (nodes + edges) for the canvas."""
    hosts: list[ProjectHostOut]
    edges: list[ProjectEdgeOut]


class ProjectListResponse(BaseModel):
    projects: list[ProjectOut]
    total: int
