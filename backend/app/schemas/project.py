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

import re
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
#  M5-01 / 1.2 — DHCP server config (per router interface)
# ═══════════════════════════════════════════════════════════════════════

class InterfaceDHCPConfigIn(BaseModel):
    """Body for PUT /api/projects/<pid>/nodes/<nid>/interfaces/<iid>/dhcp.

    The pool endpoints must both be set when ``enabled=True`` and
    must lie inside the bridge's subnet (validated server-side).
    ``lease_time`` is in seconds (60..86400). ``dns`` is a
    comma-separated IPv4 list (each entry validated).
    """
    enabled: bool = False
    pool_start: str | None = None
    pool_end: str | None = None
    lease_time: int = 43200  # 12 hours
    dns: str | None = None

    @field_validator("pool_start", "pool_end")
    @classmethod
    def _valid_ipv4(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        try:
            IPv4Address(v)
        except ValueError as exc:
            raise ValueError(f"must be a valid IPv4: {exc}")
        return v

    @field_validator("lease_time")
    @classmethod
    def _valid_lease(cls, v: int) -> int:
        if not 60 <= v <= 86400:
            raise ValueError("lease_time must be between 60 and 86400 seconds")
        return v

    @field_validator("dns")
    @classmethod
    def _valid_dns(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        for part in v.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                IPv4Address(part)
            except ValueError as exc:
                raise ValueError(f"dns entry {part!r} must be a valid IPv4: {exc}")
        return v


# ═══════════════════════════════════════════════════════════════════════
#  M5-01 / 1.3 — DHCP relay config (per router interface)
# ═══════════════════════════════════════════════════════════════════════

class InterfaceDHCPRelayConfigIn(BaseModel):
    """Body for PUT /api/projects/<pid>/nodes/<nid>/interfaces/<iid>/dhcp/relay.

    A single interface is either a DHCP *server* (feature 1.2) or a
    DHCP *relay* (feature 1.3) — never both. Validation of the
    mutual exclusion is done in the service layer because it needs
    to see the current state of the iface's ``dhcp_enabled`` field.
    ``server_ip`` is the IPv4 of the upstream DHCP server that
    should receive the relayed DISCOVERs. The iface is the one on
    which DISCOVERs are received from clients — the relay uses
    that iface's IP as the giaddr.
    """
    enabled: bool = False
    server_ip: str | None = None

    @field_validator("server_ip")
    @classmethod
    def _valid_server_ip(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        try:
            IPv4Address(v)
        except ValueError as exc:
            raise ValueError(f"must be a valid IPv4: {exc}")
        return v


# ═══════════════════════════════════════════════════════════════════════
#  M5-01 / 1.4 — DHCP reservations (MAC → fixed IP bindings)
# ═══════════════════════════════════════════════════════════════════════

# 12 hex + 5 colons, e.g. "aa:bb:cc:dd:ee:ff". Case-insensitive;
# we normalise to lowercase before storing.
_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


def _normalise_mac(value: str) -> str:
    """Lowercase + validate a MAC string. Raises ValueError on bad input."""
    if not isinstance(value, str):
        raise ValueError("mac_address must be a string")
    v = value.strip().lower()
    if not _MAC_RE.match(v):
        raise ValueError(
            f"mac_address must look like 'aa:bb:cc:dd:ee:ff' (got {value!r})"
        )
    return v


class DHCPReservationIn(BaseModel):
    """A single MAC → IP binding for a DHCP-server router interface.

    The IP must lie inside the iface's DHCP pool (validated in the
    service layer — pool membership needs a DB read, not just the
    request body). The MAC is normalised to lowercase on the way in
    so the UNIQUE constraint on (iface_id, mac_address) doesn't
    reject "AA:BB:..." and "aa:bb:..." as different rows.

    The hostname is optional; when present, dnsmasq binds it as
    the local-DNS name for the client. 63 chars is the DNS label
    max (RFC 1035); dnsmasq will reject longer anyway.
    """
    mac_address: str
    ip_address: str
    hostname: str | None = None

    @field_validator("mac_address")
    @classmethod
    def _valid_mac(cls, v: str) -> str:
        return _normalise_mac(v)

    @field_validator("ip_address")
    @classmethod
    def _valid_ip(cls, v: str) -> str:
        try:
            IPv4Address(v)
        except ValueError as exc:
            raise ValueError(f"must be a valid IPv4: {exc}")
        return v

    @field_validator("hostname")
    @classmethod
    def _valid_hostname(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if len(v) > 63:
            raise ValueError("hostname must be ≤ 63 characters (DNS label max)")
        # dnsmasq's regex is slightly looser but a basic sanity check
        # is enough; the alternative (full RFC 1123) is over-engineered
        # for a "type a friendly name" form.
        if not re.match(r"^[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?$", v):
            raise ValueError(
                "hostname must be alphanumeric (hyphens allowed in the middle)"
            )
        return v


class DHCPReservationsIn(BaseModel):
    """Body for PUT /api/projects/<pid>/nodes/<nid>/interfaces/<iid>/dhcp/reservations.

    Replaces the full reservation list (the API is idempotent — send
    the desired end-state, not a delta). An empty list disables all
    reservations. The service layer additionally rejects duplicate
    MACs or IPs inside the same list (those should be a single row).
    """
    reservations: list[DHCPReservationIn] = Field(default_factory=list)


class DHCPReservationOut(BaseModel):
    id: str
    iface_id: str
    mac_address: str
    ip_address: str
    hostname: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DHCPReservationsOut(BaseModel):
    reservations: list[DHCPReservationOut] = Field(default_factory=list)


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
    # M5-01 / 1.2 — DHCP server config (router interfaces only).
    dhcp_enabled: bool = False
    dhcp_pool_start: str | None = None
    dhcp_pool_end: str | None = None
    dhcp_lease_time: int = 43200
    dhcp_dns: str | None = None
    # M5-01 / 1.3 — DHCP relay config (router interfaces only).
    # Mutually exclusive with ``dhcp_enabled``; a single iface is
    # either a server or a relay, never both.
    dhcp_relay_enabled: bool = False
    dhcp_relay_server: str | None = None
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
