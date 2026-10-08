"""AnomalyEvent ORM model — one row per detected network anomaly.

M4 phase 03. The router panel polls the router's ARP table every 2s.
When an IP's MAC changes between polls (the classic MITM signature),
the proxy writes an AnomalyEvent row and broadcasts it over the
project's WebSocket so the canvas UI can light up the affected
node + show a banner.

``resolved_at`` is set when the user dismisses the banner — the row
stays in the DB for the logs view (phase 07) so the timeline of
"what happened" is preserved.
"""

from __future__ import annotations

import enum
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_node import ProjectNode


class AnomalyKind(str, enum.Enum):
    """The categories of anomaly the detector currently recognises."""
    ARP_MAC_CHANGE = "arp_mac_change"
    # Phase 03 only ships the ARP-MAC-change detector. Other kinds
    # (NEIGH_STALE, ROUTE_MISMATCH) are reserved for later phases.
    NEIGH_STALE = "neigh_stale"
    ROUTE_MISMATCH = "route_mismatch"


class AnomalySeverity(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    DANGER = "danger"


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    # The router whose ARP table produced the diff.
    # (Phase 03 anomalies are always router-sourced; the affected
    # endpoint is captured inside the `detail` JSON.)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    # One-line human description, e.g. "Host-1 (10.30.10.11) MAC
    # changed from 02:42:..:0b to 02:42:..:63".
    summary: Mapped[str] = mapped_column(Text)
    # Full before/after state as a JSON dict. Shape depends on kind:
    #   arp_mac_change: {"ip": "10.30.10.11", "old_mac": "...", "new_mac": "...", "iface": "eth1"}
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    # Set when the user clicks "Dismiss" on the banner. NULL = still
    # visible in the panel + canvas highlight.
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped["Project"] = relationship()
    node: Mapped["ProjectNode"] = relationship()

    __table_args__ = (
        Index("idx_anomalies_project_created", "project_id", "created_at"),
        Index("idx_anomalies_node", "node_id"),
    )

    def __repr__(self) -> str:
        return f"<AnomalyEvent {self.kind} severity={self.severity} node={self.node_id[:8]}>"
