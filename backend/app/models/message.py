"""Message ORM model — Phase 08 (per-host message windows).

Every time a host agent SENDS or RECEIVES a communication, it POSTs a
``Message`` row to the backend. The backend stores it and broadcasts a
``message`` WebSocket event to every subscriber of the relevant
``project_id`` so the frontend's per-host console can stream the bubble
in real time.

A ``Message`` row is scoped to ONE ``(project_id, host_id)`` pair — the
``host_id`` is the local host's identifier (``host-1``, ``host-2`` …).
``peer_host_id`` is whichever other endpoint was on the other side of
the call (``out`` ⇒ the destination, ``in`` ⇒ the source).
``comm_id`` ties the row back to the corresponding ``Communication``
orchestrator row when one exists.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.host import Base


class MessageDirection(str, enum.Enum):
    IN = "in"
    OUT = "out"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    host_id: Mapped[str] = mapped_column(String(50), index=True)
    direction: Mapped[str] = mapped_column(
        SAEnum(MessageDirection, name="message_direction", values_callable=lambda x: [e.value for e in x]),
    )
    peer_host_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comm_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[str] = mapped_column(Text)
    protocol: Mapped[str] = mapped_column(String(20), default="HTTP")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Fast history reads: "last 100 messages for this host, newest first".
        Index(
            "ix_messages_project_host_ts",
            "project_id",
            "host_id",
            "timestamp",
        ),
    )

    def __repr__(self) -> str:
        arrow = "→" if self.direction == MessageDirection.OUT.value else "←"
        return (
            f"<Message {self.project_id[:8]} {self.host_id} {arrow} "
            f"{self.peer_host_id} ({self.protocol})>"
        )