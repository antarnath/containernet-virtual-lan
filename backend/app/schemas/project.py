"""Pydantic schemas for the /api/projects endpoints (M4 5-primitive model).

The split between "In" (request body) and "Out" (response body) lets the
API evolve in both directions independently. ``In`` schemas are strict;
``Out`` schemas include server-generated fields (id, status, created_at).

5-primitive model:
  * Project      — the whole canvas
  * ProjectNode  — a device (host / switch / router / server / attacker)
  * ProjectInterface — a port on a node
  * ProjectLink  — a wire between two interfaces (one Docker bridge)
  * ProjectCapture — the passive sniffer on a link (1:1 with the link)

There is no "subnet" table — a subnet is whatever set of nodes share
a bridge (i.e. share a link).
"""

from __future__ import annotations

from datetime import datetime
from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─── 5 node kinds + the 5 attack modes (mirror the ORM) ──────────────
NodeKindLiteral = Literal["host", "switch", "router", "server", "attacker"]

AttackModeLiteral = Literal[
    "unknown_host",
    "duplicate_ip",
    "arp_spoof",
    "tcp_flood",
    "http_flood",
]

ProjectStatusLiteral = Literal[
    "draft", "starting", "running", "partial", "stopped", "error",
]


# ═══════════════════════════════════════════════════════════════════════
#  REQUESTS
# ═══════════════════════════════════════════════════════════════════════

class ProjectCreateIn(BaseModel):
    """Body for POST /api/projects.

    M4 is intentionally minimal: just the name. The user adds nodes
    via POST /nodes, interfaces via POST /nodes/{id}/interfaces, and
    links via POST /links. There is no "topology_type" or "subnet"
    — the user is the engineer.
    """
    name: str = Field(..., min_length=1, max_length=80)


class ProjectUpdateIn(BaseModel):
    """Body for PATCH /api/projects/{id}.

    All fields optional. The canvas auto-saves viewport state on every
    pan/zoom; the user can rename the project here.
    """
    name: str | None = Field(default=None, min_length=1, max_length=80)
    viewport_x: float | None = None
    viewport_y: float | None = None
    viewport_zoom: float | None = None


class ProjectNodeCreateIn(BaseModel):
    """Body for POST /api/projects/{id}/nodes.

    ``name`` is optional; the backend auto-generates ``Host-1``,
    ``Router-2``, etc. based on the kind and the project's existing
    node count.
    """
    kind: NodeKindLiteral
    canvas_x: float = 0.0
    canvas_y: float = 0.0
    name: str | None = Field(default=None, min_length=1, max_length=100)
    attack_mode: AttackModeLiteral | None = None


class ProjectNodeUpdateIn(BaseModel):
    """Body for PATCH /api/projects/{id}/nodes/{node_id}."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    canvas_x: float | None = None
    canvas_y: float | None = None
    attack_mode: AttackModeLiteral | None = None


class ProjectInterfaceCreateIn(BaseModel):
    """Body for POST /api/projects/{id}/nodes/{node_id}/interfaces."""
    name: str = Field(..., min_length=1, max_length=50)
    ip_address: str | None = None
    subnet_mask: str | None = None  # "/24", "/30", etc.

    @field_validator("ip_address")
    @classmethod
    def _valid_ipv4(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            IPv4Address(v)
        except ValueError as exc:
            raise ValueError(f"ip_address must be a valid IPv4: {exc}")
        return v

    @field_validator("subnet_mask")
    @classmethod
    def _valid_mask(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("subnet_mask must look like '/24' or '/30'")
        try:
            n = int(v[1:])
        except ValueError as exc:
            raise ValueError(f"subnet_mask must be an integer: {exc}")
        if not 0 <= n <= 32:
            raise ValueError("subnet_mask must be between 0 and 32")
        return v


class ProjectInterfaceUpdateIn(BaseModel):
    """Body for PATCH /api/projects/{id}/interfaces/{iface_id}."""
    name: str | None = Field(default=None, min_length=1, max_length=50)
    ip_address: str | None = None
    subnet_mask: str | None = None

    @field_validator("ip_address")
    @classmethod
    def _valid_ipv4(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            IPv4Address(v)
        except ValueError as exc:
            raise ValueError(f"ip_address must be a valid IPv4: {exc}")
        return v

    @field_validator("subnet_mask")
    @classmethod
    def _valid_mask(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("subnet_mask must look like '/24' or '/30'")
        try:
            n = int(v[1:])
        except ValueError as exc:
            raise ValueError(f"subnet_mask must be an integer: {exc}")
        if not 0 <= n <= 32:
            raise ValueError("subnet_mask must be between 0 and 32")
        return v


class ProjectLinkCreateIn(BaseModel):
    """Body for POST /api/projects/{id}/links."""
    iface_a_id: str
    iface_b_id: str


# ═══════════════════════════════════════════════════════════════════════
#  RESPONSES
# ═══════════════════════════════════════════════════════════════════════

class ProjectInterfaceOut(BaseModel):
    id: str
    node_id: str
    name: str
    ip_address: str | None
    subnet_mask: str | None
    mac_address: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectNodeOut(BaseModel):
    id: str
    project_id: str
    name: str
    kind: str
    canvas_x: float
    canvas_y: float
    attack_mode: str | None
    container_id: str | None
    container_status: str
    created_at: datetime
    updated_at: datetime
    interfaces: list[ProjectInterfaceOut] = []

    class Config:
        from_attributes = True


class ProjectCaptureOut(BaseModel):
    id: str
    link_id: str
    container_id: str | None
    status: str
    last_packet_at: datetime | None
    packet_count: int

    class Config:
        from_attributes = True


class ProjectLinkOut(BaseModel):
    id: str
    project_id: str
    iface_a_id: str
    iface_b_id: str
    subnet_cidr: str | None
    subnet_color_index: int
    docker_bridge_name: str | None
    created_at: datetime
    capture: ProjectCaptureOut | None = None

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: str
    name: str
    status: str
    viewport_x: float
    viewport_y: float
    viewport_zoom: float
    node_count: int = 0
    link_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectDetailOut(ProjectOut):
    """ProjectOut + full topology (nodes + links) for the canvas."""
    nodes: list[ProjectNodeOut] = []
    links: list[ProjectLinkOut] = []


class ProjectListResponse(BaseModel):
    projects: list[ProjectOut]
    total: int
