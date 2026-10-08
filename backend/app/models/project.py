"""Project ORM model — represents a user-built virtual network.

M4 — the project is the canvas. It owns:
  * a set of ``ProjectNode`` rows (5 device kinds)
  * a set of ``ProjectLink`` rows (one per wire)
  * the canvas viewport state (for pan/zoom restore)
  * a lifecycle status (draft / starting / running / partial / stopped / error)

The M2 fields ``topology_type``, ``host_count``, ``subnet``, and
``gateway`` are **removed**: there are no templates in M4 and the
user types IPs on every interface individually. The M2 fields are
preserved as nullable columns during the M4 migration so any pre-M4
data doesn't crash, but the API no longer reads or writes them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project_node import ProjectNode
    from app.models.project_link import ProjectLink


class ProjectStatus(str, enum.Enum):
    """Lifecycle of a project."""
    DRAFT = "draft"            # canvas persisted, no containers yet
    STARTING = "starting"      # phase 02: spawn in progress
    RUNNING = "running"        # all containers up
    PARTIAL = "partial"        # some containers up, some down
    STOPPED = "stopped"        # containers stopped, project still in DB
    ERROR = "error"            # last start failed; see logs


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100))

    # ── M2 fields kept nullable for forward compatibility ──────────────
    # New code MUST NOT read or write these. They exist only so the
    # ``_PATCHES`` in core/database.py can drop the old M2 model
    # without crashing on legacy rows.
    topology_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    host_count: Mapped[int | None] = mapped_column(nullable=True)
    subnet: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gateway: Mapped[str | None] = mapped_column(String(45), nullable=True)

    status: Mapped[str] = mapped_column(
        # ProjectStatus is a str enum (lowercase values: "draft",
        # "starting", …). We must tell SQLAlchemy to write the *value*
        # (lowercase) rather than the default *name* (UPPERCASE) — the
        # PG enum was created with the lowercase values.
        SAEnum(
            ProjectStatus,
            name="project_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ProjectStatus.DRAFT,
    )

    # ── canvas viewport (pan/zoom state, restored on reopen) ──────────
    viewport_x: Mapped[float] = mapped_column(Float, default=0.0)
    viewport_y: Mapped[float] = mapped_column(Float, default=0.0)
    viewport_zoom: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── relationships ──────────────────────────────────────────────────
    # cascade="all, delete-orphan" ensures deleting a project removes
    # all its nodes (and through them, all interfaces + links) in one
    # transaction. Enforced at the FK level too (ondelete="CASCADE").
    nodes: Mapped[list["ProjectNode"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectNode.created_at",
    )
    links: Mapped[list["ProjectLink"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectLink.created_at",
    )

    def __repr__(self) -> str:
        n_nodes = len(self.nodes) if self.nodes else 0
        n_links = len(self.links) if self.links else 0
        return (
            f"<Project {self.name} status={self.status} "
            f"nodes={n_nodes} links={n_links}>"
        )
