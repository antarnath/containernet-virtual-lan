"""AttackSignal ORM model — one row per detected attack signal.

M4 phase 06. The attack_detector service polls every attacker's
:9092/state endpoint once per second. When the attacker's reported
``packets_per_sec`` exceeds the per-mode threshold (or when a one-shot
event like a duplicate-IP claim is observed), the detector writes an
``AttackSignal`` row and broadcasts a ``attack_signal`` WebSocket event.

Signals are append-only — there's no "dismiss" flow like AnomalyEvent.
The UI decides when to age them out (it keeps the most recent 50 per
attacker in memory).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.project_node import ProjectNode


class AttackSignalKind(str, enum.Enum):
    """The 5 categories the attack_detector emits."""
    NEW_MAC = "new_mac"             # unknown_host: a new MAC appeared on a link
    DUPLICATE_IP = "duplicate_ip"   # duplicate_ip mode active
    ARP_RATE = "arp_rate"           # arp_spoof: GARP rate > 1/sec
    SYN_RATE = "syn_rate"           # tcp_flood: SYN rate > 5/sec
    HTTP_RATE = "http_rate"         # http_flood: HTTP rate > 20/sec


# Per-mode thresholds. The detector compares the attacker's reported
# packets_per_sec against the threshold and fires a signal on every
# poll where it exceeds. (The signal rate naturally throttles because
# the detector itself only polls once per second.)
SIGNAL_THRESHOLDS: dict[str, float] = {
    AttackSignalKind.ARP_RATE.value: 1.0,
    AttackSignalKind.SYN_RATE.value: 5.0,
    AttackSignalKind.HTTP_RATE.value: 20.0,
    # For these one-shot signals, ANY running attack with the matching
    # mode fires a signal — the threshold is just a sentinel.
    AttackSignalKind.NEW_MAC.value: 0.0,
    AttackSignalKind.DUPLICATE_IP.value: 0.0,
}


class AttackSignal(Base):
    __tablename__ = "attack_signals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    attacker_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="CASCADE"),
    )
    # May be null for the global "new_mac" signal (a new MAC appeared
    # but we don't yet know whose victim it is).
    victim_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_kind: Mapped[str] = mapped_column(String(40))
    # The measured value (packets/sec, or "1" for one-shot signals).
    value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    # The window the detector looked at to compute the value.
    window_sec: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    project: Mapped["Project"] = relationship()
    attacker: Mapped["ProjectNode"] = relationship(
        foreign_keys=[attacker_node_id]
    )
    victim: Mapped["ProjectNode | None"] = relationship(
        foreign_keys=[victim_node_id]
    )

    __table_args__ = (
        Index("idx_signals_project_created", "project_id", "created_at"),
        Index("idx_signals_attacker", "attacker_node_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "attacker_node_id": self.attacker_node_id,
            "victim_node_id": self.victim_node_id,
            "signal_kind": self.signal_kind,
            "value": self.value,
            "threshold": self.threshold,
            "window_sec": self.window_sec,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<AttackSignal {self.signal_kind} "
            f"value={self.value:.1f} thr={self.threshold:.1f} "
            f"attacker={self.attacker_node_id[:8]}>"
        )
