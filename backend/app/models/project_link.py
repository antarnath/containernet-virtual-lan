"""ProjectLink ORM model — one row per wire the user drew on the canvas.

A link is two interfaces on two different nodes, joined by a wire.
In M4, **one link = one Docker bridge**. The backend creates a Linux
bridge per link at start time, attaches both endpoint veths, and pins
the IPs the user typed.

A link has:
  * iface_a_id, iface_b_id — the two endpoints
  * subnet_cidr — derived from the two endpoint IPs + mask (stored
    for query speed; the source of truth is the interface columns)
  * subnet_color_index — 1..6, the wire color slot from the
    design-system palette
  * docker_bridge_name — the Linux bridge name, set when the project
    is started (NULL while in draft)
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_interface import ProjectInterface
    from app.models.project_capture import ProjectCapture


# ─── subnet_cidr column type ───────────────────────────────────────────
# Same pattern as ProjectInterface.ip_address: a plain Python ``str``
# in service code, a PostgreSQL CIDR on disk. The wrapper handles the
# str ↔ ip_network translation on the bind/result side.
class _CIDRString(TypeDecorator):
    impl = CIDR
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, str):
            return ipaddress.ip_network(value, strict=False)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            return str(value)
        return str(value)


class ProjectLink(Base):
    __tablename__ = "project_links"
    __table_args__ = (
        # A link can't have the same interface on both ends.
        CheckConstraint("iface_a_id <> iface_b_id", name="ck_link_no_self_loop"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    iface_a_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_interfaces.id", ondelete="CASCADE"),
        index=True,
    )
    iface_b_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_interfaces.id", ondelete="CASCADE"),
        index=True,
    )
    # Derived from the two endpoint IPs (the union of both endpoints'
    # subnet must agree). Stored for query speed; recomputed in the
    # service layer if either endpoint changes. The column type is
    # a custom TypeDecorator around CIDR so the service can pass a
    # plain Python ``str`` ("10.0.0.0/24").
    subnet_cidr: Mapped[str | None] = mapped_column(
        _CIDRString(), nullable=True
    )
    # 1..6, cycles past 6. The canvas UI uses this to pick the wire
    # color from design-system.md §2.5.
    subnet_color_index: Mapped[int] = mapped_column(SmallInteger, default=1)
    # Set by the start_project lifecycle in phase 02. The bridge name
    # follows the convention ``proj_<project_short>_link_<link_short>``.
    docker_bridge_name: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # ── relationships ──────────────────────────────────────────────────
    project: Mapped["Project"] = relationship(back_populates="links")
    iface_a: Mapped["ProjectInterface"] = relationship(
        "ProjectInterface",
        foreign_keys=[iface_a_id],
    )
    iface_b: Mapped["ProjectInterface"] = relationship(
        "ProjectInterface",
        foreign_keys=[iface_b_id],
    )
    capture: Mapped["ProjectCapture | None"] = relationship(
        back_populates="link",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        a = self.iface_a.name if self.iface_a else "?"
        b = self.iface_b.name if self.iface_b else "?"
        return f"<ProjectLink {a} <-> {b} on {self.subnet_cidr}>"
