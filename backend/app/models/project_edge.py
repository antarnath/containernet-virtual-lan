"""ProjectEdge ORM model — one row per link in a project's topology graph.

Edges are stored with ``source_host_id < dest_host_id`` lexicographically
so a (source, dest) pair never appears twice. The frontend treats the edge
as undirected.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base


class ProjectEdge(Base):
    __tablename__ = "project_edges"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_host_id", "dest_host_id",
            name="uq_project_edge_pair",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_host_id: Mapped[str] = mapped_column(String(50))
    dest_host_id: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        back_populates="edges",
    )

    def __repr__(self) -> str:
        return f"<ProjectEdge {self.source_host_id} <-> {self.dest_host_id}>"
