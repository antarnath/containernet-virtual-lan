"""ProjectNode ORM model — one row per device the user placed on the canvas.

M4 — replaces the M2 ``ProjectHost`` (which only modeled hosts). The new
node has a ``kind`` discriminator (host / switch / router / server /
attacker) so the canvas can render 5 device types and the backend can
spawn the right Docker image for each.

A node owns:
  * a position on the canvas (canvas_x, canvas_y)
  * a set of ``ProjectInterface`` rows (one per port)
  * for attackers only, an ``attack_mode`` string

The "no templates" rule means there is no preset for which kinds a
project contains. The user places every node.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_interface import ProjectInterface
    from app.models.project_link import ProjectLink


class NodeKind(str, enum.Enum):
    """The 5 device kinds the user can drop on the canvas."""
    HOST = "host"
    SWITCH = "switch"
    ROUTER = "router"
    SERVER = "server"
    ATTACKER = "attacker"


# The 5 attack modes the user can pick for an attacker node.
# Kept here (not in a separate file) so the canvas and the detector
# import the same enum. Phase 06 owns the actual attack logic.
ATTACK_MODES: tuple[str, ...] = (
    "unknown_host",
    "duplicate_ip",
    "arp_spoof",
    "tcp_flood",
    "http_flood",
)


class ProjectNode(Base):
    __tablename__ = "project_nodes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    # User-editable display name. Auto-suggested on creation
    # ("Host-1", "Router-2", …) but the user can rename freely.
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(
        # NodeKind is a str enum (lowercase values: "host", "switch", …).
        # values_callable so SQLAlchemy writes the value, not the name.
        SAEnum(
            NodeKind,
            name="node_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=NodeKind.HOST,
    )
    canvas_x: Mapped[float] = mapped_column(Float, default=0.0)
    canvas_y: Mapped[float] = mapped_column(Float, default=0.0)
    # Set only when kind == attacker. NULL otherwise.
    attack_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Container runtime fields — populated by phase 02's spawn_node().
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    container_status: Mapped[str] = mapped_column(
        String(20), default="idle"   # idle | starting | running | stopped | error
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── relationships ──────────────────────────────────────────────────
    project: Mapped["Project"] = relationship(back_populates="nodes")
    interfaces: Mapped[list["ProjectInterface"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
        order_by="ProjectInterface.created_at",
    )
    # Links that have an endpoint on this node (joined through the
    # interface). Used for "would dangle" checks on node delete.
    links: Mapped[list["ProjectLink"]] = relationship(
        secondary="project_interfaces",
        primaryjoin="ProjectNode.id==ProjectInterface.node_id",
        secondaryjoin=(
            "or_("
            "ProjectLink.iface_a_id==ProjectInterface.id,"
            "ProjectLink.iface_b_id==ProjectInterface.id"
            ")"
        ),
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<ProjectNode {self.name} kind={self.kind}>"
