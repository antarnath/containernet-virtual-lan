"""ProjectHost ORM model — one row per host inside a project.

This is the per-project analogue of the legacy global ``Host`` table used
by the static pc1/pc2/pc3 setup. We keep the legacy ``Host`` table intact
during the dynamic transition — it backs the old ``/api/hosts`` endpoint
until Phase 09 retires the static services.

Key
---
Each row is uniquely identified by ``(project_id, host_id)`` — host IDs
are scoped to a project (``host-1``, ``host-2`` … ``host-N``), so the same
``host_id`` may exist in multiple projects.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base


class ProjectHostStatus(str, enum.Enum):
    PENDING = "pending"     # project created, container not yet spawned
    ONLINE = "online"       # heartbeat received within threshold
    OFFLINE = "offline"     # no heartbeat within threshold
    UNKNOWN = "unknown"     # never seen


class ProjectHost(Base):
    __tablename__ = "project_hosts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    host_id: Mapped[str] = mapped_column(String(50), index=True)
    hostname: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(45))
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        SAEnum(ProjectHostStatus, name="project_host_status"),
        default=ProjectHostStatus.PENDING,
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Back-reference so Project.hosts works.
    project: Mapped["Project"] = relationship(  # noqa: F821
        back_populates="hosts",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectHost project={self.project_id} host={self.host_id} "
            f"ip={self.ip_address} status={self.status}>"
        )
