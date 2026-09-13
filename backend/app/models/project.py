"""Project ORM model — represents a user-created virtual LAN.

A project is the unit of work in ContainerNet. It owns:
  * a topology (mesh / star / ring / bus / tree)
  * a fixed host count (decided at creation)
  * a fixed subnet (also decided at creation)
  * a set of ProjectHost rows (one per virtual machine in the LAN)
  * a set of ProjectEdge rows (one per link in the topology graph)

Phase 2 only persists the topology graph. Phase 03 will spawn the actual
Docker containers and update ``container_id`` on the ProjectHost rows.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base


class ProjectStatus(str, enum.Enum):
    """Lifecycle of a project."""
    DRAFT = "draft"           # topology persisted, no containers yet
    RUNNING = "running"       # all containers up
    PARTIAL = "partial"       # some containers up, some down
    STOPPED = "stopped"       # containers stopped, project still in DB


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100))
    topology_type: Mapped[str] = mapped_column(String(20))
    host_count: Mapped[int] = mapped_column(Integer)
    subnet: Mapped[str] = mapped_column(String(20))   # e.g. "10.20.0.0/24"
    gateway: Mapped[str] = mapped_column(String(45))  # e.g. "10.20.0.1"
    status: Mapped[str] = mapped_column(
        SAEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.DRAFT,
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
    # cascade="all, delete-orphan" ensures that deleting a project removes
    # all its hosts and edges in the same transaction. This is enforced at
    # the FK level too (ondelete="CASCADE") so raw SQL deletes work.
    hosts: Mapped[list["ProjectHost"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["ProjectEdge"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Project {self.name} {self.topology_type} "
            f"hosts={self.host_count} subnet={self.subnet} status={self.status}>"
        )
