"""Communication ORM model — one row per sent message.

M4 phase 05. Every call to ``communication_service.send_message``
inserts a row here. The message console (frontend) reads from this
table for the history; the canvas / wire view uses the
``realtime`` websocket (``type === 'message'`` event) for the
live "the packet just crossed your wire" highlight.

Columns:
  * id              — uuid, the comm_id the host agent saw
  * project_id      — the parent project
  * src_node_id     — who sent it (host / server / attacker)
  * dst_node_id     — who received it (NULL if dst_ip didn't match
                      any node in the project — free-form IP)
  * dst_ip          — the literal destination IP
  * protocol        — HTTP / TCP / ICMP / …
  * payload         — the body (truncated to 4 KB at write time)
  * status          — delivered | failed | unreachable
  * hops_count      — number of links in the resolved route
  * created_at      — when the backend received the request
  * delivered_at    — when the destination's /receive acked (NULL
                      if failed or unreachable)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_node import ProjectNode


class Communication(Base):
    __tablename__ = "communications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    src_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    dst_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dst_ip: Mapped[str] = mapped_column(String(45))
    protocol: Mapped[str] = mapped_column(String(16), default="HTTP")
    payload: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    hops_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped["Project"] = relationship()
    src_node: Mapped["ProjectNode"] = relationship(foreign_keys=[src_node_id])
    dst_node: Mapped["ProjectNode | None"] = relationship(foreign_keys=[dst_node_id])

    __table_args__ = (
        Index("idx_comm_project_created", "project_id", "created_at"),
        Index("idx_comm_src_node", "src_node_id"),
        Index("idx_comm_dst_node", "dst_node_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Communication {self.id[:8]} "
            f"{self.src_node_id[:8]}->{self.dst_ip} status={self.status}>"
        )