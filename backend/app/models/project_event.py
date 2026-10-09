"""ProjectEvent — the audit log for a project.

M4 phase 07. Every significant backend action writes a row:
  * lifecycle: starting, running, stopping, stopped, error
  * node_started, node_stopped, node_error
  * link_created, link_deleted
  * bridge_created, bridge_deleted
  * message_sent
  * anomaly (links to the AnomalyEvent row id)
  * attack_signal (links to the AttackSignal row id)
  * error (any backend error that surfaces to the user)

Events are append-only. The frontend LogsView polls this table
(newest first, cursor-paginated) and subscribes to the WS channel
for live updates (the WS payload is the same row dict, plus
``{type: "event"}`` for routing).

Why a separate table from anomaly_event / attack_signal?
  Those are *typed* event tables with their own thresholds and
  detector loops. The project_events table is the *union* — the
  one place the LogsView reads. A given anomaly has exactly one
  row in anomaly_event AND one row in project_event (the latter
  is what the user sees in the timeline).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_node import ProjectNode
    from app.models.project_link import ProjectLink


class ProjectEventKind(str, enum.Enum):
    """The 9 event kinds the LogsView can show."""
    LIFECYCLE = "lifecycle"      # project start/stop/restart transitions
    NODE_STARTED = "node_started"
    NODE_STOPPED = "node_stopped"
    LINK_CREATED = "link_created"
    BRIDGE_CREATED = "bridge_created"
    MESSAGE_SENT = "message_sent"
    ANOMALY = "anomaly"
    ATTACK_SIGNAL = "attack_signal"
    ERROR = "error"


# Public string forms (so the API serialises them in a single place).
EVENT_KIND_VALUES = frozenset(k.value for k in ProjectEventKind)


class ProjectEvent(Base):
    __tablename__ = "project_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    kind: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Optional foreign keys — most events reference one of these.
    node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    link_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_links.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped["Project"] = relationship()
    node: Mapped["ProjectNode | None"] = relationship(foreign_keys=[node_id])
    link: Mapped["ProjectLink | None"] = relationship(foreign_keys=[link_id])

    __table_args__ = (
        Index("idx_events_project_ts", "project_id", "ts"),
        Index("idx_events_project_kind", "project_id", "kind"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "ts": self.ts.isoformat() if self.ts else None,
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail or {},
            "node_id": self.node_id,
            "link_id": self.link_id,
        }

    def __repr__(self) -> str:
        return (
            f"<ProjectEvent {self.kind} {self.summary[:40]!r} "
            f"at {self.ts.isoformat() if self.ts else '?'}>"
        )
