"""ProjectCapture ORM model — one row per passive sniffer on a link.

M4 replaces M2's "one capture container per project" with "one
capture container per link". Each link gets a capture; the container
runs tcpdump on that link's bridge and writes NDJSON for the wire
view to read.

A capture is the 1:1 child of a link (the ``UNIQUE`` constraint on
``link_id``). When the link is deleted, the capture goes with it.
The capture container's lifecycle is owned by the start/stop project
flow in phase 02 / phase 04.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project_link import ProjectLink


class ProjectCapture(Base):
    __tablename__ = "project_captures"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    link_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_links.id", ondelete="CASCADE"),
        unique=True,  # one capture per link
    )
    # Docker container ID. NULL until phase 02 spawns the container.
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="idle"   # idle | running | error
    )
    # Last packet timestamp — updated by packet_service as packets
    # stream in (phase 04). NULL until the first packet arrives.
    last_packet_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    packet_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # ── relationships ──────────────────────────────────────────────────
    link: Mapped["ProjectLink"] = relationship(back_populates="capture")

    def __repr__(self) -> str:
        return f"<ProjectCapture link={self.link_id} status={self.status}>"
